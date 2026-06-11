from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login as auth_login
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
import csv
import pandas as pd
from datetime import datetime
from decimal import Decimal

from marketing.models import SiteData, UserProfile
from channel.models import ChannelDaily
from django.contrib.auth.models import User
from .forms import SiteDataForm, UserProfileForm
from .models import AdminLog


# ── Auth helpers ──────────────────────────────────────────────

def admin_required(view_func):
    decorated = login_required(view_func, login_url='/admin-panel/login/')
    return user_passes_test(lambda u: u.is_staff, login_url='/admin-panel/login/')(decorated)

def is_admin(user):
    return user.is_authenticated and user.is_staff


# ── Admin Login ───────────────────────────────────────────────

def admin_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')
    if request.user.is_authenticated and not request.user.is_staff:
        messages.error(request, 'You do not have admin privileges.')
        return redirect('login')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff:
                auth_login(request, user)
                AdminLog.objects.create(
                    user=user, action='login', model_name='Auth',
                    details='Admin logged in from admin panel'
                )
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect(request.GET.get('next', 'admin_dashboard'))
            else:
                messages.error(request, 'This account does not have admin privileges.')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'admin_panel/admin_login.html')


# ── Admin Dashboard ───────────────────────────────────────────

@admin_required
def admin_dashboard(request):
    total_sites    = SiteData.objects.count()
    total_users    = User.objects.count()
    total_profiles = UserProfile.objects.count()
    recent_sites   = SiteData.objects.order_by('-id')[:10]
    recent_users   = User.objects.order_by('-date_joined')[:10]
    recent_logs    = AdminLog.objects.all()[:20]

    monthly_stats = SiteData.objects.values('month').annotate(
        total_revenue=Sum('tot_revn_amt'),
        total_activations=Sum('act_90d'),
        site_count=Count('id')
    ).order_by('-month')[:12]

    region_stats = SiteData.objects.values('region').annotate(
        total_revenue=Sum('tot_revn_amt'),
        site_count=Count('id')
    ).order_by('-total_revenue')[:10]

    return render(request, 'admin_panel/dashboard.html', {
        'total_sites': total_sites, 'total_users': total_users,
        'total_profiles': total_profiles, 'recent_sites': recent_sites,
        'recent_users': recent_users, 'recent_logs': recent_logs,
        'monthly_stats': monthly_stats, 'region_stats': region_stats,
        'active_tab': 'dashboard',
    })


# ── Site Data CRUD ────────────────────────────────────────────

@admin_required
def site_data_list(request):
    sites = SiteData.objects.all().order_by('-id')

    search_query  = request.GET.get('search', '')
    region_filter = request.GET.get('region', '')
    tech_filter   = request.GET.get('technology', '')

    if search_query:
        sites = sites.filter(
            Q(franchise__icontains=search_query) |
            Q(region__icontains=search_query) |
            Q(pta_district__icontains=search_query) |
            Q(technology__icontains=search_query)
        )
    if region_filter:
        sites = sites.filter(region=region_filter)
    if tech_filter:
        sites = sites.filter(technology=tech_filter)

    paginator  = Paginator(sites, 50)
    sites_page = paginator.get_page(request.GET.get('page', 1))

    regions      = SiteData.objects.values_list('region', flat=True).distinct().order_by('region')
    technologies = SiteData.objects.values_list('technology', flat=True).distinct().order_by('technology')

    return render(request, 'admin_panel/site_data_list.html', {
        'sites': sites_page, 'regions': regions, 'technologies': technologies,
        'search_query': search_query, 'region_filter': region_filter,
        'tech_filter': tech_filter, 'active_tab': 'site_data',
    })


@admin_required
def site_data_create(request):
    if request.method == 'POST':
        form = SiteDataForm(request.POST)
        if form.is_valid():
            site = form.save()
            AdminLog.objects.create(
                user=request.user, action='create', model_name='SiteData',
                object_id=str(site.id),
                details=f'Created site data for {site.franchise or "Unknown"}'
            )
            messages.success(request, 'Site data created successfully!')
            return redirect('admin_site_data_list')
    else:
        form = SiteDataForm()
    return render(request, 'admin_panel/site_data_form.html', {
        'form': form, 'title': 'Create Site Data', 'active_tab': 'site_data',
    })


