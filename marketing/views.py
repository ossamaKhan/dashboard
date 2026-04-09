from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum, Avg, Count
from django.contrib.auth.models import User
from .models import SiteData, UserProfile
from django.http import JsonResponse
from collections import defaultdict
from django.contrib import messages
import math
import os


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ── Role helpers ──────────────────────────────────────────────

def get_scoped_qs(user):
    profile = get_or_create_profile(user)
    qs = SiteData.objects.all()
    if profile.category == 'BU' and profile.user_business_unit:
        qs = qs.filter(business_unit=profile.user_business_unit)
    elif profile.category == 'ARM' and profile.user_arm:
        qs = qs.filter(arm=profile.user_arm)
    return qs


def get_locked_filters(user):
    profile = get_or_create_profile(user)
    locked = {
        'category': profile.category,
        'region':   {'locked': False},
        'bu':       {'locked': False},
    }
    if profile.category == 'BU':
        locked['bu'] = {'locked': True, 'value': profile.user_business_unit}
    elif profile.category == 'ARM':
        locked['region'] = {'locked': True, 'value': ''}
        locked['bu']     = {'locked': True, 'value': ''}
    return locked


# ── Auth ──────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            messages.error(request, 'No account found with that email address.')
            return render(request, 'dashboard/login.html')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Incorrect password. Please try again.')
        return render(request, 'dashboard/login.html')
    return render(request, 'dashboard/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    errors = {}
    form_data = {}
    if request.method == 'POST':
        full_name        = request.POST.get('full_name', '').strip()
        phone            = request.POST.get('phone', '').strip()
        email            = request.POST.get('email', '').strip().lower()
        password         = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        form_data = {'full_name': full_name, 'phone': phone, 'email': email}
        if not email.endswith('@ptclgroup.com'):
            errors['email'] = 'Only @ptclgroup.com email addresses are allowed.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists.'
        if len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        if password != confirm_password:
            errors['confirm_password'] = 'Passwords do not match.'
        if not full_name:
            errors['full_name'] = 'Full name is required.'
        if not phone:
            errors['phone'] = 'Phone number is required.'
        if not errors:
            username = email.split('@')[0]
            base = username; c = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{c}"; c += 1
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=full_name.split()[0] if full_name else '',
                last_name=' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else '',
            )
            profile = get_or_create_profile(user)
            profile.phone = phone
            profile.save()
            auth_login(request, user)
            return redirect('dashboard')
    return render(request, 'dashboard/register.html', {'errors': errors, 'form_data': form_data})


def logout_view(request):
    auth_logout(request)
    return redirect('login')


# ── Profile ───────────────────────────────────────────────────

@login_required(login_url='login')
def profile_view(request):
    profile = get_or_create_profile(request.user)
    if request.method == 'POST':
        action = request.POST.get('action', 'profile')
        if action == 'profile':
            request.user.first_name = request.POST.get('first_name', '').strip()
            request.user.last_name  = request.POST.get('last_name', '').strip()
            request.user.save()
            profile.phone       = request.POST.get('phone', '').strip()
            profile.designation = request.POST.get('designation', '').strip()
            profile.department  = request.POST.get('department', '').strip()
            profile.region      = request.POST.get('region', '').strip()
            profile.employee_id = request.POST.get('employee_id', '').strip()
            profile.bio         = request.POST.get('bio', '').strip()[:300]
            if 'picture' in request.FILES:
                pic = request.FILES['picture']
                if pic.content_type.startswith('image/'):
                    if profile.picture:
                        try:
                            if os.path.isfile(profile.picture.path):
                                os.remove(profile.picture.path)
                        except Exception:
                            pass
                    profile.picture = pic
                else:
                    messages.error(request, 'Please upload a valid image file.')
                    return redirect('profile')
            profile.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
        elif action == 'password':
            current_pw = request.POST.get('current_password', '')
            new_pw     = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_new_password', '')
            if not request.user.check_password(current_pw):
                messages.error(request, 'Current password is incorrect.')
            elif len(new_pw) < 8:
                messages.error(request, 'New password must be at least 8 characters.')
            elif new_pw != confirm_pw:
                messages.error(request, 'New passwords do not match.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully!')
            return redirect('profile')
        elif action == 'remove_picture':
            if profile.picture:
                try:
                    if os.path.isfile(profile.picture.path):
                        os.remove(profile.picture.path)
                except Exception:
                    pass
                profile.picture = None
                profile.save()
            messages.success(request, 'Profile picture removed.')
            return redirect('profile')
    return render(request, 'dashboard/profile.html', {'profile': profile})


