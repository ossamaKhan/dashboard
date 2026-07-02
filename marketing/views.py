from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum, Avg, Count, Max, F, Value, DecimalField, Case, When, FloatField, Q
from django.db.models.functions import Coalesce
from django.contrib.auth.models import User
from .models import SiteData, UserProfile, ChatMessage, UserLoginLog, ChatRoom, PushSubscription
from django.http import JsonResponse
from collections import defaultdict
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
import math
import os
import hashlib
import json as _json
from django.core.cache import cache


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ── Role helpers ──────────────────────────────────────────────

def get_scoped_qs(user):
    profile = get_or_create_profile(user)
    qs = SiteData.objects.all()
    if profile.category == 'BU' and profile.user_business_unit:
        bu = profile.user_business_unit.split(',')[0].strip()
        if bu:
            qs = qs.filter(business_unit=bu)
    elif profile.category == 'ARM' and profile.user_arm:
        qs = qs.filter(arm=profile.user_arm)
    return qs


def get_locked_filters(user):
    profile = get_or_create_profile(user)
    locked = {
        'category': profile.category,
        'region':   {'locked': False, 'value': None},
        'bu':       {'locked': False, 'value': None},
        'arm':      {'locked': False, 'value': None},
    }
    if profile.category == 'BU':
        _bus = [b.strip() for b in profile.user_business_unit.split(',') if b.strip()]
        locked['bu'] = {'locked': True, 'value': _bus[0] if _bus else ''}
    elif profile.category == 'ARM':
        arm_val = profile.user_arm or ''
        # Derive BU from SiteData based on ARM
        from marketing.models import SiteData, UserProfile, ChatMessage, UserLoginLog, ChatRoom, PushSubscription
        bu_val = (SiteData.objects.filter(arm=arm_val)
                  .values_list('business_unit', flat=True).first()) or ''
        locked['region'] = {'locked': True,  'value': 'Central B'}
        locked['bu']     = {'locked': True,  'value': bu_val}
        locked['arm']    = {'locked': True,  'value': arm_val}
    return locked


# ── Auth ──────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# Chat helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _get_or_create_region_room():
    """Get or create the main region-wide channel."""
    room, created = ChatRoom.objects.get_or_create(
        slug='region',
        defaults={'name': 'Central B — All Teams', 'room_type': 'region'}
    )
    if created:
        # Add all users with Region or Admin category
        from django.contrib.auth.models import User as _User
        for u in _User.objects.filter(
            profile__category__in=['Region']
        ).select_related('profile'):
            room.members.add(u)
        # Also add all staff/admin users
        for u in _User.objects.filter(is_staff=True):
            room.members.add(u)
    return room


def _ensure_rooms_exist():
    """
    Create / sync:
    1. One region-wide room  — all users
    2. One room per BU       — all ARM/BU users in that BU + all Region users
    """
    from django.contrib.auth.models import User as _User
    from django.utils.text import slugify

    region_users = list(_User.objects.filter(
        profile__category='Region'
    ).select_related('profile'))
    staff_users  = list(_User.objects.filter(is_staff=True))
    arm_users    = list(_User.objects.filter(
        profile__category='ARM'
    ).select_related('profile'))
    bu_users     = list(_User.objects.filter(
        profile__category='BU'
    ).select_related('profile'))

    # ── 1. Region-wide room ───────────────────────────────────────────────
    region_room = _get_or_create_region_room()
    for u in region_users + staff_users + arm_users + bu_users:
        region_room.members.add(u)

    # ── 2. BU-level rooms (one per distinct BU in UserProfile) ───────────
    from marketing.models import SiteData
    bus = list(SiteData.objects.exclude(
        business_unit__isnull=True
    ).exclude(business_unit='').values_list(
        'business_unit', flat=True
    ).distinct())

    for bu in bus:
        slug = 'bu-' + slugify(bu)[:94]
        room, _ = ChatRoom.objects.get_or_create(
            slug=slug,
            defaults={
                'name':      f"{bu} — Team",
                'room_type': 'rd',
            }
        )
        # Add Region + staff users
        for u in region_users + staff_users:
            room.members.add(u)
        # Add BU users whose BU matches
        for u in bu_users:
            if getattr(u.profile, 'user_business_unit', '') == bu:
                room.members.add(u)
        # Add ARM users whose ARM is in this BU
        for u in arm_users:
            arm_val = getattr(u.profile, 'user_arm', '')
            if arm_val and SiteData.objects.filter(arm=arm_val, business_unit=bu).exists():
                room.members.add(u)


def _send_push_to_room(room, sender, text_preview):
    """Fire-and-forget Web Push to all room members except sender."""
    try:
        from pywebpush import webpush, WebPushException
        from django.conf import settings
        import json, threading

        vapid_private = getattr(settings, 'VAPID_PRIVATE_KEY', '')
        vapid_claims  = getattr(settings, 'VAPID_CLAIMS', {})
        if not vapid_private:
            return  # Push not configured

        subs = PushSubscription.objects.filter(
            user__in=room.members.all()
        ).exclude(user=sender)

        preview = text_preview[:60] + ('…' if len(text_preview) > 60 else '')
        sender_name = sender.get_full_name() or sender.username

        def _send():
            for sub in subs:
                try:
                    webpush(
                        subscription_info={
                            "endpoint": sub.endpoint,
                            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                        },
                        data=json.dumps({
                            "title": f"💬 {sender_name}",
                            "body":  preview,
                            "room":  room.slug,
                        }),
                        vapid_private_key=vapid_private,
                        vapid_claims=vapid_claims,
                    )
                except WebPushException:
                    sub.delete()  # Subscription expired
                except Exception:
                    pass

        threading.Thread(target=_send, daemon=True).start()
    except ImportError:
        pass  # pywebpush not installed — silent fail


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
            try:
                from login_tracker import record_login
                record_login(request, user)
            except Exception:
                pass   # never block login
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


@login_required(login_url='login')
def base_page(request):
    profile = get_or_create_profile(request.user)
    locked  = get_locked_filters(request.user)
    return render(request, 'dashboard/base_page.html', {'profile': profile, 'locked': locked})


@login_required(login_url='login')
def revenue_page(request):
    profile = get_or_create_profile(request.user)
    locked  = get_locked_filters(request.user)
    return render(request, 'dashboard/revenue_page.html', {'profile': profile, 'locked': locked})


@login_required(login_url='login')
def site_map_page(request):
    profile = get_or_create_profile(request.user)
    locked  = get_locked_filters(request.user)
    return render(request, 'dashboard/site_map.html', {'profile': profile, 'locked': locked})


@login_required(login_url='login')
def performance_ranking_page(request):
    profile = get_or_create_profile(request.user)
    locked  = get_locked_filters(request.user)
    return render(request, 'dashboard/performance_ranking.html', {'profile': profile, 'locked': locked})


# ── Filters ───────────────────────────────────────────────────
# CHANGED: franchise dropdown now filters by business_unit instead of pta_district.
# The frontend sends ?region=X&business_unit=Y; franchises are scoped to that BU.

@login_required(login_url='login')
def filter_options(request):
    region        = request.GET.get('region')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')

    base = get_scoped_qs(request.user)

    arm_qs = base
    if region:        arm_qs = arm_qs.filter(region=region)
    if business_unit: arm_qs = arm_qs.filter(business_unit=business_unit)

    fr_qs = arm_qs
    if arm:           fr_qs = fr_qs.filter(arm=arm)

    years_list  = list(base.filter(year__isnull=False).values_list('year', flat=True).distinct().order_by('year'))
    latest_year = max(years_list) if years_list else None

    return JsonResponse({
        'regions':        list(base.filter(region__isnull=False).exclude(region='').values_list('region', flat=True).distinct().order_by('region')),
        'arms':           list(arm_qs.filter(arm__isnull=False).exclude(arm='').values_list('arm', flat=True).distinct().order_by('arm')),
        'franchises':     list(fr_qs.filter(franchise__isnull=False).exclude(franchise='').values_list('franchise', flat=True).distinct().order_by('franchise')),
        'technologies':   list(base.filter(technology__isnull=False).exclude(technology='').values_list('technology', flat=True).distinct().order_by('technology')),
        'business_units': list(base.filter(business_unit__isnull=False).exclude(business_unit='').values_list('business_unit', flat=True).distinct().order_by('business_unit')),
        'site_statuses':  list(base.filter(site_status__isnull=False).exclude(site_status='').values_list('site_status', flat=True).distinct().order_by('site_status')),
        'months':         list(base.filter(month__isnull=False).values_list('month', flat=True).distinct().order_by('month')),
        'years':          years_list,
        'latest_year':    latest_year,
        'bisp_types':     [],
    })


# ── Map Data ──────────────────────────────────────────────────