@admin_required
def site_data_edit(request, pk):
    site = get_object_or_404(SiteData, pk=pk)
    if request.method == 'POST':
        form = SiteDataForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            AdminLog.objects.create(
                user=request.user, action='update', model_name='SiteData',
                object_id=str(site.id),
                details=f'Updated site data for {site.franchise or "Unknown"}'
            )
            messages.success(request, 'Site data updated successfully!')
            return redirect('admin_site_data_list')
    else:
        form = SiteDataForm(instance=site)
    return render(request, 'admin_panel/site_data_form.html', {
        'form': form, 'title': f'Edit Site - {site.franchise or site.id}',
        'site': site, 'active_tab': 'site_data',
    })


@admin_required
def site_data_delete(request, pk):
    site = get_object_or_404(SiteData, pk=pk)
    if request.method == 'POST':
        franchise = site.franchise or 'Unknown'
        site.delete()
        AdminLog.objects.create(
            user=request.user, action='delete', model_name='SiteData',
            object_id=str(pk), details=f'Deleted site data for {franchise}'
        )
        messages.success(request, 'Site data deleted successfully!')
        return redirect('admin_site_data_list')
    return render(request, 'admin_panel/site_data_confirm_delete.html', {
        'site': site, 'active_tab': 'site_data',
    })


# ── Helper: pull distinct BU and ARM lists from SiteData ─────

def _get_bu_choices():
    """Distinct business_unit values from SiteData, sorted."""
    return list(
        SiteData.objects.exclude(business_unit__isnull=True)
        .exclude(business_unit='')
        .values_list('business_unit', flat=True)
        .distinct()
        .order_by('business_unit')
    )

def _get_arm_choices():
    """Distinct arm values from SiteData, sorted."""
    return list(
        SiteData.objects.exclude(arm__isnull=True)
        .exclude(arm='')
        .values_list('arm', flat=True)
        .distinct()
        .order_by('arm')
    )


# ── User CRUD ─────────────────────────────────────────────────

@admin_required
def user_list(request):
    users = User.objects.all().select_related('profile').order_by('-date_joined')

    search_query  = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    # NEW: filter by category
    category_filter = request.GET.get('category', '')

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    elif status_filter == 'admin':
        users = users.filter(is_staff=True)

    # Filter by RBAC category via related profile
    if category_filter in ('Region', 'BU', 'ARM'):
        users = users.filter(profile__category=category_filter)

    paginator  = Paginator(users, 20)
    users_page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin_panel/user_list.html', {
        'users':          users_page,
        'search_query':   search_query,
        'status_filter':  status_filter,
        'category_filter': category_filter,
        'total_count':    User.objects.count(),
        'active_count':   User.objects.filter(is_active=True).count(),
        'admin_count':    User.objects.filter(is_staff=True).count(),
        # Category counts for the header chips
        'region_count':   UserProfile.objects.filter(category='Region').count(),
        'bu_count':        UserProfile.objects.filter(category='BU').count(),
        'arm_count':       UserProfile.objects.filter(category='ARM').count(),
        'active_tab':     'users',
    })


@admin_required
def user_create(request):
    """
    Create a brand new user (admin-initiated).
    Includes category, user_business_unit, user_arm assignment.
    """
    bu_choices  = _get_bu_choices()
    arm_choices = _get_arm_choices()

    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        email      = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        password   = request.POST.get('password', '')
        is_active  = request.POST.get('is_active') == 'on'
        is_staff   = request.POST.get('is_staff') == 'on'

        # ── RBAC fields ──
        category           = request.POST.get('category', 'Region')
        user_business_unit = ','.join([b.strip() for b in request.POST.getlist('user_business_unit') if b.strip()])
        user_arm           = request.POST.get('user_arm', '').strip()

        errors = []
        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append('A user with this username already exists.')
        if not email:
            errors.append('Email is required.')
        elif User.objects.filter(email=email).exists():
            errors.append('A user with this email already exists.')
        if not password or len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if category == 'BU' and not user_business_unit.strip(','):
            errors.append('Please select a Business Unit for BU category users.')
        if category == 'ARM' and not user_arm:
            errors.append('Please select an ARM for ARM category users.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name,
                is_active=is_active, is_staff=is_staff,
            )
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone              = request.POST.get('phone', '').strip()
            profile.designation        = request.POST.get('designation', '').strip()
            profile.department         = request.POST.get('department', '').strip()
            profile.region             = request.POST.get('region', '').strip()
            profile.employee_id        = request.POST.get('employee_id', '').strip()
            # ── RBAC ──
            profile.category           = category
            profile.user_business_unit = ','.join([b.strip() for b in request.POST.getlist('user_business_unit') if b.strip()]) if category == 'BU' else ''
            profile.user_arm           = user_arm           if category == 'ARM' else ''
            profile.save()

            AdminLog.objects.create(
                user=request.user, action='create', model_name='User',
                object_id=str(user.id),
                details=f'Created user {user.username} [{category}]'
            )
            messages.success(request, f'User "{user.username}" created as {category}!')
            return redirect('admin_user_list')

    return render(request, 'admin_panel/user_form.html', {
        'title':              'Create New User',
        'designation_choices': UserProfile.DESIGNATION_CHOICES,
        'bu_choices':          bu_choices,
        'arm_choices':         arm_choices,
        'active_tab':          'users',
        'is_create':           True,
    })


