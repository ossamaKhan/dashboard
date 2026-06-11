from django.db import models
from django.contrib.auth.models import User


class SiteData(models.Model):
    # ── Time fields ──
    month              = models.IntegerField(null=True, blank=True)
    year               = models.IntegerField(null=True, blank=True)

    # ── Site identifiers ──
    key                = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    id_2g              = models.CharField(max_length=50, null=True, blank=True)
    id_3g              = models.CharField(max_length=100, null=True, blank=True)
    id_4g              = models.CharField(max_length=100, null=True, blank=True)

    # ── Classification ──
    technology         = models.CharField(max_length=50, null=True, blank=True)
    business_unit      = models.CharField(max_length=100, null=True, blank=True)
    region             = models.CharField(max_length=100, null=True, blank=True)
    commercial_district = models.CharField(max_length=100, null=True, blank=True)
    cl_status          = models.CharField(max_length=100, null=True, blank=True)
    usf_status         = models.CharField(max_length=50, null=True, blank=True)

    # ── Location ──
    latitude           = models.FloatField(null=True, blank=True)
    longitude          = models.FloatField(null=True, blank=True)

    # ── Administrative ──
    pta_district       = models.CharField(max_length=100, null=True, blank=True)
    site_status        = models.CharField(max_length=50, null=True, blank=True)
    site_type          = models.CharField(max_length=50, null=True, blank=True)
    franchise          = models.CharField(max_length=50, null=True, blank=True)
    arm                = models.CharField(max_length=200, null=True, blank=True)

    # ── Metrics ──
    bvs                = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    fca                = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

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

    avg_dly_act        = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    act_recharger      = models.IntegerField(null=True, blank=True)

    m0_revn            = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    mnp_fca            = models.IntegerField(null=True, blank=True)
    handset_4g         = models.IntegerField(null=True, blank=True)

    rchrg_face_value_mtd   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    pp_rechar_face_val_mtd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    prepaid_dgtl_amount    = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    postpaid_dgtl_amount   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    conventional_recharge  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'site_data'
        indexes = [
            models.Index(fields=['year'],                name='idx_year'),
            models.Index(fields=['month'],               name='idx_month'),
            models.Index(fields=['key'],                 name='idx_key'),
            models.Index(fields=['region'],              name='idx_region'),
            models.Index(fields=['business_unit'],       name='idx_business_unit'),
            models.Index(fields=['commercial_district'], name='idx_commercial_district'),
            models.Index(fields=['franchise'],           name='idx_franchise'),
            models.Index(fields=['technology'],          name='idx_technology'),
            models.Index(fields=['site_status'],         name='idx_site_status'),
            models.Index(fields=['arm'],                 name='idx_arm'),
            models.Index(fields=['latitude', 'longitude'], name='idx_lat_lng'),
            models.Index(fields=['year', 'month'],                        name='idx_year_month'),
            models.Index(fields=['year', 'month', 'region'],              name='idx_year_month_region'),
            models.Index(fields=['year', 'month', 'business_unit'],       name='idx_year_month_bu'),
            models.Index(fields=['year', 'month', 'commercial_district'], name='idx_year_month_district'),
            models.Index(fields=['year', 'month', 'franchise'],           name='idx_year_month_franchise'),
            models.Index(fields=['year', 'month', 'key'],                 name='idx_year_month_key'),
        ]

    def __str__(self):
        return f"{self.key} - {self.franchise} - {self.month}/{self.year}"


class UserProfile(models.Model):
    DESIGNATION_CHOICES = [
        ('RD', 'RD'),
        ('ARM', 'ARM'),
        ('Manager', 'Manager'),
        ('Executive', 'Executive'),
    ]

    CATEGORY_CHOICES = [
        ('Region', 'Region'),
        ('BU', 'BU'),
        ('ARM', 'ARM'),
    ]
    category           = models.CharField(
        max_length=10,
        choices=CATEGORY_CHOICES,
        default='Region',
        help_text='Region = full access | BU = locked to one business unit | ARM = locked to one ARM'
    )
    user_business_unit = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Exact business_unit value from SiteData (used when category=BU)'
    )
    user_arm           = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Exact arm value from SiteData (used when category=ARM)'
    )

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
    last_seen   = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} Profile [{self.category}]"

    def get_picture_url(self):
        if self.picture:
            return self.picture.url
        return None


class ChatMessage(models.Model):
    sender         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    text           = models.TextField(blank=True, default='')
    image          = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    # ── Voice messages ──
    audio          = models.FileField(upload_to='chat_audio/', blank=True, null=True)
    audio_duration = models.PositiveIntegerField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        # No default ordering — views specify order_by() explicitly for best performance
        db_table = 'chat_message'
        indexes = [
            models.Index(fields=['id'],         name='idx_chat_id'),
            models.Index(fields=['created_at'], name='idx_chat_created'),
        ]

    def __str__(self):
        return f"{self.sender.username} @ {self.created_at}"