# ── Dashboard ─────────────────────────────────────────────────

@login_required(login_url='login')
def dashboard(request):
    profile = get_or_create_profile(request.user)
    locked  = get_locked_filters(request.user)
    return render(request, 'dashboard/index.html', {'profile': profile, 'locked': locked})


# ── Filters ───────────────────────────────────────────────────

@login_required(login_url='login')
def filter_options(request):
    region = request.GET.get('region')
    pta    = request.GET.get('pta_district')

    base = get_scoped_qs(request.user)

    pta_qs = base
    if region:
        pta_qs = pta_qs.filter(region=region)

    fr_qs = base
    if region:
        fr_qs = fr_qs.filter(region=region)
    if pta:
        fr_qs = fr_qs.filter(pta_district=pta)

    years_list  = list(base.filter(year__isnull=False).values_list('year', flat=True).distinct().order_by('year'))
    latest_year = max(years_list) if years_list else None

    return JsonResponse({
        'regions':        list(base.filter(region__isnull=False).exclude(region='').values_list('region', flat=True).distinct().order_by('region')),
        'pta_districts':  list(pta_qs.filter(pta_district__isnull=False).exclude(pta_district='').values_list('pta_district', flat=True).distinct().order_by('pta_district')),
        'franchises':     list(fr_qs.filter(franchise__isnull=False).exclude(franchise='').values_list('franchise', flat=True).distinct().order_by('franchise')),
        'technologies':   list(base.filter(technology__isnull=False).exclude(technology='').values_list('technology', flat=True).distinct().order_by('technology')),
        'business_units': list(base.filter(business_unit__isnull=False).exclude(business_unit='').values_list('business_unit', flat=True).distinct().order_by('business_unit')),
        'site_statuses':  list(base.filter(site_status__isnull=False).exclude(site_status='').values_list('site_status', flat=True).distinct().order_by('site_status')),
        'months':         list(base.filter(month__isnull=False).values_list('month', flat=True).distinct().order_by('month')),
        'years':          years_list,
        'latest_year':    latest_year,
        # ── FIX 1: Return actual bisp_type values from DB so dropdown uses exact strings ──
        'bisp_types':     list(base.filter(bisp_type__isnull=False).exclude(bisp_type='').values_list('bisp_type', flat=True).distinct().order_by('bisp_type')),
    })


# ── Map Data ──────────────────────────────────────────────────

@login_required(login_url='login')
def map_data(request):
    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    key           = request.GET.get('key')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')
    bisp_type     = request.GET.get('bisp_type')  # ── FIX 2: was missing, caused NameError ──

    qs = get_scoped_qs(request.user)

    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(pta_district=pta)
    if key:           qs = qs.filter(key=key)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    if bisp_type:     qs = qs.filter(bisp_type=bisp_type)
    if month:         qs = qs.filter(month=month)
    if year:          qs = qs.filter(year=year)

    qs = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    franchises = qs.values(
        'key', 'latitude', 'longitude', 'region', 'pta_district', 'technology', 'site_status'
    ).annotate(
        total_revenue=Sum('tot_revn_amt'),
        site_count=Count('id'),
        total_activations=Sum('act_90d'),
    ).order_by('key')

    markers = []
    for f in franchises:
        lat = f['latitude']
        lng = f['longitude']
        if lat is None or lng is None: continue
        try:
            lat = float(lat); lng = float(lng)
        except: continue
        if not (20 <= lat <= 40 and 60 <= lng <= 80): continue
        def safe(val):
            if val is None: return 0
            try: return float(val)
            except: return 0
        markers.append({
            'key':         f['key'] or 'Unknown',
            'lat':         lat,
            'lng':         lng,
            'region':      f['region'] or '',
            'district':    f['pta_district'] or '',
            'technology':  f['technology'] or '',
            'site_status': f['site_status'] or '',
            'revenue':     safe(f['total_revenue']),
            'activations': safe(f['total_activations']),
        })

    return JsonResponse({'markers': markers, 'total': len(markers)})