@admin_required
def user_edit(request, pk):
    """
    Edit an existing user — updates User model, UserProfile, and RBAC category.
    """
    user       = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    bu_choices  = _get_bu_choices()
    arm_choices = _get_arm_choices()

    if request.method == 'POST':
        new_username = request.POST.get('username', '').strip()
        new_email    = request.POST.get('email', '').strip().lower()
        errors = []

        if User.objects.filter(username=new_username).exclude(pk=pk).exists():
            errors.append('This username is already taken by another user.')
        if User.objects.filter(email=new_email).exclude(pk=pk).exists():
            errors.append('This email is already used by another account.')

        # ── RBAC fields ──
        category           = request.POST.get('category', 'Region')
        user_business_unit = ','.join([b.strip() for b in request.POST.getlist('user_business_unit') if b.strip()])
        user_arm           = request.POST.get('user_arm', '').strip()

        if category == 'BU' and not user_business_unit.strip(','):
            errors.append('Please select a Business Unit for BU category users.')
        if category == 'ARM' and not user_arm:
            errors.append('Please select an ARM for ARM category users.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            user.username   = new_username
            user.email      = new_email
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name  = request.POST.get('last_name', '').strip()
            user.is_active  = request.POST.get('is_active') == 'on'
            user.is_staff   = request.POST.get('is_staff') == 'on'
            user.save()

            profile.phone              = request.POST.get('phone', '').strip()
            profile.designation        = request.POST.get('designation', '').strip()
            profile.department         = request.POST.get('department', '').strip()
            profile.region             = request.POST.get('region', '').strip()
            profile.employee_id        = request.POST.get('employee_id', '').strip()
            profile.bio                = request.POST.get('bio', '').strip()
            # ── RBAC ──
            profile.category           = category
            profile.user_business_unit = ','.join([b.strip() for b in request.POST.getlist('user_business_unit') if b.strip()]) if category == 'BU' else ''
            profile.user_arm           = user_arm           if category == 'ARM' else ''
            if 'picture' in request.FILES:
                profile.picture = request.FILES['picture']
            profile.save()

            new_password = request.POST.get('new_password', '').strip()
            if new_password:
                if len(new_password) < 8:
                    messages.error(request, 'New password must be at least 8 characters.')
                    return redirect('admin_user_edit', pk=pk)
                user.set_password(new_password)
                user.save()

            AdminLog.objects.create(
                user=request.user, action='update', model_name='User',
                object_id=str(user.id),
                details=f'Updated user {user.username} — category set to {category}'
            )
            messages.success(request, f'User "{user.username}" updated! Category: {category}')
            return redirect('admin_user_list')

    return render(request, 'admin_panel/user_form.html', {
        'title':               f'Edit User — {user.username}',
        'edit_user':            user,
        'profile':              profile,
        'designation_choices':  UserProfile.DESIGNATION_CHOICES,
        'bu_choices':           bu_choices,
        'arm_choices':          arm_choices,
        'active_tab':           'users',
        'is_create':            False,
    })


@admin_required
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('admin_user_list')
    if request.method == 'POST':
        username = user.username
        user.delete()
        AdminLog.objects.create(
            user=request.user, action='delete', model_name='User',
            object_id=str(pk), details=f'Deleted user {username}'
        )
        messages.success(request, f'User "{username}" deleted successfully.')
        return redirect('admin_user_list')
    return render(request, 'admin_panel/user_confirm_delete.html', {
        'user': user, 'active_tab': 'users',
    })


@admin_required
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_user_list')
    user.is_active = not user.is_active
    user.save()
    status = 'activated' if user.is_active else 'deactivated'
    AdminLog.objects.create(
        user=request.user, action='update', model_name='User',
        object_id=str(user.id), details=f'User {user.username} {status}'
    )
    messages.success(request, f'User "{user.username}" has been {status}.')
    return redirect('admin_user_list')


# ── NEW: Quick category assignment via AJAX/POST ──────────────

@admin_required
def user_set_category(request, pk):
    """
    Quick-assign category without going to the full edit page.
    POST: category, user_business_unit (if BU), user_arm (if ARM)
    Returns JSON for use with fetch().
    """
    user    = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        category           = request.POST.get('category', 'Region')
        user_business_unit = ','.join([b.strip() for b in request.POST.getlist('user_business_unit') if b.strip()])
        user_arm           = request.POST.get('user_arm', '').strip()

        if category not in ('Region', 'BU', 'ARM'):
            return JsonResponse({'ok': False, 'error': 'Invalid category'}, status=400)
        if category == 'BU' and not user_business_unit.strip(','):
            return JsonResponse({'ok': False, 'error': 'Business Unit is required for BU category'}, status=400)
        if category == 'ARM' and not user_arm:
            return JsonResponse({'ok': False, 'error': 'ARM value is required for ARM category'}, status=400)

        profile.category           = category
        profile.user_business_unit = ','.join([b.strip() for b in request.POST.getlist('user_business_unit') if b.strip()]) if category == 'BU' else ''
        profile.user_arm           = user_arm           if category == 'ARM' else ''
        profile.save()

        AdminLog.objects.create(
            user=request.user, action='update', model_name='User',
            object_id=str(user.id),
            details=f'Quick-set category for {user.username} → {category}'
        )
        return JsonResponse({'ok': True, 'category': category})

    return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)


