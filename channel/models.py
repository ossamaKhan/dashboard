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
    fca_target          = models.IntegerField(default=0)
    fca_ach             = models.IntegerField(default=0)
    g4_target           = models.IntegerField(default=0)
    g4_ach              = models.IntegerField(default=0)
    mnp_target          = models.IntegerField(default=0)
    mnp_ach             = models.IntegerField(default=0)
    loading_target      = models.BigIntegerField(default=0)
    loading_ach         = models.BigIntegerField(default=0)
    mbb_target          = models.IntegerField(default=0)
    mbb_ach             = models.IntegerField(default=0)
    m0_revenue_target   = models.BigIntegerField(default=0)
    m0_revenue_ach      = models.BigIntegerField(default=0)
    qos_target          = models.IntegerField(default=0)
    qos_ach             = models.IntegerField(default=0)
    bundle_target       = models.IntegerField(default=0)
    bundle_ach          = models.IntegerField(default=0)
    hvc_target          = models.IntegerField(default=0)
    hvc_ach             = models.IntegerField(default=0)

    # ── 3. Loading detail ─────────────────────────────────────
    evc_uload                  = models.BigIntegerField(default=0)
    vouchers                   = models.BigIntegerField(default=0)
    total_site_loading         = models.BigIntegerField(default=0)
    loading_ach_site_conv      = models.BigIntegerField(default=0)
    issuance_ach               = models.BigIntegerField(default=0)
    uload_recharge_ach         = models.BigIntegerField(default=0)
    data_sim_fca               = models.IntegerField(default=0)
    evc_active_base            = models.IntegerField(default=0)
    recharge_only              = models.IntegerField(default=0)
    female_fca_count           = models.IntegerField(default=0)
    dormancy_count             = models.IntegerField(default=0)

    # ── 4. CM Disown block ────────────────────────────────────
    cm_ga                                  = models.IntegerField(default=0)
    cm_disown                              = models.IntegerField(default=0)
    female_cnic_disowned                   = models.IntegerField(default=0)
    new_sim_sale_disowned_cnics            = models.IntegerField(default=0)
    fca_within_90d_disowned                = models.IntegerField(default=0)
    fca_within_90d_disown_new_activation   = models.IntegerField(default=0)
    active_90d_base_disown                 = models.IntegerField(default=0)
    active_90d_base_disown_new_activation  = models.IntegerField(default=0)

    # ── 5. NPR & Active SO ────────────────────────────────────
    npr                       = models.IntegerField(default=0)
    active_so_daily_avg       = models.IntegerField(default=0)
    active_so_npr             = models.IntegerField(default=0)
    lm_active_evc             = models.IntegerField(default=0)
    mtd_served                = models.IntegerField(default=0)
    avg_served                = models.IntegerField(default=0)

    # ── 6. CM EVC Active tiers ────────────────────────────────
    cm_evc_active_platinum    = models.IntegerField(default=0)
    cm_evc_active_gold        = models.IntegerField(default=0)
    cm_evc_active_silver      = models.IntegerField(default=0)
    cm_evc_active             = models.IntegerField(default=0)

    # ── 7. CM 964 Active tiers ────────────────────────────────
    cm_964_active_platinum    = models.IntegerField(default=0)
    cm_964_active_gold        = models.IntegerField(default=0)
    cm_964_active_silver      = models.IntegerField(default=0)
    cm_964_active             = models.IntegerField(default=0)

    # ── 8. Bundles ────────────────────────────────────────────
    total_bundles_activated     = models.IntegerField(default=0)
    daily_avg_bundle_subs       = models.IntegerField(default=0)
    cc                          = models.IntegerField(default=0)
    total_bundles_activated_2   = models.IntegerField(default=0)
    daily_avg_bundle_subs_2     = models.IntegerField(default=0)

    # ── 9. CMTD & Retailer Transactions ───────────────────────
    evc_cmtd_active           = models.IntegerField(default=0)
    cm_daily_active           = models.IntegerField(default=0)
    active_964_cmtd           = models.IntegerField(default=0)
    retailer_trans_count_1    = models.IntegerField(default=0)
    retailer_trans_count_2    = models.IntegerField(default=0)
    trans_ge_3_pct            = models.FloatField(default=0)

    # ── 10. PBC / ZR / Retailer ───────────────────────────────
    pbc                       = models.IntegerField(default=0)
    zr_fca                    = models.IntegerField(default=0)
    zr                        = models.IntegerField(default=0)
    evc_retailer              = models.IntegerField(default=0)
    daily_active_evc          = models.IntegerField(default=0)
    daily_active_served       = models.IntegerField(default=0)

    # ── 11. SR ────────────────────────────────────────────────
    wic_sr                    = models.FloatField(default=0)
    retail_sr                 = models.FloatField(default=0)
    total_sr                  = models.FloatField(default=0)

    # ── 12. Per-Site block ────────────────────────────────────
    cell_sites_count          = models.IntegerField(default=0)
    fca_per_site              = models.FloatField(default=0)
    fca_per_site_value        = models.FloatField(default=0)
    sd_bundle                 = models.IntegerField(default=0)

    # ── 13. M0 Acquisition Source Breakdown ───────────────────
    fca_m0                    = models.IntegerField(default=0)
    mnp_m0                    = models.IntegerField(default=0)
    mbb_m0                    = models.IntegerField(default=0)
    data_sim_m0               = models.IntegerField(default=0)
    ga_m0                     = models.IntegerField(default=0)
    hvc_m0                    = models.IntegerField(default=0)
    m0_rev_fca                = models.BigIntegerField(default=0)
    m0_rev_mnp                = models.BigIntegerField(default=0)
    m0_rev_mbb                = models.BigIntegerField(default=0)
    m0_rev_data_sim           = models.BigIntegerField(default=0)
    m0_rev_ga                 = models.BigIntegerField(default=0)
    m0_hvc_rev                = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'channel_daily'
        indexes = [
            models.Index(fields=['region', 'business_unit', 'date']),
            models.Index(fields=['region', 'business_unit', 'arm']),
            models.Index(fields=['franchise_id', 'date']),
            models.Index(fields=['date', 'region']),
            models.Index(fields=['date']),
            models.Index(fields=['arm', 'date']),
            models.Index(fields=['business_unit', 'date']),
            models.Index(fields=['date', 'business_unit', 'arm']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f'{self.date} · {self.franchise_id} · {self.business_unit}'

    @property
    def fca_attainment(self):
        return round(self.fca_ach / self.fca_target * 100, 1) if self.fca_target else 0

    @property
    def loading_attainment(self):
        return round(self.loading_ach / self.loading_target * 100, 1) if self.loading_target else 0

    @property
    def m0_revenue_attainment(self):
        return round(self.m0_revenue_ach / self.m0_revenue_target * 100, 1) if self.m0_revenue_target else 0