@login_required(login_url='login')
def map_data(request):
    from django.core.cache import cache

    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    franchise     = request.GET.get('franchise')
    arm           = request.GET.get('arm')
    key           = request.GET.get('key')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')

    # ── Cache key ──────────────────────────────────────────────────────────
    # Hashed rather than built from raw values — region names like
    # "Central B" contain spaces, which some cache backends (real
    # memcached clients in particular) reject outright rather than just
    # warning about, unlike Django's default local-dev cache. Matches the
    # hashing style already used for dashboard_data()'s cache key below.
    _map_cache_params = {
        'uid': request.user.id, 'r': region, 'bu': business_unit, 'a': arm,
        'f': franchise, 'k': key, 't': technology, 'ss': site_status,
        'm': month, 'y': year,
    }
    ck = 'mapdata_v3_' + hashlib.md5(
        _json.dumps(_map_cache_params, sort_keys=True).encode()
    ).hexdigest()
    cached = cache.get(ck)
    if cached is not None:
        return JsonResponse(cached, safe=False)

    qs = get_scoped_qs(request.user)
    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(commercial_district=pta)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise=franchise)
    if key:           qs = qs.filter(key=key)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    if month:         qs = qs.filter(month=int(month))
    if year:          qs = qs.filter(year=int(year))
    qs = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    # ── Closing month for stock fields ─────────────────────────────────────
    _latest = qs.aggregate(ly=Max('year'), lm=Max('month'))
    _ly, _lm = _latest.get('ly'), _latest.get('lm')
    if _ly and _lm:
        _stock_ann = {
            'total_activations': Max(Case(When(year=_ly, month=_lm, then='act_90d'),    default=None, output_field=FloatField())),
            'total_base_4g':     Max(Case(When(year=_ly, month=_lm, then='act_90d_4g'), default=None, output_field=FloatField())),
            'total_base_30d':    Max(Case(When(year=_ly, month=_lm, then='act_30d'),    default=None, output_field=FloatField())),
            'total_hvc':         Max(Case(When(year=_ly, month=_lm, then='hvc_base'),   default=None, output_field=FloatField())),
            'total_evc':         Max(Case(When(year=_ly, month=_lm, then='evc_retailer'), default=None, output_field=FloatField())),
            'total_bvs':         Max(Case(When(year=_ly, month=_lm, then='bvs_retailer'), default=None, output_field=FloatField())),
            'total_handset_4g':  Max(Case(When(year=_ly, month=_lm, then='handset_4g'), default=None, output_field=FloatField())),
        }
    else:
        _stock_ann = {
            'total_activations': Max('act_90d'),
            'total_base_4g':     Max('act_90d_4g'),
            'total_base_30d':    Max('act_30d'),
            'total_hvc':         Max('hvc_base'),
            'total_evc':         Max('evc_retailer'),
            'total_bvs':         Max('bvs_retailer'),
            'total_handset_4g':  Max('handset_4g'),
        }

    franchises = qs.values(
        'key', 'latitude', 'longitude', 'region', 'commercial_district',
        'technology', 'site_status', 'business_unit', 'franchise', 'arm'
    ).annotate(
        total_revenue=Sum('tot_revn_amt'),
        site_count=Count('id'),
        total_net_add=Sum('net_add'),
        total_gross_churn=Sum('gross_churn'),
        total_revival=Sum('tot_revival'),
        total_fca=Sum('fca'),
        total_mnp=Sum('mnp_fca'),
        total_conv_recharge=Sum('conventional_recharge'),
        total_prepaid_digi=Sum('prepaid_dgtl_amount'),
        total_postpaid_digi=Sum('postpaid_dgtl_amount'),
        total_m0_revenue=Sum('m0_revn'),
        total_volume_gbs=Sum('volume_gbs'),
        total_data_4g_gbs=Sum('data_ntwrk_vol_4g'),
        total_avg_dly_act=Sum('avg_dly_act'),
        **_stock_ann,
    ).order_by('key')

    def safe(val):
        if val is None: return 0
        try: return float(val)
        except: return 0

    markers = []
    bu_points = defaultdict(list)
    seen_keys = set()

    for f in franchises:
        lat = f['latitude']; lng = f['longitude']
        if lat is None or lng is None:
            continue
        try:
            lat = float(lat); lng = float(lng)
        except:
            continue
        if not (20 <= lat <= 40 and 60 <= lng <= 80):
            continue

        bu = f['business_unit'] if f['business_unit'] else 'Unknown'
        digi = safe(f.get('total_prepaid_digi')) + safe(f.get('total_postpaid_digi'))
        markers.append({
            'key':           f['key'] or 'Unknown',
            'lat':           lat,
            'lng':           lng,
            'region':        f['region'] or '',
            'district':      f['commercial_district'] or '',
            'franchise':     f['franchise'] or '',
            'arm':           f['arm'] or '',
            'technology':    f['technology'] or '',
            'site_status':   f['site_status'] or '',
            'business_unit': bu,
            'revenue':       safe(f['total_revenue']),
            'net_add':       safe(f.get('total_net_add')),
            'churn':         safe(f.get('total_gross_churn')),
            'revival':       safe(f.get('total_revival')),
            'fca':           safe(f.get('total_fca')),
            'mnp':           safe(f.get('total_mnp')),
            'conv_recharge': safe(f.get('total_conv_recharge')),
            'digi_recharge': digi,
            'total_recharge': safe(f.get('total_conv_recharge')) + digi,
            'm0_revenue':    safe(f.get('total_m0_revenue')),
            'volume_gbs':    safe(f.get('total_volume_gbs')),
            'data_4g_gbs':   safe(f.get('total_data_4g_gbs')),
            'avg_dly_act':   safe(f.get('total_avg_dly_act')),
            'activations':   safe(f['total_activations']),
            'base_4g':       safe(f.get('total_base_4g')),
            'base_30d':      safe(f.get('total_base_30d')),
            'hvc':           safe(f.get('total_hvc')),
            'evc_base':      safe(f.get('total_evc')),
            'bvs_base':      safe(f.get('total_bvs')),
            'handset_4g':    safe(f.get('total_handset_4g')),
        })
        bu_points[bu].append((lng, lat))
        if f['key']:
            seen_keys.add(f['key'])

    def convex_hull(points):
        pts = sorted(set(points))
        if len(pts) < 3:
            return pts
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lower = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]

    bu_boundaries = []
    for bu, pts in bu_points.items():
        if len(set(pts)) < 3:
            continue
        hull = convex_hull(pts)
        if len(hull) < 3:
            continue
        bu_boundaries.append({
            'business_unit': bu,
            'polygon': [[lat, lng] for (lng, lat) in hull],
            'site_count': len(pts),
        })

    payload = {
        'markers':       markers,
        'total':         len(seen_keys),
        'bu_boundaries': bu_boundaries,
    }

    cache.set(ck, payload, 60)  # cache 60 seconds
    return JsonResponse(payload)


def site_search(request):
    """Search for a site by key — returns lat/lng + basic info, ignores data filters."""
    query = (request.GET.get('key') or '').strip()
    if not query:
        return JsonResponse({'error': 'No key provided'}, status=400)

    qs = get_scoped_qs(request.user).exclude(
        latitude__isnull=True).exclude(longitude__isnull=True)

    # Exact match first
    sites = qs.filter(key=query).values(
        'key','latitude','longitude','region','commercial_district',
        'franchise','arm','technology','site_status','business_unit'
    ).distinct()[:5]

    if not sites:
        # Partial match
        sites = qs.filter(key__icontains=query).values(
            'key','latitude','longitude','region','commercial_district',
            'franchise','arm','technology','site_status','business_unit'
        ).distinct()[:10]

    results = []
    seen = set()
    for s in sites:
        k = s['key']
        if k in seen: continue
        seen.add(k)
        try:
            lat = float(s['latitude']); lng = float(s['longitude'])
        except (TypeError, ValueError):
            continue
        if not (20 <= lat <= 40 and 60 <= lng <= 80):
            continue
        results.append({
            'key':           k,
            'lat':           lat,
            'lng':           lng,
            'region':        s['region'] or '',
            'district':      s['commercial_district'] or '',
            'franchise':     s['franchise'] or '',
            'arm':           s['arm'] or '',
            'technology':    s['technology'] or '',
            'site_status':   s['site_status'] or '',
            'business_unit': s['business_unit'] or '',
        })

    return JsonResponse({'sites': results, 'count': len(results)})


# ── KML Export (Google Earth) ─────────────────────────────────

# BU colour palette — mirrors the JS COLORS array in the frontend
_BU_COLORS = [
    'ff2082f5',  # orange   #f58220  (KML is aabbggrr)
    'fffе1dab',  # purple   #AB1DFE
    'ffb1355e',  # purple2  #5E35B1
    'ffd4bc00',  # teal     #00BCD4
    'ff53c800',  # green    #00C853
    'ff0003ff',  # red      #FF3D00
    'ff00d6ff',  # yellow   #FFD600
    'ff8c1ee9',  # magenta  #E91E8C
    'ffff4d7c',  # violet   #7C4DFF
    'ffff9a45',  # amber    #ff9a45
]

def _bu_color(bu_name, color_map={}):
    """Return a stable KML hex colour for a given BU name."""
    if bu_name not in color_map:
        color_map[bu_name] = _BU_COLORS[len(color_map) % len(_BU_COLORS)]
    return color_map[bu_name]


def _fmt(val):
    """Format a number for KML description tables."""
    try:
        n = float(val or 0)
        if n >= 1_000_000_000: return f'{n/1e9:.2f}B'
        if n >= 1_000_000:     return f'{n/1e6:.2f}M'
        if n >= 1_000:         return f'{n/1e3:.1f}K'
        return str(int(round(n)))
    except Exception:
        return '—'