# ── Dashboard Data ────────────────────────────────────────────

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count
from .models import SiteData, UserProfile
from collections import defaultdict
import os


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ── Role helpers ──────────────────────────────────────────────

def get_scoped_qs(user):
    profile = get_or_create_profile(user)
    qs = SiteData.objects.all()
    if profile.category == 'BU' and profile.user_business_unit:
        qs = qs.filter(business_unit=profile.user_business_unit)
    elif profile.category == 'ARM' and profile.user_arm:
        qs = qs.filter(arm=profile.user_arm)
    return qs


def get_locked_filters(user):
    profile = get_or_create_profile(user)
    locked = {
        'category': profile.category,
        'region':   {'locked': False},
        'bu':       {'locked': False},
    }
    if profile.category == 'BU':
        locked['bu'] = {'locked': True, 'value': profile.user_business_unit}
    elif profile.category == 'ARM':
        locked['region'] = {'locked': True, 'value': ''}
        locked['bu']     = {'locked': True, 'value': ''}
    return locked


# ── Auth ──────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            messages.error(request, 'No account found with that email address.')
            return render(request, 'dashboard/login.html')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Incorrect password. Please try again.')
        return render(request, 'dashboard/login.html')
    return render(request, 'dashboard/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    errors = {}
    form_data = {}
    if request.method == 'POST':
        full_name        = request.POST.get('full_name', '').strip()
        phone            = request.POST.get('phone', '').strip()
        email            = request.POST.get('email', '').strip().lower()
        password         = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        form_data = {'full_name': full_name, 'phone': phone, 'email': email}
        if not email.endswith('@ptclgroup.com'):
            errors['email'] = 'Only @ptclgroup.com email addresses are allowed.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists.'
        if len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        if password != confirm_password:
            errors['confirm_password'] = 'Passwords do not match.'
        if not full_name:
            errors['full_name'] = 'Full name is required.'
        if not phone:
            errors['phone'] = 'Phone number is required.'
        if not errors:
            username = email.split('@')[0]
            base = username; c = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{c}"; c += 1
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=full_name.split()[0] if full_name else '',
                last_name=' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else '',
            )
            profile = get_or_create_profile(user)
            profile.phone = phone
            profile.save()
            auth_login(request, user)
            return redirect('dashboard')
    return render(request, 'dashboard/register.html', {'errors': errors, 'form_data': form_data})


def logout_view(request):
    auth_logout(request)
    return redirect('login')


# ── Profile ───────────────────────────────────────────────────