# ── Import / Export ───────────────────────────────────────────

def to_dec(val):
    try:
        if pd.isna(val): return None
        cleaned = str(val).replace(',', '').replace(' ', '').strip()
        if cleaned in ('', '-', '—', 'nan', 'None'): return None
        return Decimal(cleaned)
    except:
        return None

def to_int(val):
    try:
        if pd.isna(val): return None
        cleaned = str(val).replace(',', '').replace(' ', '').strip()
        if cleaned in ('', '-', '—', 'nan', 'None'): return None
        return int(float(cleaned))
    except:
        return None

def to_float(val):
    try:
        if pd.isna(val): return None
        return float(val)
    except:
        return None

def to_str(val):
    try:
        if pd.isna(val): return None
        s = str(val).strip()
        return None if s in ('', 'nan', 'None') else s
    except:
        return None

# ── Channel column map (mirrors import_channel management command) ──
import re as _re

_CH_COL_MAP = {
    'Dated':'date','Franchise ID':'franchise_id','City':'city','Region':'region',
    'BU':'business_unit','Status':'status','ARM':'arm','GA Target':'fca_target','GA Ach':'fca_ach',
    '4G Targets':'g4_target','4G Ach':'g4_ach','MNP Target':'mnp_target','MNP Ach':'mnp_ach',
    'Loading Target':'loading_target','Loading Ach':'loading_ach','EVC Uload':'evc_uload',
    'Vouchers':'vouchers','Total Site Loading':'total_site_loading',
    'Conv. site loading':'loading_ach_site_conv','Issuance Ach':'issuance_ach',
    'Uload Recharge Ach':'uload_recharge_ach','Data SIM FCA':'data_sim_fca',
    'MBB Targets':'mbb_target','MBB Ach':'mbb_ach','M0 Revenue Targets':'m0_revenue_target',
    'M0 Revenue Ach':'m0_revenue_ach','QOS Targets':'qos_target','QOS Ach':'qos_ach',
    'EVC Active Base':'evc_active_base','Bundle Target':'bundle_target','Bundle Ach':'bundle_ach',
    'Recharge Only':'recharge_only','Female FCA Count':'female_fca_count',
    'Dormancy Count':'dormancy_count','HVC TGT':'hvc_target','HVC Ach':'hvc_ach',
    'CM GA':'cm_ga','CM Disown':'cm_disown','Female CNIC Disowned':'female_cnic_disowned',
    'New SIM Sale (Disowned CNICs)':'new_sim_sale_disowned_cnics',
    'FCA Date within 90 Days Disowned':'fca_within_90d_disowned',
    'FCA Date within 90 Days (Disown & new Activation)':'fca_within_90d_disown_new_activation',
    '90 Days Active Base Disown':'active_90d_base_disown',
    '90 Days Active Base (Disown & new Activation)':'active_90d_base_disown_new_activation',
    'NPR SO':'npr','Active SO (Daily Ave.)':'active_so_daily_avg','Active SO NPR':'active_so_npr',
    'LM Active EVC':'lm_active_evc','MTD Served':'mtd_served','Avg Served':'avg_served',
    'CM EVC Active (Platinum)':'cm_evc_active_platinum','CM EVC Active (Gold)':'cm_evc_active_gold',
    'CM EVC Active (Silver)':'cm_evc_active_silver','CM EVC Active':'cm_evc_active',
    'CM 964 Active (Platinum)':'cm_964_active_platinum','CM 964 Active (Gold)':'cm_964_active_gold',
    'CM 964 Active (Silver)':'cm_964_active_silver','CM 964 Active':'cm_964_active',
    'Total Bundles Activated':'total_bundles_activated','Daily Avg. Bundle Subs':'daily_avg_bundle_subs',
    'cc':'cc','Total Bundles Activated.1':'total_bundles_activated_2',
    'Daily Avg. Bundle Subs.1':'daily_avg_bundle_subs_2','EVC CMTD Active':'evc_cmtd_active',
    'CM Daily Active':'cm_daily_active','964 Active CMTD':'active_964_cmtd',
    'Retailer Trans Count = 1':'retailer_trans_count_1','Retailer Trans Count = 2':'retailer_trans_count_2',
    'Trans >=3%':'trans_ge_3_pct','PBC':'pbc','ZR FCA':'zr_fca','ZR':'zr',
    'EVC Retailer':'evc_retailer','Daily Active EVC':'daily_active_evc',
    'Daily Active Served':'daily_active_served','WIC SR':'wic_sr','Retail SR':'retail_sr',
    'Total SR':'total_sr','Cell Sites Count':'cell_sites_count','FCA':'fca_per_site',
    'Per Site FCA':'fca_per_site_value','SD Bundle':'sd_bundle','FCA ARPU':'fca_m0',
    'MNP ARPU':'mnp_m0','MBB ARPU':'mbb_m0','Data Sim ARPU':'data_sim_m0',
    'GA ARPU':'ga_m0','HVC ARPU':'hvc_m0','M0 Rev FCA':'m0_rev_fca',
    'M0 Rev MNP':'m0_rev_mnp','M0 Rev MBB':'m0_rev_mbb','M0 Rev Data Sim':'m0_rev_data_sim',
    'M0 Rev GA':'m0_rev_ga','M0 HVC Rev':'m0_hvc_rev',
}