@login_required(login_url='login')
def export_kml(request):
    """
    GET /api/sites.kml/
    Accepts the same filter params as /api/map/ (region, business_unit,
    franchise, site_status, month, year).
    Returns a KML file ready to open in Google Earth Pro.

    Each site is a colour-coded Placemark with a rich HTML description
    showing all KPIs.  A shared StyleMap per BU drives the icon colour.
    """
    region        = request.GET.get('region')
    franchise     = request.GET.get('franchise')
    arm           = request.GET.get('arm')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')

    qs = get_scoped_qs(request.user)
    if region:        qs = qs.filter(region=region)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise=franchise)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)
    if month:         qs = qs.filter(month=month)
    if year:          qs = qs.filter(year=year)

    qs = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    sites = qs.values(
        'key', 'latitude', 'longitude', 'region', 'commercial_district',
        'franchise', 'business_unit', 'technology', 'site_status',
    ).annotate(
        revenue      = Sum('tot_revn_amt'),
        base_90d     = Sum('act_90d'),
        base_4g      = Sum('act_90d_4g'),
        base_30d     = Sum('act_30d'),
        net_add      = Sum('net_add'),
        gross_churn  = Sum('gross_churn'),
        hvc_base     = Sum('hvc_base'),
        evc_retailer = Sum('evc_retailer'),
        bvs_retailer = Sum('bvs_retailer'),
        digi_recharge= Sum('prepaid_dgtl_amount') + Sum('postpaid_dgtl_amount'),
        conv_recharge= Sum('conventional_recharge'),
    ).order_by('business_unit', 'key')

    # ── Collect BUs so we can emit one StyleMap per BU ────────
    bu_set = sorted(set(
        (s['business_unit'] or 'Unknown') for s in sites
    ))

    def row(label, value):
        return (
            f'<tr>'
            f'<td style="color:#888;padding:3px 8px 3px 0;font-size:11px">{label}</td>'
            f'<td style="font-weight:700;font-size:11px;padding:3px 0">{value}</td>'
            f'</tr>'
        )

    def placemark_desc(s):
        bu   = s['business_unit'] or 'Unknown'
        rev  = float(s['revenue']  or 0)
        digi = float(s['digi_recharge'] or 0)
        conv = float(s['conv_recharge'] or 0)
        total_rech = digi + conv
        digi_share = f'{digi/total_rech*100:.1f}%' if total_rech else '—'
        return (
            '<![CDATA['
            '<div style="font-family:Arial,sans-serif;min-width:240px">'
            f'<div style="background:#f58220;color:#fff;padding:8px 12px;'
            f'font-size:13px;font-weight:700;border-radius:6px 6px 0 0">📡 {s["key"] or "Unknown"}</div>'
            '<table style="width:100%;border-collapse:collapse;padding:8px">'
            + row('Business Unit',  bu)
            + row('Region',         s['region'] or '—')
            + row('District',       s['commercial_district'] or '—')
            + row('Franchise',      s['franchise'] or '—')
            + row('Technology',     s['technology'] or '—')
            + row('Status',         s['site_status'] or '—')
            + '<tr><td colspan="2" style="padding:6px 0 2px;font-size:10px;'
              'font-weight:800;color:#f58220;text-transform:uppercase;'
              'letter-spacing:1px">─── KPIs ───</td></tr>'
            + row('Revenue',        f'PKR {_fmt(rev)}')
            + row('90D Base',       _fmt(s['base_90d']))
            + row('4G Base',        _fmt(s['base_4g']))
            + row('30D Base',       _fmt(s['base_30d']))
            + row('Net Adds',       _fmt(s['net_add']))
            + row('Gross Churn',    _fmt(s['gross_churn']))
            + row('HVC Base',       _fmt(s['hvc_base']))
            + row('EVC Retailer',   _fmt(s['evc_retailer']))
            + row('BVS Retailer',   _fmt(s['bvs_retailer']))
            + row('Digital Rech.',  f'PKR {_fmt(digi)} ({digi_share})')
            + row('Conv. Rech.',    f'PKR {_fmt(conv)}')
            + '</table></div>'
            ']]>'
        )

    # ── Build KML string ──────────────────────────────────────
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"'
        '     xmlns:gx="http://www.google.com/kml/ext/2.2">',
        '<Document>',
        f'  <name>Ufone 5G — Central B Sites</name>',
        f'  <description>Auto-generated from live database. '
        f'Filters: region={region or "all"}, bu={business_unit or "all"}, '
        f'month={month or "all"}, year={year or "all"}</description>',
        '',
    ]

    # One Style + StyleMap per BU
    for bu in bu_set:
        color  = _bu_color(bu)
        safe_id = bu.replace(' ', '_').replace('/', '_')
        lines += [
            f'  <!-- ── {bu} ── -->',
            f'  <Style id="style_{safe_id}_normal">',
            f'    <IconStyle>',
            f'      <color>{color}</color>',
            f'      <scale>0.9</scale>',
            f'      <Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>',
            f'    </IconStyle>',
            f'    <LabelStyle><scale>0</scale></LabelStyle>',
            f'    <BalloonStyle>',
            f'      <text>$[description]</text>',
            f'    </BalloonStyle>',
            f'  </Style>',
            f'  <Style id="style_{safe_id}_highlight">',
            f'    <IconStyle>',
            f'      <color>{color}</color>',
            f'      <scale>1.3</scale>',
            f'      <Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>',
            f'    </IconStyle>',
            f'    <LabelStyle><scale>0.9</scale></LabelStyle>',
            f'    <BalloonStyle>',
            f'      <text>$[description]</text>',
            f'    </BalloonStyle>',
            f'  </Style>',
            f'  <StyleMap id="stylemap_{safe_id}">',
            f'    <Pair><key>normal</key><styleUrl>#style_{safe_id}_normal</styleUrl></Pair>',
            f'    <Pair><key>highlight</key><styleUrl>#style_{safe_id}_highlight</styleUrl></Pair>',
            f'  </StyleMap>',
            '',
        ]

    # One Folder per BU, Placemark per site
    current_bu = None
    for s in sites:
        bu = s['business_unit'] or 'Unknown'
        safe_id = bu.replace(' ', '_').replace('/', '_')

        try:
            lat = float(s['latitude'])
            lng = float(s['longitude'])
        except (TypeError, ValueError):
            continue
        if not (20 <= lat <= 40 and 60 <= lng <= 80):
            continue

        if bu != current_bu:
            if current_bu is not None:
                lines.append('  </Folder>')
            lines += [
                f'  <Folder>',
                f'    <name>{bu}</name>',
                f'    <open>0</open>',
            ]
            current_bu = bu

        lines += [
            f'    <Placemark>',
            f'      <name>{s["key"] or "Unknown"}</name>',
            f'      <styleUrl>#stylemap_{safe_id}</styleUrl>',
            f'      <description>{placemark_desc(s)}</description>',
            f'      <Point><coordinates>{lng},{lat},0</coordinates></Point>',
            f'    </Placemark>',
        ]

    if current_bu is not None:
        lines.append('  </Folder>')

    lines += ['</Document>', '</kml>']

    kml_content = '\n'.join(lines)

    # Build a descriptive filename
    parts = ['ufone_sites']
    if region:        parts.append(region.replace(' ', '_'))
    if business_unit: parts.append(business_unit.replace(' ', '_'))
    if year:          parts.append(str(year))
    if month:         parts.append(f'm{month}')
    filename = '_'.join(parts) + '.kml'

    from django.http import HttpResponse
    response = HttpResponse(kml_content, content_type='application/vnd.google-earth.kml+xml')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── BU Boundaries GeoJSON ─────────────────────────────────────

@login_required(login_url='login')
def bu_boundaries_json(request):
    """
    GET /api/bu-boundaries/
    Serves BU district boundaries as GeoJSON.
    Priority:
      1. bu_boundaries_auto.geojson  — generated by: python manage.py fetch_bu_boundaries
      2. bu_boundaries.py            — hardcoded fallback coordinates
    """
    from django.http import JsonResponse
    import os, json as _json

    # 1 — Try auto-fetched file first (official OSM boundaries)
    auto_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bu_boundaries_auto.geojson')
    if os.path.exists(auto_path):
        with open(auto_path, encoding='utf-8') as f:
            return JsonResponse(_json.load(f))

    # 2 — Fall back to hardcoded coordinates
    try:
        from .bu_boundaries import BU_GEOJSON
        return JsonResponse(BU_GEOJSON)
    except ImportError:
        return JsonResponse({'type': 'FeatureCollection', 'features': []})


# ── Site Performance Table ────────────────────────────────────