@login_required(login_url='login')
def profile_view(request):
    profile = get_or_create_profile(request.user)
    if request.method == 'POST':
        action = request.POST.get('action', 'profile')
        if action == 'profile':
            request.user.first_name = request.POST.get('first_name', '').strip()
            request.user.last_name  = request.POST.get('last_name', '').strip()
            request.user.save()
            profile.phone       = request.POST.get('phone', '').strip()
            profile.designation = request.POST.get('designation', '').strip()
            profile.department  = request.POST.get('department', '').strip()
            profile.region      = request.POST.get('region', '').strip()
            profile.employee_id = request.POST.get('employee_id', '').strip()
            profile.bio         = request.POST.get('bio', '').strip()[:300]
            if 'picture' in request.FILES:
                pic = request.FILES['picture']
                if pic.content_type.startswith('image/'):
                    if profile.picture:
                        try:
                            if os.path.isfile(profile.picture.path):
                                os.remove(profile.picture.path)
                        except Exception:
                            pass
                    profile.picture = pic
                else:
                    messages.error(request, 'Please upload a valid image file.')
                    return redirect('profile')
            profile.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
        elif action == 'password':
            current_pw = request.POST.get('current_password', '')
            new_pw     = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_new_password', '')
            if not request.user.check_password(current_pw):
                messages.error(request, 'Current password is incorrect.')
            elif len(new_pw) < 8:
                messages.error(request, 'New password must be at least 8 characters.')
            elif new_pw != confirm_pw:
                messages.error(request, 'New passwords do not match.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully!')
            return redirect('profile')
        elif action == 'remove_picture':
            if profile.picture:
                try:
                    if os.path.isfile(profile.picture.path):
                        os.remove(profile.picture.path)
                except Exception:
                    pass
                profile.picture = None
                profile.save()
            messages.success(request, 'Profile picture removed.')
            return redirect('profile')
    return render(request, 'dashboard/profile.html', {'profile': profile})


# ── Dashboard ─────────────────────────────────────────────────

@login_required(login_url='login')
def dashboard(request):
    profile = get_or_create_profile(request.user)
    locked  = get_locked_filters(request.user)
    return render(request, 'dashboard/index.html', {'profile': profile, 'locked': locked})


# ── Filters ───────────────────────────────────────────────────

@login_required(login_url='login')
def filter_options(request):
    region = request.GET.get('region')
    pta    = request.GET.get('pta_district')

    base = get_scoped_qs(request.user)

    pta_qs = base
    if region:
        pta_qs = pta_qs.filter(region=region)

    fr_qs = base
    if region:
        fr_qs = fr_qs.filter(region=region)
    if pta:
        fr_qs = fr_qs.filter(pta_district=pta)

    years_list  = list(base.filter(year__isnull=False).values_list('year', flat=True).distinct().order_by('year'))
    latest_year = max(years_list) if years_list else None

    return JsonResponse({
        'regions':        list(base.filter(region__isnull=False).exclude(region='').values_list('region', flat=True).distinct().order_by('region')),
        'pta_districts':  list(pta_qs.filter(pta_district__isnull=False).exclude(pta_district='').values_list('pta_district', flat=True).distinct().order_by('pta_district')),
        'franchises':     list(fr_qs.filter(franchise__isnull=False).exclude(franchise='').values_list('franchise', flat=True).distinct().order_by('franchise')),
        'technologies':   list(base.filter(technology__isnull=False).exclude(technology='').values_list('technology', flat=True).distinct().order_by('technology')),
        'business_units': list(base.filter(business_unit__isnull=False).exclude(business_unit='').values_list('business_unit', flat=True).distinct().order_by('business_unit')),
        'site_statuses':  list(base.filter(site_status__isnull=False).exclude(site_status='').values_list('site_status', flat=True).distinct().order_by('site_status')),
        'months':         list(base.filter(month__isnull=False).values_list('month', flat=True).distinct().order_by('month')),
        'years':          years_list,
        'latest_year':    latest_year,
        # ── FIX 1: Return actual bisp_type values from DB so dropdown uses exact strings ──
        'bisp_types':     list(base.filter(bisp_type__isnull=False).exclude(bisp_type='').values_list('bisp_type', flat=True).distinct().order_by('bisp_type')),
    })


# ── Map Data ──────────────────────────────────────────────────

