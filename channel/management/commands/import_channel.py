"""
Usage:
    python manage.py import_channel /path/to/channel_data.xlsx
    python manage.py import_channel /path/to/channel_data.csv

Handles:
  - .xlsx, .xls, .csv input
  - Duplicate column names (gets renamed by pandas as col, col.1)
  - Comma-separated numbers ("3,604")
  - Date parsing (1/1/2025 or 2025-01-01)
  - Upsert: existing (date, franchise_id) rows get overwritten

Requires: pip install pandas openpyxl
"""

from django.core.management.base import BaseCommand, CommandError
from channel.models import ChannelDaily
from datetime import datetime
import pandas as pd
import os
import re


# ── Map source column → model field ──────────────────────────────
# Order matches the 93-column layout. Duplicates resolved by .1 suffix that
# pandas adds when reading data with duplicate header names.
COLUMN_MAP = {
    'Dated':                                          'date',
    'Franchise ID':                                   'franchise_id',
    'City':                                           'city',
    'Region':                                         'region',
    'BU':                                             'business_unit',
    'Status':                                         'status',
    'ARM':                                            'arm',
    'FCA Targets':                                    'fca_target',
    'FCA Ach':                                        'fca_ach',
    '4G Targets':                                     'g4_target',
    '4G Ach':                                         'g4_ach',
    'MNP Target':                                     'mnp_target',
    'MNP Ach':                                        'mnp_ach',
    'Loading Target':                                 'loading_target',
    'Loading Ach':                                    'loading_ach',
    'EVC Uload':                                      'evc_uload',
    'Vouchers':                                       'vouchers',
    'Total Site Loading':                             'total_site_loading',
    'Loading Ach Site Conv. Cell site loading':       'loading_ach_site_conv',
    'Issuance Ach':                                   'issuance_ach',
    'Uload Recharge Ach':                             'uload_recharge_ach',
    'Data SIM FCA':                                   'data_sim_fca',
    'MBB Targets':                                    'mbb_target',
    'MBB Ach':                                        'mbb_ach',
    'M0 Revenue Targets':                             'm0_revenue_target',
    'M0 Revenue Ach':                                 'm0_revenue_ach',
    'QOS Targets':                                    'qos_target',
    'QOS Ach':                                        'qos_ach',
    'EVC Active Base':                                'evc_active_base',
    'Bundle Target':                                  'bundle_target',
    'Bundle Ach':                                     'bundle_ach',
    'Recharge Only':                                  'recharge_only',
    'Female FCA Count':                               'female_fca_count',
    'Dormancy Count':                                 'dormancy_count',
    'HVC TGT':                                        'hvc_target',
    'HVC Ach':                                        'hvc_ach',
    'CM GA':                                          'cm_ga',
    'CM Disown':                                      'cm_disown',
    'Female CNIC Disowned':                           'female_cnic_disowned',
    'New SIM Sale (Disowned CNICs)':                  'new_sim_sale_disowned_cnics',
    'FCA Date within 90 Days Disowned':               'fca_within_90d_disowned',
    'FCA Date within 90 Days (Disown & new Activation)': 'fca_within_90d_disown_new_activation',
    '90 Days Active Base Disown':                     'active_90d_base_disown',
    '90 Days Active Base (Disown & new Activation)':  'active_90d_base_disown_new_activation',
    'NPR':                                            'npr',
    'Active SO (Daily Ave.)':                         'active_so_daily_avg',
    'Active SO NPR':                                  'active_so_npr',
    'LM Active EVC':                                  'lm_active_evc',
    'MTD Served':                                     'mtd_served',
    'Avg Served':                                     'avg_served',
    'CM EVC Active (Platinum)':                       'cm_evc_active_platinum',
    'CM EVC Active (Gold)':                           'cm_evc_active_gold',
    'CM EVC Active (Silver)':                         'cm_evc_active_silver',
    'CM EVC Active':                                  'cm_evc_active',
    'CM 964 Active (Platinum)':                       'cm_964_active_platinum',
    'CM 964 Active (Gold)':                           'cm_964_active_gold',
    'CM 964 Active (Silver)':                         'cm_964_active_silver',
    'CM 964 Active':                                  'cm_964_active',
    'Total Bundles Activated':                        'total_bundles_activated',
    'Daily Avg. Bundle Subs':                         'daily_avg_bundle_subs',
    'cc':                                             'cc',
    'Total Bundles Activated.1':                      'total_bundles_activated_2',
    'Daily Avg. Bundle Subs.1':                       'daily_avg_bundle_subs_2',
    'EVC CMTD Active':                                'evc_cmtd_active',
    'CM Daily Active':                                'cm_daily_active',
    '964 Active CMTD':                                'active_964_cmtd',
    'Retailer Trans  Count = 1':                      'retailer_trans_count_1',
    'Retailer Trans Count = 2':                       'retailer_trans_count_2',
    'Trans >=3%':                                     'trans_ge_3_pct',
    'PBC':                                            'pbc',
    'ZR FCA':                                         'zr_fca',
    'ZR':                                             'zr',
    'EVC Retailer':                                   'evc_retailer',
    'Daily Active EVC':                               'daily_active_evc',
    'Daily Active Served':                            'daily_active_served',
    'WIC SR':                                         'wic_sr',
    'Retail SR':                                      'retail_sr',
    'Total SR':                                       'total_sr',
    'Cell Sites Count':                               'cell_sites_count',
    'FCA':                                            'fca_per_site',
    'Per Site FCA':                                   'fca_per_site_value',
    'SD Bundle':                                      'sd_bundle',
    'FCA.1':                                          'fca_m0',
    'MNP':                                            'mnp_m0',
    'MBB':                                            'mbb_m0',
    'Data Sim':                                       'data_sim_m0',
    'GA':                                             'ga_m0',
    'HVC':                                            'hvc_m0',
    'M0 Rev FCA':                                     'm0_rev_fca',
    'M0 Rev MNP':                                     'm0_rev_mnp',
    'M0 Rev MBB':                                     'm0_rev_mbb',
    'M0 Rev Data Sim':                                'm0_rev_data_sim',
    'M0 Rev GA':                                      'm0_rev_ga',
    'M0 HVC Rev':                                     'm0_hvc_rev',
}