def _ch_parse_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return 0
    if isinstance(v, (int, float)): return v
    s = str(v).strip().replace(',','').replace(' ','')
    if s in ('','nan','na','-','#div/0!','#n/a'): return 0
    try: return float(s)
    except: return 0

def _ch_parse_date(v):
    if pd.isna(v): return None
    if isinstance(v, datetime): return v.date()
    if hasattr(v,'date'): return v.date()
    s = str(v).strip()
    for fmt in ('%m/%d/%Y','%d/%m/%Y','%Y-%m-%d','%m-%d-%Y'):
        try: return datetime.strptime(s,fmt).date()
        except: continue
    return None


@admin_required
def import_data(request):
    data_type = request.POST.get('data_type', 'marketing') if request.method == 'POST' else 'marketing'

    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        try:
            if data_type == 'channel':
                # ── Channel import ─────────────────────────────────────
                df = pd.read_excel(file)
                # Normalize headers (collapse newlines/spaces)
                df.columns = [_re.sub(r'\s+', ' ', str(c)).strip() for c in df.columns]
                # Handle duplicate columns
                seen = {}
                new_cols = []
                for c in df.columns:
                    if c in seen:
                        seen[c] += 1
                        new_cols.append(f'{c}.{seen[c]}')
                    else:
                        seen[c] = 0
                        new_cols.append(c)
                df.columns = new_cols

                int_fields = {f.name for f in ChannelDaily._meta.get_fields()
                              if hasattr(f,'get_internal_type') and f.get_internal_type() in ('IntegerField','BigIntegerField')}
                float_fields = {f.name for f in ChannelDaily._meta.get_fields()
                                if hasattr(f,'get_internal_type') and f.get_internal_type()=='FloatField'}

                existing_keys = set(ChannelDaily.objects.values_list('date','franchise_id'))
                objs_create = []
                objs_update = []
                skipped = 0
                total_rows = len(df)

                for idx, row in df.iterrows():
                    kwargs = {}
                    for src_col, model_field in _CH_COL_MAP.items():
                        if src_col not in df.columns: continue
                        val = row[src_col]
                        if model_field == 'date':
                            kwargs[model_field] = _ch_parse_date(val)
                        elif model_field in ('franchise_id','city','region','business_unit',
                                             'arm','status'):
                            kwargs[model_field] = str(val).strip() if not pd.isna(val) else ''
                        elif model_field in int_fields:
                            kwargs[model_field] = int(_ch_parse_num(val))
                        elif model_field in float_fields:
                            kwargs[model_field] = float(_ch_parse_num(val))
                        else:
                            kwargs[model_field] = _ch_parse_num(val)

                    if not kwargs.get('date') or not kwargs.get('franchise_id'):
                        skipped += 1
                        continue

                    key = (kwargs['date'], kwargs['franchise_id'])
                    if key in existing_keys:
                        objs_update.append(kwargs)
                    else:
                        objs_create.append(ChannelDaily(**kwargs))
                        existing_keys.add(key)

                if objs_create:
                    ChannelDaily.objects.bulk_create(objs_create, batch_size=500)
                if objs_update:
                    for kw in objs_update:
                        ChannelDaily.objects.filter(
                            date=kw['date'], franchise_id=kw['franchise_id']
                        ).update(**{k:v for k,v in kw.items() if k not in ('date','franchise_id')})

                AdminLog.objects.create(
                    user=request.user, action='import', model_name='ChannelDaily',
                    details=f'Imported {len(objs_create)} new + {len(objs_update)} updated channel rows from {file.name}'
                )
                messages.success(request, f'✅ Channel import: {len(objs_create)} created, {len(objs_update)} updated, {skipped} skipped.')

            else:
                # ── Marketing import ───────────────────────────────────
                df = pd.read_excel(file, header=None)
                df.columns = range(len(df.columns))
                df = df.iloc[1:].reset_index(drop=True)
                df = df[df[0].notna()]
                objects = []
                total_rows = len(df)
                for i, row in df.iterrows():
                    # Parse month/year from row[0]
                    _mr = row[0]; _mo = None; _yr = None
                    try:
                        import pandas as _pd
                        if hasattr(_mr,'month'): _mo=_mr.month; _yr=_mr.year
                        elif not (isinstance(_mr,float) and _pd.isna(_mr)):
                            import datetime as _dt; _s=str(_mr).strip()
                            for _f in ('%b-%Y','%B-%Y','%Y-%m-%d','%m/%d/%Y','%d/%m/%Y'):
                                try: _d=_dt.datetime.strptime(_s,_f); _mo=_d.month; _yr=_d.year; break
                                except: pass
                    except: pass
                    obj = SiteData(
                        month=_mo, year=_yr,
                        key=to_str(row[1]),
                        id_2g=to_str(row[2]),             id_3g=to_str(row[3]),           id_4g=to_str(row[4]),
                        technology=to_str(row[5]),        business_unit=to_str(row[6]),   region=to_str(row[7]),
                        commercial_district=to_str(row[8]), cl_status=to_str(row[9]),     usf_status=to_str(row[10]),
                        latitude=to_float(row[11]),       longitude=to_float(row[12]),
                        pta_district=to_str(row[13]),     site_status=to_str(row[14]),    site_type=to_str(row[15]),
                        franchise=to_str(row[16]),        arm=to_str(row[17]),
                        bvs=to_dec(row[18]),              fca=to_dec(row[19]),
                        act_90d=to_int(row[20]),          act_30d=to_int(row[21]),        act_90d_4g=to_int(row[22]),
                        hvc_base=to_int(row[23]),         tot_revn_amt=to_dec(row[24]),
                        bvs_retailer=to_int(row[25]),     evc_retailer=to_int(row[26]),
                        minutes_outgoing=to_dec(row[27]), minutes_incoming=to_dec(row[28]),
                        volume_gbs=to_dec(row[29]),       data_ntwrk_vol_4g=to_dec(row[30]),
                        fca_adjusted=to_dec(row[31]),
                        tot_revival=to_int(row[32]),      gross_churn=to_int(row[33]),
                        net_add=to_int(row[34]),          avg_dly_act=to_dec(row[35]),
                        act_recharger=to_int(row[36]),    m0_revn=to_dec(row[37]),
                        mnp_fca=to_int(row[38]),          handset_4g=to_int(row[39]),
                        rchrg_face_value_mtd=to_dec(row[40]),
                        pp_rechar_face_val_mtd=to_dec(row[41]),
                        prepaid_dgtl_amount=to_dec(row[42]),
                        postpaid_dgtl_amount=to_dec(row[43]),
                        conventional_recharge=to_dec(row[44]),
                    )
                    objects.append(obj)
                    if len(objects) == 500:
                        SiteData.objects.bulk_create(objects)
                        objects = []
                if objects:
                    SiteData.objects.bulk_create(objects)
                AdminLog.objects.create(
                    user=request.user, action='import', model_name='SiteData',
                    details=f'Imported {total_rows} records from {file.name}'
                )
                messages.success(request, f'🎉 Marketing import: {total_rows} records uploaded!')

        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('import_data')

    return render(request, 'admin_panel/import_data.html', {
        'active_tab': 'import',
        'marketing_count': SiteData.objects.count(),
        'channel_count': ChannelDaily.objects.count(),
    })


