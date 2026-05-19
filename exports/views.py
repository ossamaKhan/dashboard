import io
from datetime import datetime
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Sum, Avg, Count

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from marketing.models import SiteData


# ── Constants ─────────────────────────────────────────────────
ORANGE = 'F58220'
PURPLE = 'AB1DFE'
DARK   = '1A1235'
WHITE  = 'FFFFFF'
LIGHT  = 'FFF5EE'
GREY   = 'F0F1F5'
GREEN  = '00C853'
RED    = 'FF3D00'
TEAL   = '00897B'
YELLOW = 'F9A825'


# ── Helpers ───────────────────────────────────────────────────

def _fill(color): return PatternFill('solid', fgColor=color)
def _font(bold=False, color=DARK, size=10, italic=False):
    return Font(bold=bold, color=color, size=size, italic=italic, name='Arial')
def _border():
    t = Side(style='thin', color='DDDDDD')
    return Border(left=t, right=t, top=t, bottom=t)
def _align(h='left', v='center', wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)
def _set_col(ws, col, width):
    ws.column_dimensions[get_column_letter(col)].width = width

def fmt_num(v):
    if v is None: return '—'
    if v >= 1e9: return f'{v/1e9:.2f}B'
    if v >= 1e6: return f'{v/1e6:.2f}M'
    if v >= 1e3: return f'{v/1e3:.1f}K'
    return f'{v:,.0f}'

def safe(v): return float(v) if v is not None else 0.0


def apply_filters(request, qs=None):
    """Apply ALL filters including month/year — use for KPI display."""
    if qs is None:
        qs = SiteData.objects.all()
    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    franchise     = request.GET.get('franchise')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')
    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(commercial_district=pta)
    if franchise:     qs = qs.filter(franchise=franchise)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    if month:         qs = qs.filter(month=month)
    if year:          qs = qs.filter(year=year)
    return qs


def apply_dimension_filters(request, qs=None):
    """Apply ONLY non-time filters (region/BU/tech etc) — use as growth base."""
    if qs is None:
        qs = SiteData.objects.all()
    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    franchise     = request.GET.get('franchise')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(commercial_district=pta)
    if franchise:     qs = qs.filter(franchise=franchise)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    return qs


def get_filter_label(request):
    parts = []
    for key, label in {
        'region': 'Region', 'pta_district': 'District',
        'franchise': 'Franchise', 'technology': 'Technology',
        'business_unit': 'BU', 'site_status': 'Status',
        'month': 'Month', 'year': 'Year',
    }.items():
        val = request.GET.get(key)
        if val:
            parts.append(f'{label}: {val}')
    return ' | '.join(parts) if parts else 'All Data'