@login_required(login_url='login')
def map_data(request):
    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    key           = request.GET.get('key')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')
    bisp_type     = request.GET.get('bisp_type')  # ── FIX 2: was missing, caused NameError ──

    qs = get_scoped_qs(request.user)

    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(pta_district=pta)
    if key:           qs = qs.filter(key=key)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    if bisp_type:     qs = qs.filter(bisp_type=bisp_type)
    if month:         qs = qs.filter(month=month)
    if year:          qs = qs.filter(year=year)

    qs = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    franchises = qs.values(
        'key', 'latitude', 'longitude', 'region', 'pta_district', 'technology', 'site_status'
    ).annotate(
        total_revenue=Sum('tot_revn_amt'),
        site_count=Count('id'),
        total_activations=Sum('act_90d'),
    ).order_by('key')

    markers = []
    for f in franchises:
        lat = f['latitude']
        lng = f['longitude']
        if lat is None or lng is None: continue
        try:
            lat = float(lat); lng = float(lng)
        except: continue
        if not (20 <= lat <= 40 and 60 <= lng <= 80): continue
        def safe(val):
            if val is None: return 0
            try: return float(val)
            except: return 0
        markers.append({
            'key':         f['key'] or 'Unknown',
            'lat':         lat,
            'lng':         lng,
            'region':      f['region'] or '',
            'district':    f['pta_district'] or '',
            'technology':  f['technology'] or '',
            'site_status': f['site_status'] or '',
            'revenue':     safe(f['total_revenue']),
            'activations': safe(f['total_activations']),
        })

    return JsonResponse({'markers': markers, 'total': len(markers)})