@login_required(login_url='login')
def site_performance_table(request):
    """
    GET /api/site-table/
    Dynamic grouping based on active filters:
      - No filter / Region filter  → group by BU
      - BU filter                  → group by Franchise
      - Franchise filter           → group by Site Key
    Params: region, franchise, business_unit, site_status, month, year,
            sort_by, order (top/bottom), page, page_size
    """
    region        = request.GET.get('region')
    franchise     = request.GET.get('franchise')
    arm           = request.GET.get('arm')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')
    sort_by       = request.GET.get('sort_by', 'revenue_ytd')
    order         = request.GET.get('order', 'top')
    page          = int(request.GET.get('page', 1))
    page_size     = int(request.GET.get('page_size', 10))

    qs_base = get_scoped_qs(request.user)
    if region:        qs_base = qs_base.filter(region=region)
    if business_unit: qs_base = qs_base.filter(business_unit=business_unit)
    if arm:           qs_base = qs_base.filter(arm=arm)
    if franchise:     qs_base = qs_base.filter(franchise=franchise)
    if site_status:   qs_base = qs_base.filter(site_status=site_status)

    qs_for_latest = qs_base
    if year:  qs_for_latest = qs_for_latest.filter(year=year)
    if month: qs_for_latest = qs_for_latest.filter(month=month)
    qs = qs_base

    def safe(v):
        try: return float(v or 0)
        except: return 0

    # ── Determine grouping level ──────────────────────────────
    if franchise:
        group_field = 'key'
        group_label = 'Site'
    elif arm:
        group_field = 'franchise'
        group_label = 'Franchise'
    elif business_unit:
        group_field = 'arm'
        group_label = 'ARM'
    elif region:
        group_field = 'business_unit'
        group_label = 'BU'
    else:
        group_field = 'region'
        group_label = 'Region'

    # ── Determine latest period ───────────────────────────────
    latest = qs_for_latest.order_by('-year', '-month').values('year', 'month').first()
    if not latest:
        return JsonResponse({'rows': [], 'total': 0, 'page': 1, 'pages': 0,
                             'group_label': group_label})

    ly, lm   = latest['year'], latest['month']
    prev_y   = ly - 1
    mom_m    = lm - 1 if lm > 1 else 12
    mom_y    = ly     if lm > 1 else prev_y

    # ── Single-query conditional aggregation ─────────────────
    all_rows = (
        qs.values(group_field)
        .annotate(
            rev_ytd_c   = Sum(Case(When(year=ly, month__lte=lm, then='tot_revn_amt'),         default=0, output_field=FloatField())),
            rech_ytd_c  = Sum(Case(When(year=ly, month__lte=lm, then='prepaid_dgtl_amount'),  default=0, output_field=FloatField()))
                        + Sum(Case(When(year=ly, month__lte=lm, then='postpaid_dgtl_amount'), default=0, output_field=FloatField()))
                        + Sum(Case(When(year=ly, month__lte=lm, then='conventional_recharge'),default=0, output_field=FloatField())),
            base_ytd_c  = Sum(Case(When(year=ly, month=lm,      then='act_90d'),              default=0, output_field=FloatField())),
            churn_ytd_c = Sum(Case(When(year=ly, month__lte=lm, then='gross_churn'),          default=0, output_field=FloatField())),
            netadd_ytd_c= Sum(Case(When(year=ly, month__lte=lm, then='net_add'),              default=0, output_field=FloatField())),
            fca_ytd_c   = Sum(Case(When(year=ly, month__lte=lm, then='fca'),                  default=0, output_field=FloatField())),
            rev_ytd_p   = Sum(Case(When(year=prev_y, month__lte=lm, then='tot_revn_amt'),     default=0, output_field=FloatField())),
            rech_ytd_p  = Sum(Case(When(year=prev_y, month__lte=lm, then='prepaid_dgtl_amount'), default=0, output_field=FloatField()))
                        + Sum(Case(When(year=prev_y, month__lte=lm, then='postpaid_dgtl_amount'),default=0, output_field=FloatField()))
                        + Sum(Case(When(year=prev_y, month__lte=lm, then='conventional_recharge'),default=0, output_field=FloatField())),
            base_ytd_p  = Sum(Case(When(year=prev_y, month=lm,  then='act_90d'),              default=0, output_field=FloatField())),
            churn_ytd_p = Sum(Case(When(year=prev_y, month__lte=lm, then='gross_churn'),      default=0, output_field=FloatField())),
            netadd_ytd_p= Sum(Case(When(year=prev_y, month__lte=lm, then='net_add'),          default=0, output_field=FloatField())),
            fca_ytd_p   = Sum(Case(When(year=prev_y, month__lte=lm, then='fca'),              default=0, output_field=FloatField())),
            rev_cm      = Sum(Case(When(year=ly,     month=lm,   then='tot_revn_amt'),         default=0, output_field=FloatField())),
            rech_cm     = Sum(Case(When(year=ly,     month=lm,   then='prepaid_dgtl_amount'),  default=0, output_field=FloatField()))
                        + Sum(Case(When(year=ly,     month=lm,   then='postpaid_dgtl_amount'), default=0, output_field=FloatField()))
                        + Sum(Case(When(year=ly,     month=lm,   then='conventional_recharge'),default=0, output_field=FloatField())),
            base_cm     = Sum(Case(When(year=ly,     month=lm,   then='act_90d'),              default=0, output_field=FloatField())),
            churn_cm    = Sum(Case(When(year=ly,     month=lm,   then='gross_churn'),          default=0, output_field=FloatField())),
            netadd_cm   = Sum(Case(When(year=ly,     month=lm,   then='net_add'),              default=0, output_field=FloatField())),
            fca_cm      = Sum(Case(When(year=ly,     month=lm,   then='fca'),                  default=0, output_field=FloatField())),
            rev_yoy_p   = Sum(Case(When(year=prev_y, month=lm,   then='tot_revn_amt'),         default=0, output_field=FloatField())),
            rech_yoy_p  = Sum(Case(When(year=prev_y, month=lm,   then='prepaid_dgtl_amount'),  default=0, output_field=FloatField()))
                        + Sum(Case(When(year=prev_y, month=lm,   then='postpaid_dgtl_amount'), default=0, output_field=FloatField()))
                        + Sum(Case(When(year=prev_y, month=lm,   then='conventional_recharge'),default=0, output_field=FloatField())),
            base_yoy_p  = Sum(Case(When(year=prev_y, month=lm,   then='act_90d'),              default=0, output_field=FloatField())),
            churn_yoy_p = Sum(Case(When(year=prev_y, month=lm,   then='gross_churn'),          default=0, output_field=FloatField())),
            netadd_yoy_p= Sum(Case(When(year=prev_y, month=lm,   then='net_add'),              default=0, output_field=FloatField())),
            fca_yoy_p   = Sum(Case(When(year=prev_y, month=lm,   then='fca'),                  default=0, output_field=FloatField())),
            rev_mp      = Sum(Case(When(year=mom_y,  month=mom_m, then='tot_revn_amt'),         default=0, output_field=FloatField())),
            rech_mp     = Sum(Case(When(year=mom_y,  month=mom_m, then='prepaid_dgtl_amount'),  default=0, output_field=FloatField()))
                        + Sum(Case(When(year=mom_y,  month=mom_m, then='postpaid_dgtl_amount'), default=0, output_field=FloatField()))
                        + Sum(Case(When(year=mom_y,  month=mom_m, then='conventional_recharge'),default=0, output_field=FloatField())),
            base_mp     = Sum(Case(When(year=mom_y,  month=mom_m, then='act_90d'),              default=0, output_field=FloatField())),
            churn_mp    = Sum(Case(When(year=mom_y,  month=mom_m, then='gross_churn'),          default=0, output_field=FloatField())),
            netadd_mp   = Sum(Case(When(year=mom_y,  month=mom_m, then='net_add'),              default=0, output_field=FloatField())),
            fca_mp      = Sum(Case(When(year=mom_y,  month=mom_m, then='fca'),                  default=0, output_field=FloatField())),
        )
    )

    def pct(curr, prev):
        if not prev: return 0
        return round((curr - prev) / prev * 100, 1)

    rows = []
    for r in all_rows:
        group_val = r.get(group_field) or '—'
        rev_ytd   = safe(r['rev_ytd_c']);  rech_ytd  = safe(r['rech_ytd_c']);  base_ytd  = safe(r['base_ytd_c'])
        if rev_ytd == 0 and rech_ytd == 0 and base_ytd == 0:
            continue
        rev_ytd_p  = safe(r['rev_ytd_p']);  rech_ytd_p = safe(r['rech_ytd_p']); base_ytd_p = safe(r['base_ytd_p'])
        rev_cm     = safe(r['rev_cm']);      rech_cm    = safe(r['rech_cm']);     base_cm    = safe(r['base_cm'])
        rev_yoy_p  = safe(r['rev_yoy_p']);  rech_yoy_p = safe(r['rech_yoy_p']); base_yoy_p = safe(r['base_yoy_p'])
        rev_mp     = safe(r['rev_mp']);      rech_mp    = safe(r['rech_mp']);     base_mp    = safe(r['base_mp'])

        churn_ytd  = safe(r['churn_ytd_c']); churn_ytd_p = safe(r['churn_ytd_p'])
        netadd_ytd = safe(r['netadd_ytd_c']);netadd_ytd_p= safe(r['netadd_ytd_p'])
        churn_cm   = safe(r['churn_cm']);    churn_yoy_p = safe(r['churn_yoy_p'])
        netadd_cm  = safe(r['netadd_cm']);   netadd_yoy_p= safe(r['netadd_yoy_p'])
        churn_mp   = safe(r['churn_mp']);    netadd_mp   = safe(r['netadd_mp'])
        fca_ytd    = safe(r['fca_ytd_c']);   fca_ytd_p   = safe(r['fca_ytd_p'])
        fca_cm     = safe(r['fca_cm']);      fca_yoy_p   = safe(r['fca_yoy_p'])
        fca_mp     = safe(r['fca_mp'])
        rows.append({
            'group':          group_val,
            'group_label':    group_label,
            'rev_ytd':        rev_ytd,       'rev_ytd_pct':   pct(rev_ytd,  rev_ytd_p),   'rev_ytd_prev':  rev_ytd_p,
            'rev_yoy_curr':   rev_cm,        'rev_yoy_pct':   pct(rev_cm,   rev_yoy_p),   'rev_yoy_prev':  rev_yoy_p,
            'rev_mom_curr':   rev_cm,        'rev_mom_pct':   pct(rev_cm,   rev_mp),       'rev_mom_prev':  rev_mp,
            'rech_ytd':       rech_ytd,      'rech_ytd_pct':  pct(rech_ytd, rech_ytd_p),  'rech_ytd_prev': rech_ytd_p,
            'rech_yoy_curr':  rech_cm,       'rech_yoy_pct':  pct(rech_cm,  rech_yoy_p),  'rech_yoy_prev': rech_yoy_p,
            'rech_mom_curr':  rech_cm,       'rech_mom_pct':  pct(rech_cm,  rech_mp),      'rech_mom_prev': rech_mp,
            'base_ytd':       base_ytd,      'base_ytd_pct':  pct(base_ytd, base_ytd_p),  'base_ytd_prev': base_ytd_p,
            'base_yoy_curr':  base_cm,       'base_yoy_pct':  pct(base_cm,  base_yoy_p),  'base_yoy_prev': base_yoy_p,
            'base_mom_curr':  base_cm,       'base_mom_pct':  pct(base_cm,  base_mp),      'base_mom_prev': base_mp,
            'churn_ytd':      churn_ytd,     'churn_ytd_pct': pct(churn_ytd,churn_ytd_p), 'churn_ytd_prev':churn_ytd_p,
            'churn_yoy_curr': churn_cm,      'churn_yoy_pct': pct(churn_cm, churn_yoy_p), 'churn_yoy_prev':churn_yoy_p,
            'churn_mom_curr': churn_cm,      'churn_mom_pct': pct(churn_cm, churn_mp),     'churn_mom_prev':churn_mp,
            'churn_base_ytd': safe(r.get('base_ytd_c',0)),  'churn_base_cm': base_cm,  'churn_base_mp': base_mp,
            'netadd_ytd':     netadd_ytd,    'netadd_ytd_pct':pct(netadd_ytd,netadd_ytd_p),'netadd_ytd_prev':netadd_ytd_p,
            'netadd_yoy_curr':netadd_cm,     'netadd_yoy_pct':pct(netadd_cm,netadd_yoy_p),'netadd_yoy_prev':netadd_yoy_p,
            'netadd_mom_curr':netadd_cm,     'netadd_mom_pct':pct(netadd_cm,netadd_mp),   'netadd_mom_prev':netadd_mp,
            'fca_ytd':        fca_ytd,       'fca_ytd_pct':   pct(fca_ytd,  fca_ytd_p),   'fca_ytd_prev':  fca_ytd_p,
            'fca_yoy_curr':   fca_cm,        'fca_yoy_pct':   pct(fca_cm,   fca_yoy_p),   'fca_yoy_prev':  fca_yoy_p,
            'fca_mom_curr':   fca_cm,        'fca_mom_pct':   pct(fca_cm,   fca_mp),       'fca_mom_prev':  fca_mp,
        })

    sort_key = {
        'revenue_ytd':   lambda r: r['rev_ytd_pct'],
        'recharge_ytd':  lambda r: r['rech_ytd_pct'],
        'base_ytd':      lambda r: r['base_ytd_pct'],
        'churn_ytd':     lambda r: r['churn_ytd_pct'],
        'netadd_ytd':    lambda r: r['netadd_ytd_pct'],
        'fca_ytd':       lambda r: r['fca_ytd_pct'],
        'revenue_mom':   lambda r: r['rev_mom_pct'],
        'recharge_mom':  lambda r: r['rech_mom_pct'],
        'base_mom':      lambda r: r['base_mom_pct'],
        'churn_mom':     lambda r: r['churn_mom_pct'],
        'netadd_mom':    lambda r: r['netadd_mom_pct'],
        'fca_mom':       lambda r: r['fca_mom_pct'],
        'revenue_yoy':   lambda r: r['rev_yoy_pct'],
        'recharge_yoy':  lambda r: r['rech_yoy_pct'],
        'base_yoy':      lambda r: r['base_yoy_pct'],
        'churn_yoy':     lambda r: r['churn_yoy_pct'],
        'netadd_yoy':    lambda r: r['netadd_yoy_pct'],
        'fca_yoy':       lambda r: r['fca_yoy_pct'],
    }.get(sort_by, lambda r: r['rev_ytd_pct'])

    rows.sort(key=sort_key, reverse=(order == 'top'))

    total  = len(rows)
    pages  = max(1, (total + page_size - 1) // page_size)
    page   = max(1, min(page, pages))
    start  = (page - 1) * page_size
    paged  = rows[start:start + page_size]

    return JsonResponse({
        'rows':        paged,
        'total':       total,
        'page':        page,
        'pages':       pages,
        'page_size':   page_size,
        'period':      {'year': ly, 'month': lm},
        'group_label': group_label,
    })

# ── Dashboard Data ────────────────────────────────────────────

@login_required(login_url='login')
def dashboard_data(request):
    region        = request.GET.get('region')
    pta           = request.GET.get('pta_district')
    franchise     = request.GET.get('franchise')
    arm           = request.GET.get('arm')
    technology    = request.GET.get('technology')
    business_unit = request.GET.get('business_unit')
    site_status   = request.GET.get('site_status')
    month         = request.GET.get('month')
    year          = request.GET.get('year')

    role_base = get_scoped_qs(request.user)

    # ── Cache: return instantly on repeat requests (5 min TTL) ──
    _cache_params = {
        'r': region, 'p': pta, 'f': franchise, 'a': arm,
        't': technology, 'bu': business_unit, 'ss': site_status,
        'm': month, 'y': year, 'uid': request.user.id,
    }
    _cache_key = 'dash_' + hashlib.md5(
        _json.dumps(_cache_params, sort_keys=True).encode()
    ).hexdigest()
    _cached = cache.get(_cache_key)
    if _cached is not None:
        return JsonResponse(_cached)

    qs = role_base
    if region:        qs = qs.filter(region=region)
    if pta:           qs = qs.filter(commercial_district=pta)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise=franchise)
    if technology:    qs = qs.filter(technology=technology)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if site_status:   qs = qs.filter(site_status=site_status)

    growth_base = qs

    qs_kpi = qs
    if month: qs_kpi = qs_kpi.filter(month=month)
    if year:  qs_kpi = qs_kpi.filter(year=year)

    def safe(v):
        return float(v) if v is not None else 0

    def growth_pct(curr, prev):
        if prev == 0:
            return 100.0 if curr != 0 else 0.0
        return round(((curr - prev) / prev) * 100, 1)

    def distinct_site_count(queryset):
        return queryset.exclude(key__isnull=True).exclude(key='').values('key').distinct().count()

    # ── Stock vs Flow field classification ────────────────────
    # STOCK fields are point-in-time snapshots (e.g. act_90d as of month-end).
    # Summing across months gives a nonsense inflated number — the correct value
    # is the Sum across sites within the LATEST month of the period only.
    # FLOW fields (revenue, churn, recharge, fca, etc.) accumulate legitimately.
    STOCK_FIELDS = [
        'act_90d', 'act_90d_4g', 'act_30d', 'hvc_base',
        'evc_retailer', 'bvs_retailer', 'handset_4g', 'act_recharger',
    ]

    def latest_month_of(qs):
        """Return the (year, month) of the most recent record in qs, or None."""
        return qs.order_by('-year', '-month').values('year', 'month').first()

    def aggregate_with_stock_fix(qs):
        """
        Aggregate a period queryset correctly:
        - FLOW fields: Sum across all rows in qs (all months of the period).
        - STOCK fields: Sum across sites in the LATEST month of qs only.
        Returns a single merged dict identical in shape to a plain .aggregate() call.
        """
        # ── Flow aggregate (all months) ───────────────────────
        flow_agg = qs.aggregate(
            total_revenue=Sum('tot_revn_amt'),
            total_net_add=Sum('net_add'),
            total_churn=Sum('gross_churn'),
            avg_revenue=Avg('tot_revn_amt'),
            _prepaid_digi=Sum('prepaid_dgtl_amount'),
            _postpaid_digi=Sum('postpaid_dgtl_amount'),
            total_conv_recharge=Sum('conventional_recharge'),
            total_fca=Sum('fca'),
            total_revival=Sum('tot_revival'),
        )

        # ── Stock aggregate (latest month of this period only) ─
        lp = latest_month_of(qs)
        if lp:
            stock_qs = qs.filter(year=lp['year'], month=lp['month'])
        else:
            stock_qs = qs.none()

        stock_agg = stock_qs.aggregate(
            total_activations=Sum('act_90d'),
            total_hvc=Sum('hvc_base'),
            total_base_90d=Sum('act_90d'),
            total_base_4g=Sum('act_90d_4g'),
            total_base_30d=Sum('act_30d'),
            total_act_recharge=Sum('act_recharger'),
            total_bvs=Sum('bvs_retailer'),
            total_evc=Sum('evc_retailer'),
            total_handset_4g=Sum('handset_4g'),
            total_revenue_lm=Sum('tot_revn_amt'),  # latest-month revenue for ARPU
            total_avg_daily_active=Sum('avg_dly_act'),
        )

        return {**flow_agg, **stock_agg}

    # ── KPIs ──────────────────────────────────────────────────
    kpis = aggregate_with_stock_fix(qs_kpi)

    _digi = safe(kpis.get('_prepaid_digi')) + safe(kpis.get('_postpaid_digi'))
    kpis['total_digi_recharge'] = _digi
    _conv = safe(kpis.get('total_conv_recharge'))
    kpis['total_recharge'] = _digi + _conv
    kpis['total_sites'] = distinct_site_count(qs_kpi)
    kpis.pop('_postpaid_digi', None)
    kpis.pop('_prepaid_digi', None)

    _rev_lm = safe(kpis.get('total_revenue_lm'))  # revenue of latest month only
    _b90 = safe(kpis.get('total_base_90d'))
    kpis['total_arpu'] = (_rev_lm / _b90) if _b90 else 0

    _b90 = safe(kpis.get('total_base_90d'))
    _b4g = safe(kpis.get('total_base_4g'))
    kpis['penetration_4g'] = ((_b4g / _b90) * 100) if _b90 else 0

    kpis['total_gross_churn'] = safe(kpis.get('total_churn'))
    kpis['computed_net_adds'] = safe(kpis.get('total_net_add'))

    # ── Technology site count breakdown ───────────────────────
    # Count distinct sites per technology generation
    # A site with "2G+3G+4G" counts toward 4G; "2G+3G" toward 3G; "2G" toward 2G
    # Single query for all technology site counts — classify in Python
    _tech_rows = (qs_kpi.exclude(key__isnull=True).exclude(key='')
                  .values('key', 'technology').distinct())
    _s4g = set(); _s3g = set(); _s2g = set()
    for row in _tech_rows:
        k, t = row['key'], (row['technology'] or '')
        if '4G' in t:
            _s4g.add(k)
        elif '3G' in t:
            _s3g.add(k)
        else:
            _s2g.add(k)
    sites_4g = len(_s4g)
    sites_3g = len(_s3g)
    sites_2g = len(_s2g)
    kpis['sites_4g'] = sites_4g
    kpis['sites_3g'] = sites_3g
    kpis['sites_2g'] = sites_2g

    # ── Revenue Tier Breakdown (Silver/Gold/Platinum per site) ─
    # compute_tiers: always uses latest month of the given qs (point-in-time)
    def compute_tiers(qs):
        lp = latest_month_of(qs)
        if not lp:
            return 0, 0, 0
        tqs = qs.filter(year=lp['year'], month=lp['month'])
        rows = (tqs.exclude(key__isnull=True).exclude(key='')
                .values('key').annotate(site_rev=Sum('tot_revn_amt')))
        plat = gold = silv = 0
        for r in rows:
            rev = float(r['site_rev'] or 0)
            if rev > 700_000:   plat += 1
            elif rev > 400_000: gold += 1
            else:               silv += 1
        return plat, gold, silv

    _tier_plat, _tier_gold, _tier_silv = compute_tiers(qs_kpi)
    kpis['tier_platinum'] = _tier_plat
    kpis['tier_gold']     = _tier_gold
    kpis['tier_silver']   = _tier_silv

    # ── Revenue to Recharge ratio ─────────────────────────────
    _rev   = safe(kpis.get('total_revenue'))
    _rech  = safe(kpis.get('total_recharge'))
    kpis['rev_rech_ratio'] = round(_rev / _rech, 2) if _rech else 0

    # ── Growth ────────────────────────────────────────────────
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

        # Each period queryset — flow fields sum across all months in the range,
        # stock fields will be pulled from the latest month of each period.
        # YTD includes December of previous year as the base month
        from django.db.models import Q
        ytd_curr_qs = growth_base.filter(
            year=latest_year, month__lte=latest_month
        )
        ytd_prev_qs = growth_base.filter(
            year=prev_year, month__lte=latest_month
        )
        yoy_curr_qs = growth_base.filter(year=latest_year, month=latest_month)
        yoy_prev_qs = growth_base.filter(year=prev_year,   month=latest_month)
        mom_prev_qs = growth_base.filter(year=mom_year,    month=mom_month)

        ytd_curr_agg = aggregate_with_stock_fix(ytd_curr_qs)
        ytd_prev_agg = aggregate_with_stock_fix(ytd_prev_qs)
        yoy_curr_agg = aggregate_with_stock_fix(yoy_curr_qs)
        yoy_prev_agg = aggregate_with_stock_fix(yoy_prev_qs)
        mom_prev_agg = aggregate_with_stock_fix(mom_prev_qs)

        # ── Base-card YTD fix ────────────────────────────────────
        # aggregate_with_stock_fix() always pulls stock fields from the
        # LATEST month within whatever queryset it's handed. ytd_prev_qs
        # is bounded by month__lte=latest_month, so its latest month is
        # "latest_month of prev_year" — i.e. the stock baseline was
        # silently just duplicating YOY instead of using December LY as
        # the true start-of-year reference point for the base cards
        # (90D/4G/30D/HVC Base).
        #
        # This override is kept in a SEPARATE dict (not applied in place
        # to ytd_prev_agg) so it only affects those 4 metrics' own growth
        # entries below — total_arpu's calc divides total_revenue_lm by
        # total_base_90d from this same agg; overwriting base_90d in
        # place would mix Dec-LY's base with last-May's revenue. Flow
        # fields (revenue, churn, net adds, recharge, FCA) are untouched
        # either way — Jan-through-latest-month is already correct for those.
        ytd_prev_agg_bases = dict(ytd_prev_agg)
        dec_ly_agg = aggregate_with_stock_fix(growth_base.filter(year=prev_year, month=12))
        for _k in ('total_base_90d', 'total_base_4g', 'total_base_30d', 'total_hvc'):
            ytd_prev_agg_bases[_k] = dec_ly_agg.get(_k, 0)

        for agg in [ytd_curr_agg, ytd_prev_agg, yoy_curr_agg, yoy_prev_agg, mom_prev_agg]:
            digi = safe(agg.get('_prepaid_digi')) + safe(agg.get('_postpaid_digi'))
            agg['total_digi_recharge'] = digi
            agg['total_recharge'] = digi + safe(agg.get('total_conv_recharge'))
            agg['total_gross_churn'] = safe(agg.get('total_churn'))
            agg['computed_net_adds'] = safe(agg.get('total_net_add'))
            # Rev / Recharge ratio (×100 for % display)
            _r = safe(agg.get('total_revenue'))
            _rch = safe(agg.get('total_recharge'))
            agg['rev_rech_ratio'] = round((_r / _rch) * 100, 1) if _rch else 0

        ytd_curr_agg['total_sites'] = distinct_site_count(ytd_curr_qs)
        ytd_prev_agg['total_sites'] = distinct_site_count(ytd_prev_qs)
        yoy_curr_agg['total_sites'] = distinct_site_count(yoy_curr_qs)
        yoy_prev_agg['total_sites'] = distinct_site_count(yoy_prev_qs)
        mom_prev_agg['total_sites'] = distinct_site_count(mom_prev_qs)

        def arpu_from(agg):
            # ARPU = latest-month revenue / latest-month 90D base
            # total_revenue_lm is the revenue from the latest month of that period
            rev_lm = safe(agg.get('total_revenue_lm'))
            b90    = safe(agg.get('total_base_90d'))
            return (rev_lm / b90) if b90 else 0

        def pen_from(agg):
            b90 = safe(agg.get('total_base_90d'))
            b4g = safe(agg.get('total_base_4g'))
            return ((b4g / b90) * 100) if b90 else 0

        growth_metric_keys = [
            'total_revenue', 'total_activations', 'total_net_add',
            'total_recharge', 'total_churn', 'total_hvc', 'avg_revenue',
            'total_base_90d', 'total_base_4g', 'total_base_30d',
            'total_digi_recharge', 'total_conv_recharge',
            'total_sites', 'total_arpu', 'penetration_4g',
            'total_act_recharge', 'total_bvs', 'total_evc', 'total_handset_4g',
            'computed_net_adds', 'total_gross_churn', 'total_revival',
            'rev_rech_ratio', 'total_avg_daily_active', 'total_fca',
        ]

        BASE_CARD_KEYS = ('total_base_90d', 'total_base_4g', 'total_base_30d', 'total_hvc')

        for k in growth_metric_keys:
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
                # Base cards compare against December-of-last-year, not
                # "same month last year" — see ytd_prev_agg_bases above.
                ytd_prev = safe((ytd_prev_agg_bases if k in BASE_CARD_KEYS
                                  else ytd_prev_agg).get(k))
                yoy_curr = safe(yoy_curr_agg.get(k))
                yoy_prev = safe(yoy_prev_agg.get(k))
                mom_prev = safe(mom_prev_agg.get(k))
            mom_curr = yoy_curr

            growth[k] = {
                'ytd_pct':  growth_pct(ytd_curr, ytd_prev),
                'yoy_pct':  growth_pct(yoy_curr, yoy_prev),
                'mtd_pct':  growth_pct(mom_curr, mom_prev),
                'ytd_curr': ytd_curr,  'ytd_prev': ytd_prev,
                'yoy_curr': yoy_curr,  'yoy_prev': yoy_prev,
                'mtd_curr': mom_curr,  'mtd_prev': mom_prev,
            }
        # ── Tier growth (Platinum / Gold / Silver site counts) ──────
        # Computed separately because they can't be derived from aggregate_with_stock_fix
        def _tier_growth(curr_plat, curr_gold, curr_silv, prev_plat, prev_gold, prev_silv):
            def pct(c, p): return growth_pct(c, p)
            return {
                'platinum': {
                    'ytd_curr': curr_plat, 'ytd_prev': prev_plat, 'ytd_pct': pct(curr_plat, prev_plat),
                    'yoy_curr': curr_plat, 'yoy_prev': prev_plat, 'yoy_pct': pct(curr_plat, prev_plat),
                    'mtd_curr': curr_plat, 'mtd_prev': prev_plat, 'mtd_pct': pct(curr_plat, prev_plat),
                },
                'gold': {
                    'ytd_curr': curr_gold, 'ytd_prev': prev_gold, 'ytd_pct': pct(curr_gold, prev_gold),
                    'yoy_curr': curr_gold, 'yoy_prev': prev_gold, 'yoy_pct': pct(curr_gold, prev_gold),
                    'mtd_curr': curr_gold, 'mtd_prev': prev_gold, 'mtd_pct': pct(curr_gold, prev_gold),
                },
                'silver': {
                    'ytd_curr': curr_silv, 'ytd_prev': prev_silv, 'ytd_pct': pct(curr_silv, prev_silv),
                    'yoy_curr': curr_silv, 'yoy_prev': prev_silv, 'yoy_pct': pct(curr_silv, prev_silv),
                    'mtd_curr': curr_silv, 'mtd_prev': prev_silv, 'mtd_pct': pct(curr_silv, prev_silv),
                },
            }

        ytd_curr_plat, ytd_curr_gold, ytd_curr_silv = compute_tiers(ytd_curr_qs)
        ytd_prev_plat, ytd_prev_gold, ytd_prev_silv = compute_tiers(ytd_prev_qs)
        yoy_curr_plat, yoy_curr_gold, yoy_curr_silv = compute_tiers(yoy_curr_qs)
        yoy_prev_plat, yoy_prev_gold, yoy_prev_silv = compute_tiers(yoy_prev_qs)
        mom_curr_plat, mom_curr_gold, mom_curr_silv = compute_tiers(yoy_curr_qs)
        mom_prev_plat, mom_prev_gold, mom_prev_silv = compute_tiers(mom_prev_qs)

        growth['tier_platinum'] = {
            'ytd_pct': growth_pct(ytd_curr_plat, ytd_prev_plat), 'ytd_curr': ytd_curr_plat, 'ytd_prev': ytd_prev_plat,
            'yoy_pct': growth_pct(yoy_curr_plat, yoy_prev_plat), 'yoy_curr': yoy_curr_plat, 'yoy_prev': yoy_prev_plat,
            'mtd_pct': growth_pct(mom_curr_plat, mom_prev_plat), 'mtd_curr': mom_curr_plat, 'mtd_prev': mom_prev_plat,
        }
        growth['tier_gold'] = {
            'ytd_pct': growth_pct(ytd_curr_gold, ytd_prev_gold), 'ytd_curr': ytd_curr_gold, 'ytd_prev': ytd_prev_gold,
            'yoy_pct': growth_pct(yoy_curr_gold, yoy_prev_gold), 'yoy_curr': yoy_curr_gold, 'yoy_prev': yoy_prev_gold,
            'mtd_pct': growth_pct(mom_curr_gold, mom_prev_gold), 'mtd_curr': mom_curr_gold, 'mtd_prev': mom_prev_gold,
        }
        growth['tier_silver'] = {
            'ytd_pct': growth_pct(ytd_curr_silv, ytd_prev_silv), 'ytd_curr': ytd_curr_silv, 'ytd_prev': ytd_prev_silv,
            'yoy_pct': growth_pct(yoy_curr_silv, yoy_prev_silv), 'yoy_curr': yoy_curr_silv, 'yoy_prev': yoy_prev_silv,
            'mtd_pct': growth_pct(mom_curr_silv, mom_prev_silv), 'mtd_curr': mom_curr_silv, 'mtd_prev': mom_prev_silv,
        }



    # ── Chart data ────────────────────────────────────────────
    def sl(lst, key):
        return [safe(i[key]) for i in lst]

    revenue_by_region = list(qs_kpi.exclude(region__isnull=True).values('region').annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue')[:10])
    act_by_tech       = list(qs_kpi.exclude(technology__isnull=True).values('technology').annotate(activations=Sum('act_90d')).order_by('-activations'))
    rev_by_bu         = list(qs_kpi.exclude(business_unit__isnull=True).values('business_unit').annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue'))

    recharge = qs_kpi.aggregate(
        prepaid_digital=Sum('prepaid_dgtl_amount'),
        postpaid_digital=Sum('postpaid_dgtl_amount'),
        conventional=Sum('conventional_recharge'),
    )
    # Override with combined totals for the breakdown chart
    recharge['digital'] = safe(recharge['prepaid_digital']) + safe(recharge['postpaid_digital'])
    recharge['total']   = recharge['digital'] + safe(recharge['conventional'])

    net_qs = (
        qs_kpi.exclude(net_add__isnull=True).exclude(year__isnull=True).exclude(month__isnull=True)
        .values('year', 'month')
        .annotate(value=Sum('net_add'))
        .order_by('year', 'month')
    )
    months_range = list(range(1, 13))
    years_net    = sorted(set(r['year'] for r in net_qs if r['year'] is not None))
    series_net   = defaultdict(lambda: [None] * 12)
    for r in net_qs:
        if r['year'] is not None and r['month'] is not None:
            series_net[r['year']][r['month'] - 1] = safe(r['value'])
    net_add_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_net[y]} for y in years_net],
    }

    # ── Monthly Revenue trend (multi-year, None for missing months) ───
    rev_chart_qs = qs
    if year: rev_chart_qs = rev_chart_qs.filter(year=year)
    rev_month_qs = (
        rev_chart_qs.exclude(tot_revn_amt__isnull=True).exclude(year__isnull=True).exclude(month__isnull=True)
        .values('year', 'month')
        .annotate(value=Sum('tot_revn_amt'))
        .order_by('year', 'month')
    )
    years_rev_m  = sorted(set(r['year'] for r in rev_month_qs if r['year'] is not None))
    series_rev_m = defaultdict(lambda: [None] * 12)
    for r in rev_month_qs:
        if r['year'] is not None and r['month'] is not None:
            series_rev_m[r['year']][r['month'] - 1] = safe(r['value'])
    rev_monthly_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_rev_m[y]} for y in years_rev_m],
    }

    # ── Monthly Total Recharge trend ──────────────────────────
    # Use qs (not qs_kpi) so the monthly trend is NOT filtered by month/year selection
    # This ensures all 12 months always display correctly in the chart
    rech_chart_qs = qs
    if year: rech_chart_qs = rech_chart_qs.filter(year=year)
    rech_month_qs = (
        rech_chart_qs.exclude(year__isnull=True).exclude(month__isnull=True)
        .values('year', 'month')
        .annotate(
            prepaid=Sum('prepaid_dgtl_amount'),
            postpaid=Sum('postpaid_dgtl_amount'),
            conv=Sum('conventional_recharge'),
        )
        .order_by('year', 'month')
    )
    years_rech_m  = sorted(set(r['year'] for r in rech_month_qs if r['year'] is not None))
    series_rech_m = defaultdict(lambda: [None] * 12)
    series_digi_m = defaultdict(lambda: [None] * 12)
    series_conv_m = defaultdict(lambda: [None] * 12)
    for r in rech_month_qs:
        if r['year'] is not None and r['month'] is not None:
            idx_m = r['month'] - 1
            pre  = safe(r.get('prepaid'))
            post = safe(r.get('postpaid'))
            cv   = safe(r.get('conv'))
            digi = pre + post
            total = digi + cv
            series_rech_m[r['year']][idx_m] = total if (total > 0) else None
            series_digi_m[r['year']][idx_m] = digi  if (digi  > 0) else None
            series_conv_m[r['year']][idx_m] = cv     if (cv    > 0) else None

    rech_monthly_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_rech_m[y]} for y in years_rech_m],
    }
    digi_monthly_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_digi_m[y]} for y in years_rech_m],
    }
    conv_monthly_chart = {
        'labels':   months_range,
        'datasets': [{'label': str(y), 'data': series_conv_m[y]} for y in years_rech_m],
    }

    traffic          = list(qs_kpi.exclude(region__isnull=True).values('region').annotate(outgoing=Sum('minutes_outgoing'), incoming=Sum('minutes_incoming')).order_by('-outgoing')[:8])
    data_vol         = list(qs_kpi.exclude(technology__isnull=True).values('technology').annotate(volume=Sum('volume_gbs')).order_by('-volume'))
    site_status_data = list(qs_kpi.exclude(site_status__isnull=True).values('site_status').annotate(count=Count('key', distinct=True)).order_by('-count'))
    top_districts    = list(qs_kpi.exclude(commercial_district__isnull=True).values('commercial_district').annotate(revenue=Sum('tot_revn_amt')).order_by('-revenue'))

    churn_monthly_qs = (
        qs_kpi.exclude(month__isnull=True)
        .values('month')
        .annotate(churn=Sum('gross_churn'), revival=Sum('fca'))
        .order_by('month')
    )
    churn_map = {r['month']: r for r in churn_monthly_qs}
    churn_by_month   = [safe(churn_map.get(m, {}).get('churn')) for m in months_range]
    revival_by_month = [safe(churn_map.get(m, {}).get('revival')) for m in months_range]
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

    # ── Base KPI monthly trends — multi-year ──────────────────
    # base_trend_raw groups by (year, month), so each row = one month.
    # Stock fields (b90, b4g, etc.) are summed across SITES within that month —
    # this is correct because we're not summing across months here.
    # Flow fields (fca, churn, revival) also sum correctly per month.
    trend_base_qs = qs
    if year:
        trend_base_qs = trend_base_qs.filter(year=year)

    base_trend_raw = (
        trend_base_qs
        .exclude(month__isnull=True)
        .exclude(year__isnull=True)
        .values('year', 'month')
        .annotate(
            b90=Sum('act_90d'),
            b4g=Sum('act_90d_4g'),
            b30=Sum('act_30d'),
            hvc=Sum('hvc_base'),
            act_rch=Sum('act_recharger'),
            bvs=Sum('bvs_retailer'),
            evc=Sum('evc_retailer'),
            hs4g=Sum('handset_4g'),
            fca=Sum('fca'),
            revival=Sum('tot_revival'),
            churn=Sum('gross_churn'),
            net_add=Sum('net_add'),
            avg_dly_act=Sum('avg_dly_act'),
             )
        .order_by('year', 'month')
    )

    trend_years        = sorted(set(r['year'] for r in base_trend_raw if r['year'] is not None))
    trend_months_range = list(range(1, 13))
    trend_rows         = list(base_trend_raw)

    def build_series(rows, fn):
        series = defaultdict(lambda: [None] * 12)
        for r in rows:
            if r['year'] is not None and r['month'] is not None:
                series[r['year']][r['month'] - 1] = fn(r)
        return series

    s_b90    = build_series(trend_rows, lambda r: safe(r.get('b90'))     if r.get('b90')     is not None else None)
    s_b30    = build_series(trend_rows, lambda r: safe(r.get('b30'))     if r.get('b30')     is not None else None)
    s_hvc    = build_series(trend_rows, lambda r: safe(r.get('hvc'))     if r.get('hvc')     is not None else None)
    s_b4g    = build_series(trend_rows, lambda r: safe(r.get('b4g'))     if r.get('b4g')     is not None else None)
    s_actrch = build_series(trend_rows, lambda r: safe(r.get('act_rch')) if r.get('act_rch') is not None else None)
    s_bvs    = build_series(trend_rows, lambda r: safe(r.get('bvs'))     if r.get('bvs')     is not None else None)
    s_evc    = build_series(trend_rows, lambda r: safe(r.get('evc'))     if r.get('evc')     is not None else None)
    s_hs4g   = build_series(trend_rows, lambda r: safe(r.get('hs4g'))    if r.get('hs4g')    is not None else None)
    s_net_adds = build_series(trend_rows, lambda r: safe(r.get('net_add')) if r.get('net_add') is not None else None)
    s_churn    = build_series(trend_rows, lambda r: safe(r.get('churn'))   if r.get('churn')   is not None else None)
    s_revival  = build_series(trend_rows, lambda r: safe(r.get('revival')) if r.get('revival') is not None else None)
    s_pen4g    = build_series(trend_rows, lambda r: round(safe(r.get('b4g')) / safe(r.get('b90')) * 100, 2) if safe(r.get('b90')) else None)
    s_hvc_pct  = build_series(trend_rows, lambda r: round(safe(r.get('hvc')) / safe(r.get('b90')) * 100, 2) if safe(r.get('b90')) else None)
    s_fca      = build_series(trend_rows, lambda r: safe(r.get('fca'))     if r.get('fca')     is not None else None)
    s_actrch_pct = build_series(trend_rows, lambda r: round(safe(r.get('act_rch')) / safe(r.get('b90')) * 100, 2) if safe(r.get('b90')) else None)
    s_hs4g_pct   = build_series(trend_rows, lambda r: round(safe(r.get('hs4g'))    / safe(r.get('b90')) * 100, 2) if safe(r.get('b90')) else None)
    s_ada_pct    = build_series(trend_rows, lambda r: round(safe(r.get('avg_dly_act')) / safe(r.get('b90')) * 100, 2) if safe(r.get('b90')) else None)

    avg_qs = (
        trend_base_qs
        .exclude(avg_dly_act__isnull=True)
        .exclude(year__isnull=True)
        .exclude(month__isnull=True)
        .values('year', 'month')
        .annotate(value=Sum('avg_dly_act'))
        .order_by('year', 'month')
    )
    s_ada = build_series(
        list(avg_qs),
        lambda r: safe(r.get('value')) if r.get('value') is not None else None
    )

    base_trends = {
        'labels':       trend_months_range,
        'years':        [str(y) for y in trend_years],
        'base90':       [s_b90[y]      for y in trend_years],
        'base30':       [s_b30[y]      for y in trend_years],
        'hvc':          [s_hvc[y]      for y in trend_years],
        'base4g':       [s_b4g[y]      for y in trend_years],
        'act_recharge': [s_actrch[y]   for y in trend_years],
        'bvs':          [s_bvs[y]      for y in trend_years],
        'evc':          [s_evc[y]      for y in trend_years],
        'handset_4g':   [s_hs4g[y]     for y in trend_years],
        'net_adds':     [s_net_adds[y] for y in trend_years],
        'churn':        [s_churn[y]    for y in trend_years],
        'revival':      [s_revival[y]  for y in trend_years],
        'pen4g':        [s_pen4g[y]    for y in trend_years],
        'hvc_pct':      [s_hvc_pct[y]  for y in trend_years],
                'ada':          [s_ada[y]      for y in trend_years],
        'fca':          [s_fca[y]        for y in trend_years],
        'actrch_pct':   [s_actrch_pct[y] for y in trend_years],
        'hs4g_pct':     [s_hs4g_pct[y]   for y in trend_years],
        'ada_pct':      [s_ada_pct[y]    for y in trend_years],
    }

    # ── Cache the result ────────────────────────────────────────
    _response_data = {
        'kpis':   {k: safe(v) for k, v in kpis.items()},
        'growth': growth,
        'revenue_by_region': {'labels': [r['region'] for r in revenue_by_region],    'values': sl(revenue_by_region, 'revenue')},
        'act_by_tech':       {'labels': [r['technology'] for r in act_by_tech],       'values': sl(act_by_tech, 'activations')},
        'rev_by_bu':         {'labels': [r['business_unit'] for r in rev_by_bu],      'values': sl(rev_by_bu, 'revenue')},
        'recharge': {
            'labels': ['Total Recharge', 'Digital Recharge', 'Conventional'],
            'values': [safe(recharge['total']), safe(recharge['digital']), safe(recharge['conventional'])],
        },
        'net_add_region':         net_add_chart,
        'rev_monthly':            rev_monthly_chart,
        'rech_monthly':           rech_monthly_chart,
        'digi_monthly':           digi_monthly_chart,
        'conv_monthly':           conv_monthly_chart,
        'traffic':                {'labels': [r['region'] for r in traffic], 'outgoing': sl(traffic, 'outgoing'), 'incoming': sl(traffic, 'incoming')},
        'data_vol':               {'labels': [r['technology'] for r in data_vol], 'values': sl(data_vol, 'volume')},
        'site_status':            {'labels': [r['site_status'] for r in site_status_data], 'values': [r['count'] for r in site_status_data]},
        'top_districts':          {'labels': [r['commercial_district'] for r in top_districts], 'values': sl(top_districts, 'revenue')},
        'churn_revival':          {'labels': [r['region'] for r in churn_revival], 'churn': sl(churn_revival, 'churn'), 'revival': sl(churn_revival, 'revival')},
        'churn_revival_by_month': churn_revival_by_month,
        'base_trends':            base_trends,
    }
    cache.set(_cache_key, _response_data, 300)  # 5 min TTL
    return JsonResponse(_response_data)