def get_kpis_and_growth(qs, year_param, growth_base=None):
    """Compute KPIs from qs (with time filters), growth from growth_base (no time filters)."""
    if growth_base is None:
        growth_base = qs
    agg = qs.aggregate(
        total_revenue=Sum('tot_revn_amt'),
        total_activations=Sum('act_90d'),
        total_net_add=Sum('net_add'),
        avg_revenue=Avg('tot_revn_amt'),
        total_churn=Sum('gross_churn'),
        total_hvc=Sum('hvc_base'),
        total_base_90d=Sum('act_90d'),
        total_base_4g=Sum('act_90d_4g'),
        total_base_30d=Sum('act_30d'),
        total_prepaid_digi=Sum('prepaid_dgtl_amount'),
        total_postpaid_digi=Sum('postpaid_dgtl_amount'),
        total_conv_recharge=Sum('conventional_recharge'),
        total_evc=Sum('evc_retailer'),
        total_bvs=Sum('bvs_retailer'),
        total_fca=Sum('fca'),
        total_net_add_sum=Sum('net_add'),
    )

    digi = safe(agg['total_prepaid_digi']) + safe(agg['total_postpaid_digi'])
    conv = safe(agg['total_conv_recharge'])
    act  = safe(agg['total_activations'])
    b90  = safe(agg['total_base_90d'])
    b4g  = safe(agg['total_base_4g'])
    rev  = safe(agg['total_revenue'])

    total_sites = qs.exclude(key__isnull=True).exclude(key='').values('key').distinct().count()

    kpis = {
        'Total Revenue (PKR)':         rev,
        'Total Recharge (PKR)':        digi + conv,
        'Digital Recharge (PKR)':      digi,
        'Conventional Recharge (PKR)': conv,
        'ARPU (PKR)':                  (rev / act) if act else 0,
        '90D Activations':             safe(agg['total_activations']),
        '90D Base':                    b90,
        '4G Base':                     b4g,
        '4G Penetration (%)':          round((b4g / b90 * 100), 2) if b90 else 0,
        '30D Base':                    safe(agg['total_base_30d']),
        'HVC Base':                    safe(agg['total_hvc']),
        'Net Additions':               safe(agg['total_net_add']),
        'Gross Churn':                 safe(agg['total_churn']),
        'FCA (Revival)':               safe(agg['total_fca']),
        'EVC Retailers':               safe(agg['total_evc']),
        'BVS Retailers':               safe(agg['total_bvs']),
        'Avg Revenue / Site (PKR)':    safe(agg['avg_revenue']),
        'Total Sites':                 total_sites,
    }

    # Growth calculation
    growth = {}
    if year_param:
        latest_period = growth_base.filter(year=year_param).order_by('-month').values('year', 'month').first()
    else:
        latest_period = growth_base.order_by('-year', '-month').values('year', 'month').first()

    if latest_period:
        ly = latest_period['year']
        lm = latest_period['month']
        py = ly - 1
        mom_m = lm - 1 if lm > 1 else 12
        mom_y = ly if lm > 1 else py

        agg_kw = dict(
            total_revenue=Sum('tot_revn_amt'),
            total_activations=Sum('act_90d'),
            total_net_add=Sum('net_add'),
            total_churn=Sum('gross_churn'),
            total_hvc=Sum('hvc_base'),
            total_base_90d=Sum('act_90d'),
            total_base_4g=Sum('act_90d_4g'),
            total_base_30d=Sum('act_30d'),
            total_prepaid_digi=Sum('prepaid_dgtl_amount'),
            total_postpaid_digi=Sum('postpaid_dgtl_amount'),
            total_conv_recharge=Sum('conventional_recharge'),
        )

        def _agg(q): return q.aggregate(**agg_kw)
        def gb_filter(**kwargs): return growth_base.filter(**kwargs)
        def _derived(a):
            d = safe(a.get('total_prepaid_digi')) + safe(a.get('total_postpaid_digi'))
            a['total_digi'] = d
            a['total_recharge'] = d + safe(a.get('total_conv_recharge'))
            act_ = safe(a.get('total_activations'))
            b90_ = safe(a.get('total_base_90d'))
            b4g_ = safe(a.get('total_base_4g'))
            a['arpu'] = safe(a.get('total_revenue')) / act_ if act_ else 0
            a['pen4g'] = (b4g_ / b90_ * 100) if b90_ else 0
            return a

        ytd_c = _derived(_agg(gb_filter(year=ly, month__lte=lm)))
        ytd_p = _derived(_agg(gb_filter(year=py, month__lte=lm)))
        yoy_c = _derived(_agg(gb_filter(year=ly, month=lm)))
        yoy_p = _derived(_agg(gb_filter(year=py, month=lm)))
        mom_p = _derived(_agg(gb_filter(year=mom_y, month=mom_m)))

        def pct(c, p): return round(((c - p) / p * 100), 1) if p else (100.0 if c else 0.0)

        metric_map = {
            'Total Revenue (PKR)': 'total_revenue',
            'Total Recharge (PKR)': 'total_recharge',
            'Digital Recharge (PKR)': 'total_digi',
            'Conventional Recharge (PKR)': 'total_conv_recharge',
            'ARPU (PKR)': 'arpu',
            '90D Activations': 'total_activations',
            '90D Base': 'total_base_90d',
            '4G Base': 'total_base_4g',
            '4G Penetration (%)': 'pen4g',
            '30D Base': 'total_base_30d',
            'HVC Base': 'total_hvc',
            'Net Additions': 'total_net_add',
            'Gross Churn': 'total_churn',
        }

        for kpi_name, field in metric_map.items():
            growth[kpi_name] = {
                'ytd_curr': safe(ytd_c.get(field)),
                'ytd_prev': safe(ytd_p.get(field)),
                'ytd_pct':  pct(safe(ytd_c.get(field)), safe(ytd_p.get(field))),
                'yoy_curr': safe(yoy_c.get(field)),
                'yoy_prev': safe(yoy_p.get(field)),
                'yoy_pct':  pct(safe(yoy_c.get(field)), safe(yoy_p.get(field))),
                'mom_curr': safe(yoy_c.get(field)),
                'mom_prev': safe(mom_p.get(field)),
                'mom_pct':  pct(safe(yoy_c.get(field)), safe(mom_p.get(field))),
                'latest_period': f"{lm}/{ly}",
                'prev_period':   f"{mom_m}/{mom_y}",
            }

    return kpis, growth


# ── Excel cell writer helpers ─────────────────────────────────

def write_title_block(ws, title, subtitle, cols=10):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=cols)
    c = ws['A1']
    c.value = title
    c.font = Font(bold=True, size=16, color=WHITE, name='Arial')
    c.fill = _fill(DARK)
    c.alignment = _align('center')
    ws.row_dimensions[1].height = 38

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=cols)
    c2 = ws['A2']
    c2.value = subtitle
    c2.font = Font(size=9, color='666666', name='Arial')
    c2.fill = _fill(GREY)
    c2.alignment = _align('center')
    ws.row_dimensions[2].height = 16
    ws.row_dimensions[3].height = 6