@admin_required
def wipe_data(request):
    """Wipe marketing or channel data — POST only with confirmation."""
    if request.method == 'POST':
        data_type = request.POST.get('data_type', '')
        confirm   = request.POST.get('confirm', '')
        if confirm != 'DELETE':
            messages.error(request, 'Type DELETE to confirm wipe.')
            return redirect('import_data')
        if data_type == 'marketing':
            count = SiteData.objects.count()
            SiteData.objects.all().delete()
            AdminLog.objects.create(
                user=request.user, action='delete', model_name='SiteData',
                details=f'Wiped all {count} marketing records'
            )
            messages.success(request, f'🗑️ Wiped {count} marketing records.')
        elif data_type == 'channel':
            count = ChannelDaily.objects.count()
            ChannelDaily.objects.all().delete()
            AdminLog.objects.create(
                user=request.user, action='delete', model_name='ChannelDaily',
                details=f'Wiped all {count} channel records'
            )
            messages.success(request, f'🗑️ Wiped {count} channel records.')
        else:
            messages.error(request, 'Invalid data type.')
    return redirect('import_data')


@admin_required
def export_data(request):
    file_format = request.GET.get('format', 'csv')
    model       = request.GET.get('model', 'sitedata')
    queryset    = SiteData.objects.all() if model == 'sitedata' else User.objects.all()
    filename    = f'{"site_data" if model == "sitedata" else "users"}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)

    if model == 'sitedata':
        headers = [f.name for f in SiteData._meta.fields]
        writer.writerow(headers)
        for obj in queryset:
            writer.writerow([getattr(obj, f.name) for f in SiteData._meta.fields])
    else:
        writer.writerow(['id', 'username', 'email', 'first_name', 'last_name',
                         'is_active', 'is_staff', 'date_joined',
                         'category', 'user_business_unit', 'user_arm'])
        for obj in queryset:
            try:
                p = obj.profile
                cat = p.category; bu = p.user_business_unit; arm = p.user_arm
            except Exception:
                cat = bu = arm = ''
            writer.writerow([obj.id, obj.username, obj.email, obj.first_name,
                             obj.last_name, obj.is_active, obj.is_staff,
                             obj.date_joined, cat, bu, arm])

    AdminLog.objects.create(
        user=request.user, action='export', model_name=model.capitalize(),
        details=f'Exported {queryset.count()} records to CSV'
    )
    return response


# ── Admin Logs ────────────────────────────────────────────────

@admin_required
def admin_logs(request):
    logs = AdminLog.objects.all().order_by('-created_at')

    action_filter = request.GET.get('action', '')
    model_filter  = request.GET.get('model', '')
    if action_filter:
        logs = logs.filter(action=action_filter)
    if model_filter:
        logs = logs.filter(model_name__icontains=model_filter)

    paginator = Paginator(logs, 50)
    logs_page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin_panel/admin_logs.html', {
        'logs': logs_page, 'action_filter': action_filter,
        'model_filter': model_filter,
        'actions': ['create', 'update', 'delete', 'import', 'export', 'login'],
        'active_tab': 'logs',
    })