# ── Nearby Sites ──────────────────────────────────────────────

@login_required(login_url='login')
def nearby_sites(request):
    try:
        user_lat = float(request.GET.get('lat'))
        user_lng = float(request.GET.get('lng'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid or missing lat/lng'}, status=400)

    radius = request.GET.get('radius')
    try:
        radius = float(radius) if radius else None
    except ValueError:
        radius = None

    limit = request.GET.get('limit')
    try:
        limit = int(limit) if limit else (50 if radius else 3)
    except ValueError:
        limit = 50 if radius else 3

    role_base = get_scoped_qs(request.user)

    latest = role_base.order_by('-year', '-month').values('year', 'month').first()
    if latest:
        qs = role_base.filter(year=latest['year'], month=latest['month'])
    else:
        qs = role_base

    lat_range = (radius / 111.0) if radius else 2.0
    lng_range = (radius / (111.0 * 0.85)) if radius else 2.0
    candidates = qs.filter(
        latitude__gte=user_lat - lat_range,
        latitude__lte=user_lat + lat_range,
        longitude__gte=user_lng - lng_range,
        longitude__lte=user_lng + lng_range,
    ).exclude(latitude__isnull=True).exclude(longitude__isnull=True).values(
        'key', 'latitude', 'longitude', 'region', 'commercial_district', 'franchise',
        'arm', 'business_unit', 'technology', 'site_status', 'tot_revn_amt',
        'act_90d', 'act_90d_4g', 'act_30d', 'net_add', 'gross_churn', 'hvc_base',
        'evc_retailer', 'bvs_retailer', 'handset_4g', 'mnp_fca', 'fca',
        'm0_revn', 'volume_gbs', 'data_ntwrk_vol_4g', 'avg_dly_act', 'tot_revival',
        'conventional_recharge', 'prepaid_dgtl_amount', 'postpaid_dgtl_amount',
        'year', 'month',
    )

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
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
        if radius is not None and d > radius:
            continue
        scored.append((d, s))

    scored.sort(key=lambda x: x[0])
    top = scored[:limit]

    def safe(v):
        return float(v) if v is not None else 0

    results = []
    for dist, s in top:
        _pre  = safe(s.get('prepaid_dgtl_amount'))
        _post = safe(s.get('postpaid_dgtl_amount'))
        _conv = safe(s.get('conventional_recharge'))
        results.append({
            'key':            s['key'] or 'Unknown',
            'distance_km':    round(dist, 2),
            'latitude':       float(s['latitude']),
            'longitude':      float(s['longitude']),
            'region':         s['region'] or '—',
            'pta_district':   s['commercial_district'] or '—',
            'franchise':      s['franchise'] or '—',
            'arm':            s.get('arm') or '—',
            'business_unit':  s['business_unit'] or '—',
            'technology':     s['technology'] or '—',
            'site_status':    s['site_status'] or '—',
            # ── flow metrics ─────────────────────────────────────────────
            'revenue':        safe(s['tot_revn_amt']),
            'm0_revenue':     safe(s.get('m0_revn')),
            'fca':            safe(s.get('fca')),
            'mnp':            safe(s.get('mnp_fca')),
            'net_add':        safe(s['net_add']),
            'churn':          safe(s['gross_churn']),
            'revival':        safe(s.get('tot_revival')),
            'avg_dly_act':    safe(s.get('avg_dly_act')),
            'volume_gbs':     safe(s.get('volume_gbs')),
            'data_4g_gbs':    safe(s.get('data_ntwrk_vol_4g')),
            'conv_recharge':  _conv,
            'digi_recharge':  _pre + _post,
            'total_recharge': _pre + _post + _conv,
            # ── closing / stock metrics ───────────────────────────────────
            'activations':    safe(s['act_90d']),
            'base_4g':        safe(s['act_90d_4g']),
            'base_30d':       safe(s.get('act_30d')),
            'hvc':            safe(s['hvc_base']),
            'evc_base':       safe(s.get('evc_retailer')),
            'bvs_base':       safe(s.get('bvs_retailer')),
            'handset_4g':     safe(s.get('handset_4g')),
            'period':         f"{s['month']}/{s['year']}" if s['year'] else '—',
        })

    return JsonResponse({
        'user_location':  {'lat': user_lat, 'lng': user_lng},
        'radius_km':      radius,
        'count':          len(results),
        'total_in_scope': len(scored),
        'sites':          results,
    })


# ── Chat ──────────────────────────────────────────────────────

@login_required(login_url='login')
def chat_page(request):
    profile = get_or_create_profile(request.user)
    profile.last_seen = timezone.now()
    profile.save(update_fields=['last_seen'])
    # Auto-create rooms on first visit if none exist
    try:
        if not ChatRoom.objects.exists():
            _ensure_rooms_exist()
        # Make sure this user is in at least the region room
        region_room = ChatRoom.objects.filter(slug='region').first()
        if region_room:
            region_room.members.add(request.user)
    except Exception:
        pass  # Table may not exist yet before migration
    rooms = list(ChatRoom.objects.filter(members=request.user).values('slug','name','room_type'))
    return render(request, 'dashboard/chat.html', {'profile': profile, 'chat_rooms': rooms})


@login_required(login_url='login')
def chat_messages(request):
    """Send/receive messages. Supports rooms, edit, delete."""
    is_poll = request.method == 'GET' and request.GET.get('since')
    if not is_poll:
        UserProfile.objects.filter(user=request.user).update(last_seen=timezone.now())

    room_slug = request.GET.get('room') or request.POST.get('room') or 'region'
    try:
        room = ChatRoom.objects.get(slug=room_slug)
    except ChatRoom.DoesNotExist:
        room = _get_or_create_region_room()

    if request.method == 'POST':
        action = request.POST.get('action', 'send')

        # ── EDIT ──────────────────────────────────────────────────────────
        if action == 'edit':
            msg_id = request.POST.get('id')
            new_text = request.POST.get('text', '').strip()
            try:
                msg = ChatMessage.objects.get(id=msg_id, sender=request.user, deleted=False)
                msg.text = new_text[:2000]
                msg.edited = True
                msg.save(update_fields=['text', 'edited', 'updated_at'])
                return JsonResponse({'ok': True, 'id': msg.id, 'text': msg.text})
            except ChatMessage.DoesNotExist:
                return JsonResponse({'error': 'Not found'}, status=404)

        # ── DELETE ────────────────────────────────────────────────────────
        if action == 'delete':
            msg_id = request.POST.get('id')
            try:
                msg = ChatMessage.objects.get(id=msg_id, sender=request.user)
                msg.deleted = True
                msg.save(update_fields=['deleted', 'updated_at'])
                return JsonResponse({'ok': True, 'id': msg.id})
            except ChatMessage.DoesNotExist:
                return JsonResponse({'error': 'Not found'}, status=404)

        # ── SEND ──────────────────────────────────────────────────────────
        text  = request.POST.get('text', '').strip()
        image = request.FILES.get('image')
        audio = request.FILES.get('audio')

        if not text and not image and not audio:
            return JsonResponse({'error': 'Empty message'}, status=400)
        if image and not image.content_type.startswith('image/'):
            return JsonResponse({'error': 'File must be an image'}, status=400)
        if image and image.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Image must be under 5 MB'}, status=400)
        if audio and audio.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'Audio must be under 10 MB'}, status=400)

        audio_duration = None
        if audio:
            try:
                audio_duration = int(request.POST.get('audio_duration', 0)) or None
            except (ValueError, TypeError):
                audio_duration = None

        msg = ChatMessage.objects.create(
            sender=request.user,
            room=room,
            text=text[:2000] if text else '',
            image=image if image else None,
            audio=audio if audio else None,
            audio_duration=audio_duration,
        )

        # Push notification to other room members
        _send_push_to_room(room, request.user, text or '📎 Attachment')

        return JsonResponse({'ok': True, 'id': msg.id})

    # ── GET ───────────────────────────────────────────────────────────────
    since = request.GET.get('since')
    base_qs = ChatMessage.objects.filter(room=room, deleted=False).select_related('sender', 'sender__profile')

    if since:
        try:
            messages_list = list(base_qs.filter(id__gt=int(since)).order_by('id'))
        except ValueError:
            messages_list = []
    else:
        messages_list = list(base_qs.order_by('-id')[:100])[::-1]

    def serialize(m):
        sp = getattr(m.sender, 'profile', None)
        return {
            'id':             m.id,
            'sender_id':      m.sender.id,
            'sender_name':    m.sender.get_full_name() or m.sender.username,
            'designation':    sp.designation if sp else '',
            'picture':        sp.get_picture_url() if sp else None,
            'text':           m.text,
            'image':          m.image.url if m.image else None,
            'audio':          m.audio.url if m.audio else None,
            'audio_duration': m.audio_duration,
            'created_at':     m.created_at.isoformat(),
            'is_mine':        m.sender_id == request.user.id,
            'edited':         m.edited,
            'deleted':        m.deleted,
        }

    return JsonResponse({'messages': [serialize(m) for m in messages_list], 'count': len(messages_list)})