def write_section_header(ws, row, title, color=ORANGE, cols=10, start_col=1):
    if cols > 1:
        ws.merge_cells(start_row=row, start_column=start_col, end_row=row, end_column=start_col + cols - 1)
    c = ws.cell(row=row, column=start_col, value=f'  {title}')
    c.font = Font(bold=True, size=11, color=WHITE, name='Arial')
    c.fill = _fill(color)
    c.alignment = _align('left')
    ws.row_dimensions[row].height = 22
    return row + 1


def write_header_row(ws, row, headers, color='333333', start_col=1):
    for ci, h in enumerate(headers, start_col):
        c = ws.cell(row=row, column=ci, value=h)
        c.font = Font(bold=True, color=WHITE, size=9, name='Arial')
        c.fill = _fill(color)
        c.alignment = _align('center')
        c.border = _border()
    ws.row_dimensions[row].height = 16
    return row + 1


def write_data_row(ws, row, values, start_col=1, num_cols=None):
    bg = LIGHT if row % 2 == 0 else WHITE
    for ci, val in enumerate(values, start_col):
        c = ws.cell(row=row, column=ci, value=val)
        c.fill = _fill(bg)
        c.border = _border()
        c.font = Font(size=9, name='Arial')
        if isinstance(val, float) and val != int(val):
            c.number_format = '#,##0.00'
            c.alignment = _align('right')
        elif isinstance(val, (int, float)):
            c.number_format = '#,##0'
            c.alignment = _align('right')
        else:
            c.alignment = _align('left')
    return row + 1


def write_pct_cell(ws, row, col, value, positive_good=True):
    c = ws.cell(row=row, column=col, value=value / 100 if value is not None else 0)
    c.number_format = '+0.0%;-0.0%;0.0%'
    c.font = Font(bold=True, size=9, name='Arial',
                  color=GREEN if (value or 0) >= 0 else RED)
    c.fill = _fill(LIGHT if row % 2 == 0 else WHITE)
    c.border = _border()
    c.alignment = _align('center')


# ── Excel Export ──────────────────────────────────────────────