# ── Dashboard Data ────────────────────────────────────────────
@login_required(login_url='login')
def dashboard_data(request):
    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    franchise     = request.GET.get('franchise')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')
    bisp_type     = request.GET.get('bisp_type')  # exact DB string e.g. 'BISP', 'Non BISP'

    role_base = get_scoped_qs(request.user)

    # ── Fully filtered queryset — used for KPIs, charts, and growth ──
    qs = role_base
    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(pta_district=pta)
    if franchise:     qs = qs.filter(franchise=franchise)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    if bisp_type:     qs = qs.filter(bisp_type=bisp_type)

    # ── Growth base — same as qs but WITHOUT month/year filters ──
    growth_base = qs

    # Apply month/year only to the main qs
    qs_kpi = qs
    if month: qs_kpi = qs_kpi.filter(month=month)
    if year:  qs_kpi = qs_kpi.filter(year=year)

    def safe(v):
        return float(v) if v is not None else 0

    def growth_pct(curr, prev):
        if prev == 0:
            return 100.0 if curr != 0 else 0.0
        return round(((curr - prev) / prev) * 100, 1)

    # KPIs — fully filtered (including month/year)
    kpis = qs_kpi.aggregate(
        total_revenue=Sum('tot_revn_amt'),
        total_activations=Sum('act_90d'),
        total_net_add=Sum('net_add'),
        total_recharge=Sum('total_recharge'),
        avg_revenue=Avg('tot_revn_amt'),
        total_sites=Count('key'),
        total_churn=Sum('gross_churn'),
        total_hvc=Sum('hvc_base'),
        total_base_90d=Sum('act_90d'),
        total_base_4g=Sum('act_90d_4g'),
        total_digi_recharge=Sum('digi_recharge'),
        total_conv_recharge=Sum('conventional_recharge'),
        total_base_30d=Sum('act_30d'),
    )
    # ARPU = total revenue / total activations (derived, not a DB field)
    _rev = safe(kpis.get('total_revenue'))
    _act = safe(kpis.get('total_activations'))
    kpis['total_arpu'] = (_rev / _act) if _act else 0

    # 4G Penetration = 4G base / 90D base
    _b90 = safe(kpis.get('total_base_90d'))
    _b4g = safe(kpis.get('total_base_4g'))
    kpis['penetration_4g'] = ((_b4g / _b90) * 100) if _b90 else 0

    # ── Growth — anchored to filtered scope ──
    growth = {}
    if year:
        latest_period = (
            growth_base.filter(year=year)
            .order_by('-month')
            .values('year', 'month')
            .first()
        )
    else:
        latest_period = (
            growth_base.order_by('-year', '-month')
            .values('year', 'month')
            .first()
        )

    if latest_period:
        latest_year  = latest_period['year']
        latest_month = latest_period['month']
        prev_year    = latest_year - 1
        mom_month    = latest_month - 1 if latest_month > 1 else 12
        mom_year     = latest_year      if latest_month > 1 else prev_year

        agg_kwargs = dict(
            total_revenue=Sum('tot_revn_amt'),
            total_activations=Sum('act_90d'),
            total_net_add=Sum('net_add'),
            total_recharge=Sum('total_recharge'),
            total_churn=Sum('gross_churn'),
            total_hvc=Sum('hvc_base'),
            total_sites=Count('key'),
            avg_revenue=Avg('tot_revn_amt'),
            total_base_90d=Sum('act_90d'),
            total_base_4g=Sum('act_90d_4g'),
            total_digi_recharge=Sum('digi_recharge'),
            total_conv_recharge=Sum('conventional_recharge'),
            total_base_30d=Sum('act_30d'),
        )

        ytd_curr_agg = growth_base.filter(year=latest_year, month__lte=latest_month).aggregate(**agg_kwargs)
        ytd_prev_agg = growth_base.filter(year=prev_year,   month__lte=latest_month).aggregate(**agg_kwargs)
        yoy_curr_agg = growth_base.filter(year=latest_year, month=latest_month).aggregate(**agg_kwargs)
        yoy_prev_agg = growth_base.filter(year=prev_year,   month=latest_month).aggregate(**agg_kwargs)
        mom_prev_agg = growth_base.filter(year=mom_year,    month=mom_month).aggregate(**agg_kwargs)

        # ── DEBUG ──
        MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        print("\n" + "="*70)
        print("  GROWTH CALCULATION — PERIOD ANCHORS (filtered scope)")
        print("="*70)
        print(f"  Filters: region={region} pta={pta} franchise={franchise} bu={business_unit} bisp={bisp_type}")
        print(f"  Latest period  : {MONTH_NAMES[latest_month-1]} {latest_year}  (month {latest_month})")
        print(f"  YTD compares   : Jan–{MONTH_NAMES[latest_month-1]} {latest_year}  vs  Jan–{MONTH_NAMES[latest_month-1]} {prev_year}")
        print(f"  YOY compares   : {MONTH_NAMES[latest_month-1]} {latest_year}       vs  {MONTH_NAMES[latest_month-1]} {prev_year}")
        print(f"  MOM compares   : {MONTH_NAMES[latest_month-1]} {latest_year}       vs  {MONTH_NAMES[mom_month-1]} {mom_year}")
        print("="*70)

        # Derived-metric helpers
        def arpu_from(agg):
            rev = safe(agg.get('total_revenue'))
            act = safe(agg.get('total_activations'))
            return (rev / act) if act else 0

        def pen_from(agg):
            b90 = safe(agg.get('total_base_90d'))
            b4g = safe(agg.get('total_base_4g'))
            return ((b4g / b90) * 100) if b90 else 0

        # Build list of metrics — includes derived ARPU and 4G penetration
        growth_metrics = list(agg_kwargs.keys()) + ['total_arpu', 'penetration_4g']

        for k in growth_metrics:
            if k == 'total_arpu':
                ytd_curr = arpu_from(ytd_curr_agg)
                ytd_prev = arpu_from(ytd_prev_agg)
                yoy_curr = arpu_from(yoy_curr_agg)
                yoy_prev = arpu_from(yoy_prev_agg)
                mom_prev = arpu_from(mom_prev_agg)
            elif k == 'penetration_4g':
                ytd_curr = pen_from(ytd_curr_agg)
                ytd_prev = pen_from(ytd_prev_agg)
                yoy_curr = pen_from(yoy_curr_agg)
                yoy_prev = pen_from(yoy_prev_agg)
                mom_prev = pen_from(mom_prev_agg)
            else:
                ytd_curr = safe(ytd_curr_agg.get(k))
                ytd_prev = safe(ytd_prev_agg.get(k))
                yoy_curr = safe(yoy_curr_agg.get(k))
                yoy_prev = safe(yoy_prev_agg.get(k))
                mom_prev = safe(mom_prev_agg.get(k))
            mom_curr = yoy_curr

            ytd_pct = growth_pct(ytd_curr, ytd_prev)
            yoy_pct = growth_pct(yoy_curr, yoy_prev)
            mom_pct = growth_pct(mom_curr, mom_prev)

            label = k.replace('_', ' ').upper()
            print(f"  [{label:<22}] YTD {ytd_pct:+6.1f}%  YOY {yoy_pct:+6.1f}%  MOM {mom_pct:+6.1f}%")

            growth[k] = {
                'ytd_pct': ytd_pct,
                'yoy_pct': yoy_pct,
                'mtd_pct': mom_pct,
            }

        print("="*70 + "\n")

    # ── Chart data — all on fully filtered qs_kpi ────────────────
    def sl(lst, key):
        return [safe(i[key]) for i in lst]

    revenue_by_region = list(qs_kpi.exclude(region__isnull=True).values('region').annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue')[:10])
    act_by_tech       = list(qs_kpi.exclude(technology__isnull=True).values('technology').annotate(activations=Sum('act_90d')).order_by('-activations'))
    rev_by_bu         = list(qs_kpi.exclude(business_unit__isnull=True).values('business_unit').annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue'))
    recharge          = qs_kpi.aggregate(
        prepaid_digital=Sum('prepaid_dgtl_amount'),
        postpaid_digital=Sum('postpaid_dgtl_amount'),
        conventional=Sum('conventional_recharge'),
        digi=Sum('digi_recharge'),
    )

    # Net Add Trend
    net_qs = (
        qs_kpi.exclude(net_add__isnull=True)
        .values('year', 'month')
        .annotate(value=Sum('net_add'))
        .order_by('year', 'month')
    )
    months_range = list(range(1, 13))
    years_net    = sorted(set(r['year'] for r in net_qs))
    series_net   = defaultdict(lambda: [0] * 12)
    for r in net_qs:
        series_net[r['year']][r['month'] - 1] = safe(r['value'])
    net_add_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_net[y]} for y in years_net],
    }

    traffic          = list(qs_kpi.exclude(region__isnull=True).values('region').annotate(outgoing=Sum('minutes_outgoing'), incoming=Sum('minutes_incoming')).order_by('-outgoing')[:8])
    data_vol         = list(qs_kpi.exclude(technology__isnull=True).values('technology').annotate(volume=Sum('volume_gbs')).order_by('-volume'))
    site_status_data = list(qs_kpi.exclude(site_status__isnull=True).values('site_status').annotate(count=Count('key')).order_by('-count'))
    top_districts    = list(qs_kpi.exclude(pta_district__isnull=True).values('pta_district').annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue'))

    # Avg Daily Active Trend
    avg_qs = (
        qs_kpi.exclude(avg_dly_act__isnull=True)
        .values('year', 'month')
        .annotate(value=Sum('avg_dly_act'))
        .order_by('year', 'month')
    )
    years_avg  = sorted(set(r['year'] for r in avg_qs))
    series_avg = defaultdict(lambda: [0] * 12)
    for r in avg_qs:
        series_avg[r['year']][r['month'] - 1] = safe(r['value'])
    avg_daily_active_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_avg[y]} for y in years_avg],
    }

    # Churn vs FCA — monthly
    churn_by_month   = []
    revival_by_month = []
    for m in months_range:
        md = qs_kpi.filter(month=m)
        churn_by_month.append(safe(md.aggregate(val=Sum('gross_churn'))['val']))
        revival_by_month.append(safe(md.aggregate(val=Sum('fca'))['val']))
    churn_revival_by_month = {
        'labels':  months_range,
        'churn':   churn_by_month,
        'revival': revival_by_month,
    }

    churn_revival = list(
        qs_kpi.exclude(region__isnull=True)
        .values('region')
        .annotate(churn=Sum('gross_churn'), revival=Sum('fca'))
        .order_by('-churn')[:8]
    )

    return JsonResponse({
        'kpis':   {k: safe(v) for k, v in kpis.items()},
        'growth': growth,
        'revenue_by_region': {'labels': [r['region'] for r in revenue_by_region],    'values': sl(revenue_by_region, 'revenue')},
        'act_by_tech':       {'labels': [r['technology'] for r in act_by_tech],       'values': sl(act_by_tech, 'activations')},
        'rev_by_bu':         {'labels': [r['business_unit'] for r in rev_by_bu],      'values': sl(rev_by_bu, 'revenue')},
        'recharge':          {
            'labels': ['Prepaid Digital', 'Postpaid Digital', 'Conventional', 'Digi Recharge'],
            'values': [safe(recharge['prepaid_digital']), safe(recharge['postpaid_digital']), safe(recharge['conventional']), safe(recharge['digi'])],
        },
        'net_add_region':         net_add_chart,
        'traffic':                {'labels': [r['region'] for r in traffic], 'outgoing': sl(traffic, 'outgoing'), 'incoming': sl(traffic, 'incoming')},
        'data_vol':               {'labels': [r['technology'] for r in data_vol], 'values': sl(data_vol, 'volume')},
        'site_status':            {'labels': [r['site_status'] for r in site_status_data], 'values': [r['count'] for r in site_status_data]},
        'top_districts':          {'labels': [r['pta_district'] for r in top_districts], 'values': sl(top_districts, 'revenue')},
        'churn_revival':          {'labels': [r['region'] for r in churn_revival], 'churn': sl(churn_revival, 'churn'), 'revival': sl(churn_revival, 'revival')},
        'churn_revival_by_month': churn_revival_by_month,
        'avg_daily_active':       avg_daily_active_chart,
    })