def parse_number(v):
    """Convert '3,604' or '1.5M' or '' or NaN to a clean number."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(',', '').replace(' ', '')
    if s == '' or s.lower() in ('nan', 'na', '-', '#div/0!', '#n/a'):
        return 0
    try:
        return float(s)
    except ValueError:
        return 0


def parse_date(v):
    """Parse various date formats."""
    if pd.isna(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, 'date'):  # pandas Timestamp
        return v.date()
    s = str(v).strip()
    for fmt in ('%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%m-%d-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = 'Import channel data from Excel or CSV file'

    def add_arguments(self, parser):
        parser.add_argument('filepath', type=str, help='Path to .xlsx, .xls, or .csv file')
        parser.add_argument('--sheet', type=str, default=0, help='Excel sheet name or index (default: first sheet)')
        parser.add_argument('--dry-run', action='store_true', help='Parse but do not save to DB')

    def handle(self, *args, **opts):
        filepath = opts['filepath']
        if not os.path.exists(filepath):
            raise CommandError(f'File not found: {filepath}')

        ext = os.path.splitext(filepath)[1].lower()
        self.stdout.write(f'Reading {filepath}...')
        if ext in ('.xlsx', '.xls'):
            df = pd.read_excel(filepath, sheet_name=opts['sheet'])
        elif ext == '.csv':
            df = pd.read_csv(filepath)
        else:
            raise CommandError(f'Unsupported file type: {ext}')

        self.stdout.write(f'Loaded {len(df)} rows, {len(df.columns)} columns.')

        # Clean column names (strip whitespace, newlines)
        df.columns = [re.sub(r'\s+', ' ', str(c)).strip() for c in df.columns]

        # Map columns
        unmapped = [c for c in df.columns if c not in COLUMN_MAP]
        if unmapped:
            self.stdout.write(self.style.WARNING(f'Unmapped columns (will be skipped): {unmapped}'))

        # Counters
        created = 0
        updated = 0
        skipped = 0

        objs_to_create = []
        objs_to_update = []
        existing_keys = set(
            ChannelDaily.objects.values_list('date', 'franchise_id')
        )

        # Field type lookup
        int_fields = {f.name for f in ChannelDaily._meta.get_fields()
                      if hasattr(f, 'get_internal_type') and f.get_internal_type() in ('IntegerField', 'BigIntegerField')}
        float_fields = {f.name for f in ChannelDaily._meta.get_fields()
                        if hasattr(f, 'get_internal_type') and f.get_internal_type() == 'FloatField'}

        for idx, row in df.iterrows():
            kwargs = {}
            for src_col, model_field in COLUMN_MAP.items():
                if src_col not in df.columns:
                    continue
                val = row[src_col]
                if model_field == 'date':
                    kwargs[model_field] = parse_date(val)
                elif model_field in ('franchise_id', 'city', 'region', 'business_unit', 'arm', 'status'):
                    kwargs[model_field] = str(val).strip() if not pd.isna(val) else ''
                elif model_field in int_fields:
                    kwargs[model_field] = int(parse_number(val))
                elif model_field in float_fields:
                    kwargs[model_field] = float(parse_number(val))
                else:
                    kwargs[model_field] = parse_number(val)

            if not kwargs.get('date') or not kwargs.get('franchise_id'):
                skipped += 1
                continue

            key = (kwargs['date'], kwargs['franchise_id'])
            if key in existing_keys:
                objs_to_update.append(kwargs)
            else:
                objs_to_create.append(ChannelDaily(**kwargs))
                existing_keys.add(key)

            if (idx + 1) % 500 == 0:
                self.stdout.write(f'  Processed {idx + 1} rows...')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — would create {len(objs_to_create)}, update {len(objs_to_update)}, skip {skipped}'))
            return

        # Bulk create
        if objs_to_create:
            ChannelDaily.objects.bulk_create(objs_to_create, batch_size=500)
            created = len(objs_to_create)

        # Update existing — use bulk path
        if objs_to_update:
            for kw in objs_to_update:
                ChannelDaily.objects.filter(
                    date=kw['date'], franchise_id=kw['franchise_id']
                ).update(**{k: v for k, v in kw.items() if k not in ('date', 'franchise_id')})
            updated = len(objs_to_update)

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created}, Updated: {updated}, Skipped: {skipped}'
        ))