@login_required(login_url='login')
def chat_rooms(request):
    """Return rooms the current user is a member of."""
    _ensure_rooms_exist()
    profile = getattr(request.user, 'profile', None)
    rooms = request.user.chat_rooms.all().order_by('room_type', 'name')
    return JsonResponse({'rooms': [
        {'slug': r.slug, 'name': r.name, 'type': r.room_type}
        for r in rooms
    ]})


@login_required(login_url='login')
def push_subscribe(request):
    """Save a Web Push subscription."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    import json
    data = json.loads(request.body)
    PushSubscription.objects.update_or_create(
        endpoint=data['endpoint'],
        defaults={
            'user':   request.user,
            'p256dh': data['keys']['p256dh'],
            'auth':   data['keys']['auth'],
        }
    )
    return JsonResponse({'ok': True})


@login_required(login_url='login')
def push_vapid_public(request):
    """Return VAPID public key for the frontend."""
    from django.conf import settings
    return JsonResponse({'public_key': getattr(settings, 'VAPID_PUBLIC_KEY', '')})


@login_required(login_url='login')
def delete_chat_room(request, slug):
    """One-time: delete a chat room by slug. Admin only."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Admin only")
    from django.http import HttpResponse
    deleted = ChatRoom.objects.filter(slug=slug).delete()
    return HttpResponse(f"Deleted room '{slug}': {deleted}")