@login_required(login_url='login')
def nearby_sites(request):
    """Return the 3 nearest sites to a given lat/lng based on Haversine distance.
    Respects the user's role-scoped queryset."""
    try:
        user_lat = float(request.GET.get('lat'))
        user_lng = float(request.GET.get('lng'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid or missing lat/lng'}, status=400)

    role_base = get_scoped_qs(request.user)

    # Find latest period in scope to show fresh data
    latest = role_base.order_by('-year', '-month').values('year', 'month').first()
    if latest:
        qs = role_base.filter(year=latest['year'], month=latest['month'])
    else:
        qs = role_base

    # Pull only sites with valid coordinates — keep payload light
    candidates = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True).values(
        'key', 'latitude', 'longitude', 'region', 'pta_district', 'franchise',
        'business_unit', 'technology', 'site_status', 'tot_revn_amt',
        'act_90d', 'act_90d_4g', 'net_add', 'gross_churn', 'hvc_base',
        'total_recharge', 'year', 'month',
    )

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0  # Earth radius in km
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    scored = []
    for s in candidates:
        try:
            d = haversine_km(user_lat, user_lng, float(s['latitude']), float(s['longitude']))
        except (TypeError, ValueError):
            continue
        scored.append((d, s))

    scored.sort(key=lambda x: x[0])
    top3 = scored[:3]

    def safe(v):
        return float(v) if v is not None else 0

    results = []
    for dist, s in top3:
        results.append({
            'key':           s['key'] or 'Unknown',
            'distance_km':   round(dist, 2),
            'latitude':      float(s['latitude']),
            'longitude':     float(s['longitude']),
            'region':        s['region'] or '—',
            'pta_district':  s['pta_district'] or '—',
            'franchise':     s['franchise'] or '—',
            'business_unit': s['business_unit'] or '—',
            'technology':    s['technology'] or '—',
            'site_status':   s['site_status'] or '—',
            'revenue':       safe(s['tot_revn_amt']),
            'act_90d':       safe(s['act_90d']),
            'act_90d_4g':    safe(s['act_90d_4g']),
            'net_add':       safe(s['net_add']),
            'gross_churn':   safe(s['gross_churn']),
            'hvc_base':      safe(s['hvc_base']),
            'total_recharge': safe(s['total_recharge']),
            'period':        f"{s['month']}/{s['year']}" if s['year'] else '—',
        })

    return JsonResponse({
        'user_location': {'lat': user_lat, 'lng': user_lng},
        'count':         len(results),
        'sites':         results,
    })