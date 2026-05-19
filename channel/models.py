"""
ChannelDaily — one row per (date, franchise_id).
Mirrors the columns from the channel data Excel file.

Field grouping (for sanity):
  1. Dimensions:           date, franchise_id, city, region, business_unit, status
  2. Target vs Achievement (paired): FCA, 4G, MNP, MBB, M0 Revenue, QOS, Bundle, HVC, Loading
  3. Loading details:       evc_uload, vouchers, total_site_loading, etc.
  4. CM tiers (EVC + 964):  platinum / gold / silver levels
  5. Retailer activity:     EVC retailer, daily active EVC, served, transactions
  6. Disowned CNICs block:  CM Disown, Female CNIC Disowned, etc.
  7. SR & per-site:         WIC SR, Retail SR, Total SR, Cell Sites Count
  8. Per-site / M0 breakdown (trailing block): FCA, MNP, MBB, etc. + M0 Rev breakdown
"""

from django.db import models


class ChannelDaily(models.Model):
    # ── 1. Dimensions ─────────────────────────────────────────
    date          = models.DateField(db_index=True)
    franchise_id  = models.CharField(max_length=32, db_index=True)
    city          = models.CharField(max_length=64, blank=True)
    region        = models.CharField(max_length=32, db_index=True)
    business_unit = models.CharField(max_length=32, db_index=True)
    arm           = models.CharField(max_length=200, null=True, blank=True, db_index=True)
    status        = models.CharField(max_length=16, blank=True)

    # ── 2. Targets vs Achievements ────────────────────────────
    fca_target          = models.IntegerField(default=0)   # FCA Targets
    fca_ach             = models.IntegerField(default=0)   # FCA Ach
    g4_target           = models.IntegerField(default=0)   # 4G Targets
    g4_ach              = models.IntegerField(default=0)   # 4G Ach
    mnp_target          = models.IntegerField(default=0)   # MNP Target
    mnp_ach             = models.IntegerField(default=0)   # MNP Ach
    loading_target      = models.BigIntegerField(default=0)# Loading Target
    loading_ach         = models.BigIntegerField(default=0)# Loading Ach
    mbb_target          = models.IntegerField(default=0)   # MBB Targets
    mbb_ach             = models.IntegerField(default=0)   # MBB Ach
    m0_revenue_target   = models.BigIntegerField(default=0)# M0 Revenue Targets
    m0_revenue_ach      = models.BigIntegerField(default=0)# M0 Revenue Ach
    qos_target          = models.IntegerField(default=0)   # QOS Targets
    qos_ach             = models.IntegerField(default=0)   # QOS Ach
    bundle_target       = models.IntegerField(default=0)   # Bundle Target
    bundle_ach          = models.IntegerField(default=0)   # Bundle Ach
    hvc_target          = models.IntegerField(default=0)   # HVC TGT
    hvc_ach             = models.IntegerField(default=0)   # HVC Ach

    # ── 3. Loading detail ─────────────────────────────────────
    evc_uload                  = models.BigIntegerField(default=0)   # EVC Uload
    vouchers                   = models.BigIntegerField(default=0)   # Vouchers
    total_site_loading         = models.BigIntegerField(default=0)   # Total Site Loading
    loading_ach_site_conv      = models.BigIntegerField(default=0)   # Loading Ach Site Conv. Cell site loading
    issuance_ach               = models.BigIntegerField(default=0)   # Issuance Ach
    uload_recharge_ach         = models.BigIntegerField(default=0)   # Uload Recharge Ach
    data_sim_fca               = models.IntegerField(default=0)      # Data SIM FCA
    evc_active_base            = models.IntegerField(default=0)      # EVC Active Base
    recharge_only              = models.IntegerField(default=0)      # Recharge Only
    female_fca_count           = models.IntegerField(default=0)      # Female FCA Count
    dormancy_count             = models.IntegerField(default=0)      # Dormancy Count

    # ── 4. CM Disown block ────────────────────────────────────
    cm_ga                                  = models.IntegerField(default=0)   # CM GA
    cm_disown                              = models.IntegerField(default=0)   # CM Disown
    female_cnic_disowned                   = models.IntegerField(default=0)   # Female CNIC Disowned
    new_sim_sale_disowned_cnics            = models.IntegerField(default=0)   # New SIM Sale (Disowned CNICs)
    fca_within_90d_disowned                = models.IntegerField(default=0)   # FCA Date within 90 Days Disowned
    fca_within_90d_disown_new_activation   = models.IntegerField(default=0)   # FCA Date within 90 Days (Disown & new Activation)
    active_90d_base_disown                 = models.IntegerField(default=0)   # 90 Days Active Base Disown
    active_90d_base_disown_new_activation  = models.IntegerField(default=0)   # 90 Days Active Base (Disown & new Activation)

    # ── 5. NPR & Active SO ────────────────────────────────────
    npr                       = models.IntegerField(default=0)   # NPR
    active_so_daily_avg       = models.IntegerField(default=0)   # Active SO (Daily Ave.)
    active_so_npr             = models.IntegerField(default=0)   # Active SO NPR
    lm_active_evc             = models.IntegerField(default=0)   # LM Active EVC
    mtd_served                = models.IntegerField(default=0)   # MTD Served
    avg_served                = models.IntegerField(default=0)   # Avg Served

    # ── 6. CM EVC Active tiers ────────────────────────────────
    cm_evc_active_platinum    = models.IntegerField(default=0)   # CM EVC Active (Platinum)
    cm_evc_active_gold        = models.IntegerField(default=0)   # CM EVC Active (Gold)
    cm_evc_active_silver      = models.IntegerField(default=0)   # CM EVC Active (Silver)
    cm_evc_active             = models.IntegerField(default=0)   # CM EVC Active

    # ── 7. CM 964 Active tiers ────────────────────────────────
    cm_964_active_platinum    = models.IntegerField(default=0)   # CM 964 Active (Platinum)
    cm_964_active_gold        = models.IntegerField(default=0)   # CM 964 Active (Gold)
    cm_964_active_silver      = models.IntegerField(default=0)   # CM 964 Active (Silver)
    cm_964_active             = models.IntegerField(default=0)   # CM 964 Active

    # ── 8. Bundles (duplicate columns from source) ────────────
    total_bundles_activated     = models.IntegerField(default=0) # Total Bundles Activated (first)
    daily_avg_bundle_subs       = models.IntegerField(default=0) # Daily Avg. Bundle Subs (first)
    cc                          = models.IntegerField(default=0) # cc (TODO: rename when meaning clarified)
    total_bundles_activated_2   = models.IntegerField(default=0) # Total Bundles Activated (second)
    daily_avg_bundle_subs_2     = models.IntegerField(default=0) # Daily Avg. Bundle Subs (second)

    # ── 9. CMTD & Retailer Transactions ───────────────────────
    evc_cmtd_active           = models.IntegerField(default=0)   # EVC CMTD Active
    cm_daily_active           = models.IntegerField(default=0)   # CM Daily Active
    active_964_cmtd           = models.IntegerField(default=0)   # 964 Active CMTD
    retailer_trans_count_1    = models.IntegerField(default=0)   # Retailer Trans Count = 1
    retailer_trans_count_2    = models.IntegerField(default=0)   # Retailer Trans Count = 2
    trans_ge_3_pct            = models.FloatField(default=0)     # Trans >=3%

    # ── 10. PBC / ZR / Retailer ───────────────────────────────
    pbc                       = models.IntegerField(default=0)   # PBC
    zr_fca                    = models.IntegerField(default=0)   # ZR FCA
    zr                        = models.IntegerField(default=0)   # ZR
    evc_retailer              = models.IntegerField(default=0)   # EVC Retailer
    daily_active_evc          = models.IntegerField(default=0)   # Daily Active EVC
    daily_active_served       = models.IntegerField(default=0)   # Daily Active Served

    # ── 11. SR (Sales Returns / Service Region) ───────────────
    wic_sr                    = models.FloatField(default=0)     # WIC SR
    retail_sr                 = models.FloatField(default=0)     # Retail SR
    total_sr                  = models.FloatField(default=0)     # Total SR

    # ── 12. Per-Site block ────────────────────────────────────
    cell_sites_count          = models.IntegerField(default=0)   # Cell Sites Count
    fca_per_site              = models.FloatField(default=0)     # FCA (per-site block first)
    fca_per_site_value        = models.FloatField(default=0)     # Per Site FCA
    sd_bundle                 = models.IntegerField(default=0)   # SD Bundle

    # ── 13. M0 Acquisition Source Breakdown ───────────────────
    # The trailing FCA/MNP/MBB/Data Sim/GA/HVC + M0 Rev breakdown
    fca_m0                    = models.IntegerField(default=0)   # FCA (M0 block)
    mnp_m0                    = models.IntegerField(default=0)   # MNP
    mbb_m0                    = models.IntegerField(default=0)   # MBB
    data_sim_m0               = models.IntegerField(default=0)   # Data Sim
    ga_m0                     = models.IntegerField(default=0)   # GA
    hvc_m0                    = models.IntegerField(default=0)   # HVC
    m0_rev_fca                = models.BigIntegerField(default=0)# M0 Rev FCA
    m0_rev_mnp                = models.BigIntegerField(default=0)# M0 Rev MNP
    m0_rev_mbb                = models.BigIntegerField(default=0)# M0 Rev MBB
    m0_rev_data_sim           = models.BigIntegerField(default=0)# M0 Rev Data Sim
    m0_rev_ga                 = models.BigIntegerField(default=0)# M0 Rev GA
    m0_hvc_rev                = models.BigIntegerField(default=0)# M0 HVC Rev

    class Meta:
        indexes = [
            models.Index(fields=['region', 'business_unit', 'date']),
            models.Index(fields=['region', 'business_unit', 'arm']),
            models.Index(fields=['franchise_id', 'date']),
            models.Index(fields=['date', 'region']),
        ]
        unique_together = ('date', 'franchise_id')
        verbose_name = 'Channel Daily Record'
        verbose_name_plural = 'Channel Daily Records'

    def __str__(self):
        return f'{self.date} · {self.franchise_id} · {self.business_unit}'

    # Convenience properties (computed on the fly, not stored)
    @property
    def fca_attainment(self):
        return (self.fca_ach / self.fca_target * 100) if self.fca_target else 0

    @property
    def loading_attainment(self):
        return (self.loading_ach / self.loading_target * 100) if self.loading_target else 0

    @property
    def m0_revenue_attainment(self):
        return (self.m0_revenue_ach / self.m0_revenue_target * 100) if self.m0_revenue_target else 0