@login_required(login_url='login')
def export_excel(request):
    qs = apply_filters(request)
    filter_label = get_filter_label(request)
    year_param = request.GET.get('year')
    generated = datetime.now().strftime('%Y-%m-%d %H:%M')
    growth_base = apply_dimension_filters(request)
    kpis, growth = get_kpis_and_growth(qs, year_param, growth_base)

    wb = Workbook()

    # ══════════════════════════════════════════════════════════
    # SHEET 1 — KPI Summary + Growth
    # ══════════════════════════════════════════════════════════
    ws1 = wb.active
    ws1.title = 'KPI Summary'
    ws1.sheet_view.showGridLines = False

    write_title_block(ws1, '📊 Ufone 5G — Dashboard Export',
                      f'Filters: {filter_label}   |   Generated: {generated}', cols=10)

    row = 4
    row = write_section_header(ws1, row, 'KEY PERFORMANCE INDICATORS', ORANGE, cols=10)
    headers = ['Metric', 'Current Value', 'Formatted', 'YTD Curr', 'YTD Prev', 'YTD %',
               'YOY Curr', 'YOY Prev', 'YOY %', 'MOM %']
    row = write_header_row(ws1, row, headers)

    for metric, value in kpis.items():
        g = growth.get(metric, {})
        bg = LIGHT if row % 2 == 0 else WHITE

        ws1.cell(row=row, column=1, value=metric).font = Font(bold=True, size=9, color=DARK, name='Arial')
        ws1.cell(row=row, column=1).fill = _fill(bg)
        ws1.cell(row=row, column=1).border = _border()

        ws1.cell(row=row, column=2, value=round(value, 2)).number_format = '#,##0.00'
        ws1.cell(row=row, column=2).fill = _fill(bg)
        ws1.cell(row=row, column=2).border = _border()
        ws1.cell(row=row, column=2).alignment = _align('right')
        ws1.cell(row=row, column=2).font = Font(size=9, name='Arial')

        ws1.cell(row=row, column=3, value=fmt_num(value)).font = Font(bold=True, color=ORANGE, size=9, name='Arial')
        ws1.cell(row=row, column=3).fill = _fill(bg)
        ws1.cell(row=row, column=3).border = _border()
        ws1.cell(row=row, column=3).alignment = _align('center')

        if g:
            for ci, key in enumerate(['ytd_curr', 'ytd_prev'], 4):
                c = ws1.cell(row=row, column=ci, value=round(g[key], 2))
                c.number_format = '#,##0.00'
                c.fill = _fill(bg)
                c.border = _border()
                c.alignment = _align('right')
                c.font = Font(size=9, name='Arial')

            write_pct_cell(ws1, row, 6, g.get('ytd_pct'))

            for ci, key in enumerate(['yoy_curr', 'yoy_prev'], 7):
                c = ws1.cell(row=row, column=ci, value=round(g[key], 2))
                c.number_format = '#,##0.00'
                c.fill = _fill(bg)
                c.border = _border()
                c.alignment = _align('right')
                c.font = Font(size=9, name='Arial')

            write_pct_cell(ws1, row, 9, g.get('yoy_pct'))
            write_pct_cell(ws1, row, 10, g.get('mom_pct'))
        else:
            for ci in range(4, 11):
                c = ws1.cell(row=row, column=ci, value='N/A')
                c.fill = _fill(bg)
                c.border = _border()
                c.font = Font(size=9, color='999999', name='Arial')
                c.alignment = _align('center')

        row += 1

    # Period info
    if growth:
        sample = next(iter(growth.values()), {})
        if sample:
            row += 1
            ws1.cell(row=row, column=1, value=f"Latest Period: {sample.get('latest_period','—')}   |   MOM Comparison vs: {sample.get('prev_period','—')}").font = Font(italic=True, size=8, color='888888', name='Arial')

    col_widths = [30, 16, 12, 14, 14, 9, 14, 14, 9, 9]
    for i, w in enumerate(col_widths, 1):
        _set_col(ws1, i, w)

    ws1.freeze_panes = 'A5'

    # ══════════════════════════════════════════════════════════
    # SHEET 2 — Chart Data (all charts as tables)
    # ══════════════════════════════════════════════════════════
    ws2 = wb.create_sheet('Chart Data')
    ws2.sheet_view.showGridLines = False
    write_title_block(ws2, '📈 Chart Data — All Dashboard Charts',
                      f'Filters: {filter_label}   |   Generated: {generated}', cols=6)

    row = 4

    def write_chart_table(ws, start_row, title, headers, data_rows, color=ORANGE):
        r = write_section_header(ws, start_row, title, color, cols=len(headers))
        r = write_header_row(ws, r, headers)
        for d in data_rows:
            r = write_data_row(ws, r, d)
        return r + 1

    # Revenue by Region
    rev_region = list(qs.exclude(region__isnull=True).values('region')
                      .annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue')[:15])
    row = write_chart_table(ws2, row, 'Revenue by Region (Top 15)',
                            ['Region', 'Revenue (PKR)', 'Formatted'],
                            [(r['region'], round(safe(r['revenue']), 2), fmt_num(safe(r['revenue'])))
                             for r in rev_region], ORANGE)

    # Activations by Technology
    act_tech = list(qs.exclude(technology__isnull=True).values('technology')
                    .annotate(activations=Sum('act_90d'), base4g=Sum('act_90d_4g'))
                    .order_by('-activations'))
    row = write_chart_table(ws2, row, 'Activations & 4G Base by Technology',
                            ['Technology', '90D Activations', '4G Base'],
                            [(r['technology'], r['activations'] or 0, r['base4g'] or 0)
                             for r in act_tech], PURPLE)

    # Revenue by BU
    rev_bu = list(qs.exclude(business_unit__isnull=True).values('business_unit')
                  .annotate(revenue=Sum('tot_revn_amt'), act=Sum('act_90d'),
                             churn=Sum('gross_churn'), netadd=Sum('net_add'))
                  .order_by('-revenue'))
    row = write_chart_table(ws2, row, 'KPIs by Business Unit',
                            ['Business Unit', 'Revenue (PKR)', '90D Act', 'Gross Churn', 'Net Add'],
                            [(r['business_unit'], round(safe(r['revenue']), 2),
                              r['act'] or 0, r['churn'] or 0, r['netadd'] or 0)
                             for r in rev_bu], ORANGE)

    # Site Status
    status_data = list(qs.exclude(site_status__isnull=True).values('site_status')
                       .annotate(count=Count('key', distinct=True)).order_by('-count'))
    row = write_chart_table(ws2, row, 'Site Count by Status',
                            ['Status', 'Site Count'],
                            [(r['site_status'], r['count']) for r in status_data], TEAL)

    # Monthly trend
    monthly = list(qs.exclude(year__isnull=True).values('year', 'month')
                   .annotate(
                       net_add=Sum('net_add'),
                       churn=Sum('gross_churn'),
                       fca=Sum('fca'),
                       revenue=Sum('tot_revn_amt'),
                       activations=Sum('act_90d'),
                       base_90d=Sum('act_90d'),
                       base_4g=Sum('act_90d_4g'),
                   ).order_by('year', 'month'))
    row = write_chart_table(ws2, row, 'Monthly Trend (Net Add, Churn, FCA, Revenue)',
                            ['Year', 'Month', 'Net Additions', 'Gross Churn', 'FCA Revival',
                             'Revenue (PKR)', '90D Activations', '4G Base'],
                            [(r['year'], r['month'], r['net_add'] or 0, r['churn'] or 0,
                              round(safe(r['fca']), 2), round(safe(r['revenue']), 2),
                              r['activations'] or 0, r['base_4g'] or 0)
                             for r in monthly], RED)

    # Recharge breakdown
    recharge = qs.aggregate(
        prepaid=Sum('prepaid_dgtl_amount'),
        postpaid=Sum('postpaid_dgtl_amount'),
        conventional=Sum('conventional_recharge'),
    )
    digi_total = safe(recharge['prepaid']) + safe(recharge['postpaid'])
    total_rch = digi_total + safe(recharge['conventional'])
    row = write_chart_table(ws2, row, 'Recharge Channel Breakdown',
                            ['Channel', 'Amount (PKR)', 'Formatted', 'Share (%)'],
                            [
                                ('Prepaid Digital', round(safe(recharge['prepaid']), 2),
                                 fmt_num(safe(recharge['prepaid'])),
                                 round(safe(recharge['prepaid']) / total_rch * 100, 1) if total_rch else 0),
                                ('Postpaid Digital', round(safe(recharge['postpaid']), 2),
                                 fmt_num(safe(recharge['postpaid'])),
                                 round(safe(recharge['postpaid']) / total_rch * 100, 1) if total_rch else 0),
                                ('Conventional', round(safe(recharge['conventional']), 2),
                                 fmt_num(safe(recharge['conventional'])),
                                 round(safe(recharge['conventional']) / total_rch * 100, 1) if total_rch else 0),
                                ('Total', round(total_rch, 2), fmt_num(total_rch), 100.0),
                            ], YELLOW)

    # Traffic by Region
    traffic = list(qs.exclude(region__isnull=True).values('region')
                   .annotate(outgoing=Sum('minutes_outgoing'), incoming=Sum('minutes_incoming'))
                   .order_by('-outgoing')[:12])
    row = write_chart_table(ws2, row, 'Voice Traffic by Region (Top 12)',
                            ['Region', 'Outgoing Mins', 'Incoming Mins', 'Total Mins'],
                            [(r['region'], round(safe(r['outgoing']), 0), round(safe(r['incoming']), 0),
                              round(safe(r['outgoing']) + safe(r['incoming']), 0))
                             for r in traffic], PURPLE)

    # Data Volume by Technology
    data_vol = list(qs.exclude(technology__isnull=True).values('technology')
                    .annotate(volume=Sum('volume_gbs'), vol4g=Sum('data_ntwrk_vol_4g'))
                    .order_by('-volume'))
    row = write_chart_table(ws2, row, 'Data Volume by Technology (GBs)',
                            ['Technology', 'Total GBs', '4G GBs'],
                            [(r['technology'], round(safe(r['volume']), 2), round(safe(r['vol4g']), 2))
                             for r in data_vol], TEAL)

    # EVC/BVS by Region
    retailer = list(qs.exclude(region__isnull=True).values('region')
                    .annotate(evc=Sum('evc_retailer'), bvs=Sum('bvs_retailer'))
                    .order_by('-evc'))
    row = write_chart_table(ws2, row, 'EVC & BVS Retailers by Region',
                            ['Region', 'EVC Retailers', 'BVS Retailers'],
                            [(r['region'], r['evc'] or 0, r['bvs'] or 0) for r in retailer], ORANGE)

    for col in range(1, 9):
        _set_col(ws2, col, 22)
    ws2.freeze_panes = 'A5'

    # ══════════════════════════════════════════════════════════
    # SHEET 3 — Growth Detail
    # ══════════════════════════════════════════════════════════
    ws3 = wb.create_sheet('Growth Detail')
    ws3.sheet_view.showGridLines = False
    write_title_block(ws3, '📊 Growth Detail — YTD / YOY / MOM',
                      f'Filters: {filter_label}   |   Generated: {generated}', cols=10)

    row = 4
    row = write_section_header(ws3, row, 'GROWTH METRICS — YTD / YEAR-ON-YEAR / MONTH-ON-MONTH', PURPLE, cols=10)
    headers_g = ['Metric', 'YTD Current', 'YTD Previous', 'YTD %',
                 'YOY Current', 'YOY Previous', 'YOY %',
                 'MOM Current', 'MOM Previous', 'MOM %']
    row = write_header_row(ws3, row, headers_g)

    for metric, g in growth.items():
        bg = LIGHT if row % 2 == 0 else WHITE
        ws3.cell(row=row, column=1, value=metric).font = Font(bold=True, size=9, color=DARK, name='Arial')
        ws3.cell(row=row, column=1).fill = _fill(bg)
        ws3.cell(row=row, column=1).border = _border()

        for ci, key in enumerate(['ytd_curr', 'ytd_prev'], 2):
            c = ws3.cell(row=row, column=ci, value=round(g.get(key, 0), 2))
            c.number_format = '#,##0.00'
            c.fill = _fill(bg)
            c.border = _border()
            c.alignment = _align('right')
            c.font = Font(size=9, name='Arial')

        write_pct_cell(ws3, row, 4, g.get('ytd_pct', 0))

        for ci, key in enumerate(['yoy_curr', 'yoy_prev'], 5):
            c = ws3.cell(row=row, column=ci, value=round(g.get(key, 0), 2))
            c.number_format = '#,##0.00'
            c.fill = _fill(bg)
            c.border = _border()
            c.alignment = _align('right')
            c.font = Font(size=9, name='Arial')

        write_pct_cell(ws3, row, 7, g.get('yoy_pct', 0))

        for ci, key in enumerate(['mom_curr', 'mom_prev'], 8):
            c = ws3.cell(row=row, column=ci, value=round(g.get(key, 0), 2))
            c.number_format = '#,##0.00'
            c.fill = _fill(bg)
            c.border = _border()
            c.alignment = _align('right')
            c.font = Font(size=9, name='Arial')

        write_pct_cell(ws3, row, 10, g.get('mom_pct', 0))
        row += 1

    col_widths_g = [30, 14, 14, 9, 14, 14, 9, 14, 14, 9]
    for i, w in enumerate(col_widths_g, 1):
        _set_col(ws3, i, w)
    ws3.freeze_panes = 'A6'

    # ══════════════════════════════════════════════════════════
    # SHEET 4 — Raw Site Data (ALL columns, ALL rows)
    # ══════════════════════════════════════════════════════════
    ws4 = wb.create_sheet('Raw Site Data')
    ws4.sheet_view.showGridLines = False

    raw_headers = [
        'Key', 'Region', 'District', 'Franchise', 'Business Unit',
        'Technology', 'Site Status', 'ARM', 'Year', 'Month',
        'Latitude', 'Longitude',
        'Revenue (PKR)', '90D Activations', '4G Activations', '30D Activations',
        'HVC Base', 'Net Additions', 'Gross Churn', 'FCA',
        'Avg Daily Active', 'Recharger Base',
        'Prepaid Digital (PKR)', 'Postpaid Digital (PKR)', 'Conventional Recharge (PKR)',
        'EVC Retailers', 'BVS Retailers',
        'Outgoing Mins', 'Incoming Mins', 'Volume GBs', '4G Volume GBs',
        'M0 Revenue (PKR)', 'MNP FCA', 'Handset 4G',
    ]

    write_title_block(ws4,
                      f'🗃️ Complete Site Data — {filter_label}',
                      f'Generated: {generated}   |   All available fields', cols=len(raw_headers))

    row = 4
    for ci, h in enumerate(raw_headers, 1):
        c = ws4.cell(row=row, column=ci, value=h)
        c.font = Font(bold=True, color=WHITE, size=8, name='Arial')
        c.fill = _fill(ORANGE)
        c.alignment = _align('center')
        c.border = _border()
    ws4.row_dimensions[row].height = 16
    row += 1

    raw_qs = qs.values(
        'key', 'region', 'commercial_district', 'franchise', 'business_unit',
        'technology', 'site_status', 'arm', 'year', 'month',
        'latitude', 'longitude',
        'tot_revn_amt', 'act_90d', 'act_90d_4g', 'act_30d',
        'hvc_base', 'net_add', 'gross_churn', 'fca',
        'avg_dly_act', 'act_recharger',
        'prepaid_dgtl_amount', 'postpaid_dgtl_amount', 'conventional_recharge',
        'evc_retailer', 'bvs_retailer',
        'minutes_outgoing', 'minutes_incoming', 'volume_gbs', 'data_ntwrk_vol_4g',
        'm0_revn', 'mnp_fca', 'handset_4g',
    ).order_by('region', 'business_unit', 'key', 'year', 'month')

    for ri, r in enumerate(raw_qs, row):
        bg = LIGHT if ri % 2 == 0 else WHITE
        vals = [
            r['key'], r['region'], r['commercial_district'], r['franchise'], r['business_unit'],
            r['technology'], r['site_status'], r['arm'], r['year'], r['month'],
            r['latitude'], r['longitude'],
            round(safe(r['tot_revn_amt']), 2), r['act_90d'] or 0, r['act_90d_4g'] or 0, r['act_30d'] or 0,
            r['hvc_base'] or 0, r['net_add'] or 0, r['gross_churn'] or 0, round(safe(r['fca']), 2),
            round(safe(r['avg_dly_act']), 2), r['act_recharger'] or 0,
            round(safe(r['prepaid_dgtl_amount']), 2), round(safe(r['postpaid_dgtl_amount']), 2),
            round(safe(r['conventional_recharge']), 2),
            r['evc_retailer'] or 0, r['bvs_retailer'] or 0,
            round(safe(r['minutes_outgoing']), 2), round(safe(r['minutes_incoming']), 2),
            round(safe(r['volume_gbs']), 2), round(safe(r['data_ntwrk_vol_4g']), 2),
            round(safe(r['m0_revn']), 2), r['mnp_fca'] or 0, r['handset_4g'] or 0,
        ]
        for ci, val in enumerate(vals, 1):
            c = ws4.cell(row=ri, column=ci, value=val)
            c.fill = _fill(bg)
            c.border = _border()
            c.font = Font(size=8, name='Arial')
            if isinstance(val, float):
                c.number_format = '#,##0.00'
                c.alignment = _align('right')
            elif isinstance(val, int) and ci > 8:
                c.number_format = '#,##0'
                c.alignment = _align('right')

    raw_col_widths = [
        14, 14, 16, 14, 16, 12, 12, 20, 7, 7,
        10, 10,
        14, 10, 10, 10,
        10, 10, 10, 10,
        12, 12,
        14, 14, 16,
        10, 10,
        12, 12, 12, 12,
        14, 10, 10,
    ]
    for i, w in enumerate(raw_col_widths, 1):
        _set_col(ws4, i, w)
    ws4.freeze_panes = 'A5'

    # ── Stream ─────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f'dashboard_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response = HttpResponse(
        buf,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── PDF Export ────────────────────────────────────────────────

@login_required(login_url='login')
def export_pdf(request):
    qs = apply_filters(request)
    filter_label = get_filter_label(request)
    year_param = request.GET.get('year')
    generated = datetime.now().strftime('%Y-%m-%d %H:%M')
    growth_base = apply_dimension_filters(request)
    kpis, growth = get_kpis_and_growth(qs, year_param, growth_base)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    orange = colors.HexColor('#F58220')
    dark   = colors.HexColor('#1A1235')
    purple = colors.HexColor('#AB1DFE')
    light  = colors.HexColor('#FFF5EE')
    grey   = colors.HexColor('#F0F1F5')
    green  = colors.HexColor('#00C853')
    red    = colors.HexColor('#FF3D00')
    white  = colors.white
    teal   = colors.HexColor('#00897B')

    def fmt_pct(v):
        if v is None: return '—'
        sign = '+' if v >= 0 else ''
        return f'{sign}{v:.1f}%'

    def pdf_section(title, color=orange):
        style = ParagraphStyle('sh', fontSize=11, textColor=white,
                               fontName='Helvetica-Bold')
        t = Table([[Paragraph(f'  {title}', style)]], colWidths=[doc.width])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0),(-1,-1), color),
            ('TOPPADDING', (0,0),(-1,-1), 5),
            ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ]))
        return t

    def pdf_table(headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [doc.width / len(headers)] * len(headers)
        hstyle = ParagraphStyle('th', fontSize=7, textColor=white,
                                fontName='Helvetica-Bold', alignment=1)
        dstyle = ParagraphStyle('td', fontSize=7, fontName='Helvetica')
        data = [[Paragraph(str(h), hstyle) for h in headers]]
        for ri, row in enumerate(rows):
            data.append([Paragraph(str(v) if not isinstance(v, float) else f'{v:,.2f}', dstyle)
                         for v in row])
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0),(-1,0), colors.HexColor('#333333')),
            ('ROWBACKGROUNDS', (0,1),(-1,-1), [light, white]),
            ('BOX', (0,0),(-1,-1), 0.5, colors.HexColor('#DDDDDD')),
            ('INNERGRID', (0,0),(-1,-1), 0.3, colors.HexColor('#EEEEEE')),
            ('TOPPADDING', (0,0),(-1,-1), 3),
            ('BOTTOMPADDING', (0,0),(-1,-1), 3),
            ('LEFTPADDING', (0,0),(-1,-1), 5),
            ('RIGHTPADDING', (0,0),(-1,-1), 5),
        ]))
        return t

    story = []

    # Title
    t = Table([[Paragraph('📊 Ufone 5G — Dashboard Export Report',
                           ParagraphStyle('t', fontSize=18, textColor=white,
                                          fontName='Helvetica-Bold', alignment=1))]],
              colWidths=[doc.width])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),dark),
                            ('TOPPADDING',(0,0),(-1,-1),12),
                            ('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    story.append(t)
    story.append(Spacer(1, 0.2*cm))

    meta = Table([[Paragraph(f'Filters: {filter_label}',
                              ParagraphStyle('m', fontSize=8, textColor=colors.HexColor('#666666'),
                                             fontName='Helvetica', alignment=1)),
                   Paragraph(f'Generated: {generated}',
                              ParagraphStyle('m2', fontSize=8, textColor=colors.HexColor('#666666'),
                                             fontName='Helvetica', alignment=2))]],
                 colWidths=[doc.width*0.6, doc.width*0.4])
    meta.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),grey),
                               ('TOPPADDING',(0,0),(-1,-1),5),
                               ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(meta)
    story.append(Spacer(1, 0.4*cm))

    # KPI grid
    story.append(pdf_section('KEY PERFORMANCE INDICATORS'))
    story.append(Spacer(1, 0.1*cm))
    kpi_items = list(kpis.items())
    kpi_rows = []
    for i in range(0, len(kpi_items), 4):
        chunk = kpi_items[i:i+4]
        labels = [Paragraph(f'<font size=7 color="#666666"><b>{m}</b></font>', ParagraphStyle('kl', fontName='Helvetica-Bold', alignment=1)) for m, _ in chunk]
        values = [Paragraph(f'<font size=12 color="#F58220"><b>{fmt_num(v)}</b></font>', ParagraphStyle('kv', fontName='Helvetica-Bold', alignment=1)) for _, v in chunk]
        while len(labels) < 4:
            labels.append(Paragraph('', ParagraphStyle('e', fontName='Helvetica')))
            values.append(Paragraph('', ParagraphStyle('e', fontName='Helvetica')))
        kpi_rows.append(labels)
        kpi_rows.append(values)

    kt = Table(kpi_rows, colWidths=[doc.width/4]*4)
    kt.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0,0),(-1,-1), [light, white]),
        ('BOX', (0,0),(-1,-1), 0.5, colors.HexColor('#DDDDDD')),
        ('INNERGRID', (0,0),(-1,-1), 0.3, colors.HexColor('#EEEEEE')),
        ('TOPPADDING', (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
    ]))
    story.append(kt)
    story.append(PageBreak())

    # Growth table
    if growth:
        story.append(pdf_section('GROWTH — YTD / YOY / MOM', purple))
        story.append(Spacer(1, 0.1*cm))
        g_headers = ['Metric', 'YTD Curr', 'YTD Prev', 'YTD %', 'YOY Curr', 'YOY Prev', 'YOY %', 'MOM %']
        g_rows = [(m, fmt_num(g['ytd_curr']), fmt_num(g['ytd_prev']), fmt_pct(g['ytd_pct']),
                   fmt_num(g['yoy_curr']), fmt_num(g['yoy_prev']), fmt_pct(g['yoy_pct']),
                   fmt_pct(g['mom_pct'])) for m, g in growth.items()]
        cw = [doc.width*0.22] + [doc.width*0.11]*7
        story.append(pdf_table(g_headers, g_rows, cw))
        story.append(Spacer(1, 0.3*cm))

    # Chart tables
    def add_pdf_chart(title, headers, rows, color=orange, col_widths=None):
        story.append(pdf_section(title, color))
        story.append(Spacer(1, 0.1*cm))
        story.append(pdf_table(headers, rows, col_widths))
        story.append(Spacer(1, 0.3*cm))

    rev_region = list(qs.exclude(region__isnull=True).values('region')
                      .annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue')[:10])
    add_pdf_chart('Revenue by Region (Top 10)', ['Region', 'Revenue (PKR)', 'Formatted'],
                  [(r['region'], round(safe(r['revenue']), 2), fmt_num(safe(r['revenue'])))
                   for r in rev_region])

    act_tech = list(qs.exclude(technology__isnull=True).values('technology')
                    .annotate(activations=Sum('act_90d'), base4g=Sum('act_90d_4g'))
                    .order_by('-activations'))
    add_pdf_chart('Activations by Technology', ['Technology', '90D Activations', '4G Base'],
                  [(r['technology'], r['activations'] or 0, r['base4g'] or 0)
                   for r in act_tech], purple)

    rev_bu = list(qs.exclude(business_unit__isnull=True).values('business_unit')
                  .annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue'))
    add_pdf_chart('Revenue by Business Unit', ['Business Unit', 'Revenue (PKR)'],
                  [(r['business_unit'], round(safe(r['revenue']), 2)) for r in rev_bu])

    recharge = qs.aggregate(prepaid=Sum('prepaid_dgtl_amount'),
                            postpaid=Sum('postpaid_dgtl_amount'),
                            conventional=Sum('conventional_recharge'))
    add_pdf_chart('Recharge Breakdown', ['Channel', 'Amount (PKR)', 'Formatted'],
                  [('Prepaid Digital', round(safe(recharge['prepaid']), 2), fmt_num(safe(recharge['prepaid']))),
                   ('Postpaid Digital', round(safe(recharge['postpaid']), 2), fmt_num(safe(recharge['postpaid']))),
                   ('Conventional', round(safe(recharge['conventional']), 2), fmt_num(safe(recharge['conventional'])))],
                  colors.HexColor('#F9A825'))

    status_data = list(qs.exclude(site_status__isnull=True).values('site_status')
                       .annotate(count=Count('key', distinct=True)).order_by('-count'))
    add_pdf_chart('Site Count by Status', ['Status', 'Site Count'],
                  [(r['site_status'], r['count']) for r in status_data], teal)

    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#999999'))
        canvas.drawString(1.5*cm, 0.8*cm, f'Ufone 5G Dashboard  |  {filter_label}  |  {generated}')
        canvas.drawRightString(doc.pagesize[0]-1.5*cm, 0.8*cm, f'Page {doc.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    buf.seek(0)
    filename = f'dashboard_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response