@login_required(login_url='login')
def chat_room_members(request):
    """Return member list for a room — visible only to members of that room."""
    slug = request.GET.get('room')
    try:
        room = ChatRoom.objects.get(slug=slug)
    except ChatRoom.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    if not room.members.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Not a member of this room'}, status=403)

    members = room.members.select_related('profile').order_by('first_name', 'username')
    data = []
    for u in members:
        p = getattr(u, 'profile', None)
        data.append({
            'id':          u.id,
            'name':        u.get_full_name() or u.username,
            'designation': getattr(p, 'designation', '') or '',
            'category':    getattr(p, 'category', '') or '',
            'picture':     p.get_picture_url() if p else None,
            'is_you':      u.id == request.user.id,
        })
    return JsonResponse({'room_name': room.name, 'count': len(data), 'members': data})


@login_required(login_url='login')
def setup_chat_rooms(request):
    """One-time: create rooms and assign members. Admin only. Visit once then it's done."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Admin only")
    _ensure_rooms_exist()
    from django.http import HttpResponse
    from django.contrib.auth.models import User as _U
    rooms = ChatRoom.objects.all().prefetch_related('members')
    lines = ["<h2>✅ Chat rooms created / synced</h2>"]
    lines.append(f"<p>Total users: {_U.objects.count()} | Region: {_U.objects.filter(profile__category='Region').count()} | BU: {_U.objects.filter(profile__category='BU').count()} | ARM: {_U.objects.filter(profile__category='ARM').count()} | RD (designation): {_U.objects.filter(profile__designation='RD').count()}</p>")
    lines.append("<ul>")
    for r in rooms:
        members = r.members.count()
        mnames = ", ".join(r.members.values_list('username', flat=True)[:10])
        lines.append(f"<li><b>{r.name}</b> ({r.slug}) — {members} members: {mnames}</li>")
    lines.append("</ul>")
    return HttpResponse("\n".join(lines))


@login_required(login_url='login')
def chat_users(request):
    five_min_ago = timezone.now() - timedelta(minutes=5)
    users = User.objects.select_related('profile').order_by('first_name', 'username')

    def serialize(u):
        p = getattr(u, 'profile', None)
        is_online = bool(p and p.last_seen and p.last_seen >= five_min_ago)
        return {
            'id':          u.id,
            'name':        u.get_full_name() or u.username,
            'designation': p.designation if p else '',
            'category':    p.category if p else '',
            'picture':     p.get_picture_url() if p else None,
            'is_online':   is_online,
            'is_me':       u.id == request.user.id,
        }

    return JsonResponse({
        'users': [serialize(u) for u in users],
        'total': users.count(),
    })

@login_required(login_url='/')
def download_stats(request):
    return render(request, 'dashboard/download_stats.html')