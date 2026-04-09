from django.db import models
from django.contrib.auth.models import User


class SiteData(models.Model):
    # New fields added
    region_main        = models.CharField(max_length=100, null=True, blank=True)
    bisp_type          = models.CharField(max_length=50, null=True, blank=True)
    month              = models.IntegerField(null=True, blank=True)
    year               = models.IntegerField(null=True, blank=True)
    key                = models.CharField(null=True, blank=True)

    id_2g              = models.CharField(max_length=50, null=True, blank=True)
    id_3g              = models.CharField(max_length=100, null=True, blank=True)
    id_4g              = models.CharField(max_length=100, null=True, blank=True)

    technology         = models.CharField(max_length=50, null=True, blank=True)
    business_unit      = models.CharField(max_length=100, null=True, blank=True)

    region             = models.CharField(max_length=100, null=True, blank=True)
    commercial_district = models.CharField(max_length=100, null=True, blank=True)

    cl_status          = models.CharField(max_length=100, null=True, blank=True)
    usf_status         = models.CharField(max_length=50, null=True, blank=True)

    latitude           = models.FloatField(null=True, blank=True)
    longitude          = models.FloatField(null=True, blank=True)

    pta_district       = models.CharField(max_length=100, null=True, blank=True)
    site_status        = models.CharField(max_length=50, null=True, blank=True)
    site_type          = models.CharField(max_length=50, null=True, blank=True)

    franchise          = models.CharField(max_length=50, null=True, blank=True)
    arm                = models.CharField(max_length=200, null=True, blank=True)

    fca                = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    bvs                = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    act_90d            = models.IntegerField(null=True, blank=True)
    act_30d            = models.IntegerField(null=True, blank=True)
    act_90d_4g         = models.IntegerField(null=True, blank=True)

    hvc_base           = models.IntegerField(null=True, blank=True)
    tot_revn_amt       = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    bvs_retailer       = models.IntegerField(null=True, blank=True)
    evc_retailer       = models.IntegerField(null=True, blank=True)

    minutes_outgoing   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    minutes_incoming   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    volume_gbs         = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    data_ntwrk_vol_4g  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    fca_adjusted       = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    tot_revival        = models.IntegerField(null=True, blank=True)
    gross_churn        = models.IntegerField(null=True, blank=True)
    net_add            = models.IntegerField(null=True, blank=True)

    avg_dly_act        = models.IntegerField(null=True, blank=True)
    act_recharger      = models.IntegerField(null=True, blank=True)

    m0_revn            = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    mnp_fca            = models.IntegerField(null=True, blank=True)
    handset_4g         = models.IntegerField(null=True, blank=True)

    rchrg_face_value_mtd   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    pp_rechar_face_val_mtd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    prepaid_dgtl_amount    = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    postpaid_dgtl_amount   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    conventional_recharge  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_recharge         = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    digi_recharge          = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'site_data'

    def __str__(self):
        return f"{self.franchise} - {self.month}/{self.year}"


class UserProfile(models.Model):
    DESIGNATION_CHOICES = [
        ('RD', 'RD'),
        ('ARM', 'ARM'),
        ('Manager', 'Manager'),
        ('Executive', 'Executive'),
    ]

    # ── Role / Category ───────────────────────────────────────
    # Determines which slice of data this user can see.
    CATEGORY_CHOICES = [
        ('Region', 'Region'),  # Full access — all data, all filters unlocked
        ('BU', 'BU'),          # Scoped to one Business Unit; Region filter locked
        ('ARM', 'ARM'),        # Scoped to one ARM value;  Region + BU filters locked
    ]
    category           = models.CharField(
        max_length=10,
        choices=CATEGORY_CHOICES,
        default='Region',
        help_text='Region = full access | BU = locked to one business unit | ARM = locked to one ARM'
    )
    # For BU users — must exactly match SiteData.business_unit
    user_business_unit = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Exact business_unit value from SiteData (used when category=BU)'
    )
    # For ARM users — must exactly match SiteData.arm
    user_arm           = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Exact arm value from SiteData (used when category=ARM)'
    )

    # ── Standard profile fields ────────────────────────────────
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone       = models.CharField(max_length=20, blank=True, default='')
    designation = models.CharField(max_length=50, choices=DESIGNATION_CHOICES, blank=True, default='')
    department  = models.CharField(max_length=100, blank=True, default='')
    region      = models.CharField(max_length=100, blank=True, default='Central B')
    employee_id = models.CharField(max_length=50, blank=True, default='')
    bio         = models.TextField(max_length=300, blank=True, default='')
    picture     = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} Profile [{self.category}]"

    def get_picture_url(self):
        if self.picture:
            return self.picture.url
        return None