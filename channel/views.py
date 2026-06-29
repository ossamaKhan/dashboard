"""
Channel views — optimized for maximum speed.
Caching: all API endpoints cached via Redis/Upstash (5-10 min TTL).
Queries: growth periods collapsed into single Case/When query.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Sum, Q, Case, When, FloatField, IntegerField, Max, Count
from django.core.cache import cache
from collections import defaultdict
import hashlib
import json as _json

from .models import ChannelDaily


# ── Helpers ──────────────────────────────────────────────────
def safe(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0


def attainment(ach, target):
    return round((ach / target) * 100, 1) if target else 0


def get_scoped_qs(user):
    qs = ChannelDaily.objects.all()
    try:
        profile = user.profile
        category = profile.category
    except Exception:
        return qs

    if category == 'BU':
        bu_raw = profile.user_business_unit or ''
        bu = bu_raw.split(',')[0].strip() if bu_raw else ''
        if bu:
            qs = qs.filter(business_unit=bu)

    elif category == 'ARM':
        arm = profile.user_arm or ''
        if arm:
            qs = qs.filter(arm=arm)

    return qs


def get_locked_filters(user):
    try:
        profile = user.profile
        category = profile.category
    except Exception:
        category = 'Region'

    if category == 'BU':
        bu_val = profile.user_business_unit or ''
        bu_display = bu_val.split(',')[0].strip() if bu_val else ''
        return {
            'category': 'BU',
            'region':   {'locked': True,  'value': 'Central B'},
            'bu':       {'locked': True,  'value': bu_display},
            'arm':      {'locked': False, 'value': None},
        }

    elif category == 'ARM':
        arm_val = profile.user_arm or ''
        bu_val = (ChannelDaily.objects
                  .filter(arm=arm_val)
                  .values_list('business_unit', flat=True)
                  .first()) or ''
        return {
            'category': 'ARM',
            'region':   {'locked': True, 'value': 'Central B'},
            'bu':       {'locked': True, 'value': bu_val},
            'arm':      {'locked': True, 'value': arm_val},
        }

    return {
        'category': 'Region',
        'region':   {'locked': False, 'value': None},
        'bu':       {'locked': False, 'value': None},
        'arm':      {'locked': False, 'value': None},
    }


def get_locked_context(user):
    return get_locked_filters(user)


def get_or_create_profile_local(user):
    try:
        from marketing.views import get_or_create_profile
        return get_or_create_profile(user)
    except Exception:
        return None


def _cache_key(prefix, params):
    raw = _json.dumps(params, sort_keys=True)
    return prefix + hashlib.md5(raw.encode()).hexdigest()


# ── Pages ────────────────────────────────────────────────────
@login_required(login_url='login')
def channel_dashboard(request):
    profile = get_or_create_profile_local(request.user)
    return render(request, 'channel/index.html', {
        'profile': profile,
        'locked':  get_locked_filters(request.user),
    })


@login_required(login_url='login')
def channel_performance(request):
    profile = get_or_create_profile_local(request.user)
    return render(request, 'channel/performance.html', {
        'profile': profile,
        'locked':  get_locked_filters(request.user),
    })


@login_required(login_url='login')
def channel_retailers(request):
    profile = get_or_create_profile_local(request.user)
    return render(request, 'channel/retailers.html', {
        'profile': profile,
        'locked':  get_locked_filters(request.user),
    })


@login_required(login_url='login')
def channel_enablers(request):
    profile = get_or_create_profile_local(request.user)
    return render(request, 'channel/enablers.html', {
        'profile': profile,
        'locked':  get_locked_filters(request.user),
    })


@login_required(login_url='login')
def channel_quality(request):
    profile = get_or_create_profile_local(request.user)
    return render(request, 'channel/quality.html', {
        'profile': profile,
        'locked':  get_locked_filters(request.user),
    })


# ── Filter options API ───────────────────────────────────────
@login_required(login_url='login')
def channel_filters(request):
    region        = request.GET.get('region')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')

    ck = _cache_key('ch_filters_', {
        'r': region, 'bu': business_unit, 'a': arm, 'uid': request.user.id
    })
    cached = cache.get(ck)
    if cached is not None:
        return JsonResponse(cached)

    qs = get_scoped_qs(request.user)
    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)

    arm_qs = qs
    fr_qs  = qs.filter(arm=arm) if arm else qs

    regions    = sorted(qs.exclude(region='').values_list('region', flat=True).distinct())
    bus        = sorted(qs.exclude(business_unit='').values_list('business_unit', flat=True).distinct())
    arms       = sorted(arm_qs.exclude(arm__isnull=True).exclude(arm='').values_list('arm', flat=True).distinct())
    franchises = sorted(fr_qs.exclude(franchise_id='').values_list('franchise_id', flat=True).distinct())
    years      = sorted({d.year for d in qs.values_list('date', flat=True).distinct() if d}, reverse=True)
    months     = list(range(1, 13))

    latest_date  = qs.aggregate(d=Max('date'))['d']
    latest_year  = latest_date.year  if latest_date else None
    latest_month = latest_date.month if latest_date else None

    data = {
        'regions': regions, 'business_units': bus, 'arms': arms,
        'franchises': franchises, 'years': years, 'months': months,
        'latest_year': latest_year, 'latest_month': latest_month,
    }
    cache.set(ck, data, 600)
    return JsonResponse(data)


# ── Main data API ────────────────────────────────────────────
@login_required(login_url='login')
def channel_data(request):
    region        = request.GET.get('region')
    franchise     = request.GET.get('franchise')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    month_param   = request.GET.get('month')
    year_param    = request.GET.get('year')

    ck = _cache_key('ch_data_v19_', {
        'r': region, 'f': franchise, 'bu': business_unit,
        'a': arm, 'm': month_param, 'y': year_param,
        'sec': request.GET.get('sections', ''),
        'gm':  request.GET.get('growth_metrics', ''),
        'mm':  request.GET.get('monthly_metrics', ''),
        'uid': request.user.id,
    })
    cached = cache.get(ck)
    if cached is not None:
        return JsonResponse(cached)

    qs_base = get_scoped_qs(request.user)
    if region:        qs_base = qs_base.filter(region=region)
    if business_unit: qs_base = qs_base.filter(business_unit=business_unit)
    if arm:           qs_base = qs_base.filter(arm=arm)
    if franchise:     qs_base = qs_base.filter(franchise_id=franchise)

    qs = qs_base
    if year_param:  qs = qs.filter(date__year=int(year_param))
    if month_param: qs = qs.filter(date__month=int(month_param))

    # ── KPI aggregation ──────────────────────────────────────
    agg_fields = {
        'fca_target': Sum('fca_target'), 'fca_ach': Sum('fca_ach'), 'fca_m0': Sum('fca_m0'),
        'g4_target':  Sum('g4_target'),  'g4_ach':  Sum('g4_ach'),
        'mnp_target': Sum('mnp_target'), 'mnp_ach': Sum('mnp_ach'),
        'mbb_target': Sum('mbb_target'), 'mbb_ach': Sum('mbb_ach'),
        'loading_target':    Sum('loading_target'),    'loading_ach':    Sum('loading_ach'),
        'm0_revenue_target': Sum('m0_revenue_target'), 'm0_revenue_ach': Sum('m0_revenue_ach'),
        'bundle_target': Sum('bundle_target'), 'bundle_ach': Sum('bundle_ach'),
        'hvc_target':    Sum('hvc_target'),    'hvc_ach':    Sum('hvc_ach'),
        'qos_target':    Sum('qos_target'),    'qos_ach':    Sum('qos_ach'),
        'evc_active_base':         Sum('evc_active_base'),
        'evc_retailer':            Sum('evc_retailer'),
        'daily_active_evc':        Sum('daily_active_evc'),
        'daily_active_served':     Sum('daily_active_served'),
        'cm_evc_active':           Sum('cm_evc_active'),
        'cm_964_active':           Sum('cm_964_active'),
        'cm_evc_active_platinum':  Sum('cm_evc_active_platinum'),
        'cm_evc_active_gold':      Sum('cm_evc_active_gold'),
        'cm_evc_active_silver':    Sum('cm_evc_active_silver'),
        'cm_964_active_platinum':  Sum('cm_964_active_platinum'),
        'cm_964_active_gold':      Sum('cm_964_active_gold'),
        'cm_964_active_silver':    Sum('cm_964_active_silver'),
        'total_bundles_activated': Sum('total_bundles_activated'),
        'female_fca_count':        Sum('female_fca_count'),
        'cell_sites_count':        Sum('cell_sites_count'),
        'mtd_served':              Sum('mtd_served'),
        'retailer_trans_count_1':  Sum('retailer_trans_count_1'),
        'retailer_trans_count_2':  Sum('retailer_trans_count_2'),
        'sd_bundle':               Sum('sd_bundle'),
        'zr':                      Sum('zr'),
        'dormancy_count':          Sum('dormancy_count'),
        'cm_ga':                   Sum('cm_ga'),
        'uload_recharge_ach':      Sum('uload_recharge_ach'),
        'loading_ach_site_conv':    Sum('loading_ach_site_conv'),
        'total_site_loading':       Sum('total_site_loading'),
        'trans_ge_3_pct':           Sum('trans_ge_3_pct'),
        'npr':                      Sum('npr'),
        'cm_disown':                Sum('cm_disown'),
        'new_sim_sale_disowned_cnics': Sum('new_sim_sale_disowned_cnics'),
        'fca_within_90d_disowned':  Sum('fca_within_90d_disowned'),
        'active_90d_base_disown':   Sum('active_90d_base_disown'),
        'zr_fca':                   Sum('zr_fca'),
        'active_so_daily_avg':      Sum('active_so_daily_avg'),
        'data_sim_fca':             Sum('data_sim_fca'),
        'm0_rev_fca':               Sum('m0_rev_fca'),
        'm0_rev_mnp':               Sum('m0_rev_mnp'),
        'm0_rev_mbb':               Sum('m0_rev_mbb'),
        'm0_rev_data_sim':          Sum('m0_rev_data_sim'),
        'm0_rev_ga':                Sum('m0_rev_ga'),
        'm0_hvc_rev':               Sum('m0_hvc_rev'),
    }
    agg_fields['_latest_date'] = Max('date')
    kpis_raw = qs.aggregate(**agg_fields)
    kpis = {k: safe(v) for k, v in kpis_raw.items() if k != '_latest_date'}

    # ── Stock/closing fields: override with latest-month values ─────────────
    _stock_fields = [
        'cm_evc_active', 'cm_evc_active_platinum', 'cm_evc_active_gold', 'cm_evc_active_silver',
        'cm_964_active', 'cm_964_active_platinum', 'cm_964_active_gold', 'cm_964_active_silver',
        'evc_active_base', 'evc_retailer', 'npr', 'active_so_daily_avg',
        'daily_active_served', 'daily_active_evc',
    ]
    if not month_param:
        _latest = kpis_raw.get('_latest_date')  # free — came from main aggregate
        _stock_qs = qs_base.filter(
            date__year=_latest.year, date__month=_latest.month
        ) if _latest else qs
    else:
        _stock_qs = qs
    _stock_agg = _stock_qs.aggregate(**{f: Sum(f) for f in _stock_fields})
    for _f in _stock_fields:
        kpis[_f] = safe(_stock_agg.get(_f, 0))

    for prefix, ach_f, tgt_f in [
        ('fca',       'fca_ach',        'fca_target'),
        ('g4',        'g4_ach',         'g4_target'),
        ('mnp',       'mnp_ach',        'mnp_target'),
        ('loading',   'loading_ach',    'loading_target'),
        ('m0_revenue','m0_revenue_ach', 'm0_revenue_target'),
        ('bundle',    'bundle_ach',     'bundle_target'),
        ('hvc',       'hvc_ach',        'hvc_target'),
        ('qos',       'qos_ach',        'qos_target'),
    ]:
        kpis[f'{prefix}_attainment'] = attainment(kpis.get(ach_f, 0), kpis.get(tgt_f, 0))

    fca_ach = kpis.get('fca_ach', 0) or 0
    g4_ach  = kpis.get('g4_ach',  0) or 0
    kpis['g4_penetration_pct'] = round((g4_ach / fca_ach) * 100, 1) if fca_ach else 0
    # total_franchises removed — expensive distinct count not used on channel brief

    # ── Sections: only compute what the requesting page needs ──────────────
    # ?sections=kpis,growth,monthly  (defaults to all for backward-compat)
    sections_param = request.GET.get('sections', '')
    want = set(s.strip() for s in sections_param.split(',') if s.strip()) if sections_param else None
    def need(name):
        return want is None or name in want

    response = {'kpis': kpis}

    # Metric subsetting: channel brief only needs 8 KPI metrics for growth+monthly.
    # Other pages need the full set. Detect via sections param.
    _brief_metrics = [
        'fca_ach', 'fca_target', 'g4_ach', 'g4_target',
        'mnp_ach', 'mnp_target', 'loading_ach', 'loading_target',
        'm0_revenue_ach', 'm0_revenue_target',
        'hvc_ach', 'hvc_target', 'bundle_ach', 'bundle_target',
        'cm_evc_active',
    ]
    _sections_set = set(s.strip() for s in sections_param.split(',') if s.strip())
    # Brief-only: has kpis+growth+monthly but NOT quality/enablers-only fields
    _is_brief = request.GET.get('brief') == '1'

    if need('growth'):
        _gm_param = request.GET.get('growth_metrics', '')
        if _gm_param:
            _gmets = [m.strip() for m in _gm_param.split(',') if m.strip()]
        elif _is_brief:
            _gmets = _brief_metrics
        else:
            _gmets = None
        response['growth'] = build_growth_dict(qs_base, metrics=_gmets)

    if need('monthly'):
        trend_qs = qs_base
        if year_param: trend_qs = trend_qs.filter(date__year=int(year_param))
        _mm_param = request.GET.get('monthly_metrics', '')
        _mm_list  = [m.strip() for m in _mm_param.split(',') if m.strip()] if _mm_param else None
        response['monthly'] = build_monthly_trend(trend_qs, metrics=_mm_list)

    if need('breakdowns'):
        response['top_franchises']   = build_top_franchises(qs)
        response['region_breakdown'] = build_region_breakdown(qs)
        response['bu_breakdown']     = build_bu_breakdown(qs)
    cache.set(ck, response, 900)
    return JsonResponse(response)


def build_growth_dict(qs_base, metrics=None):
    """Single conditional aggregation query for all growth periods."""
    _all_metrics = [
        'fca_ach', 'fca_target', 'g4_ach', 'g4_target',
        'mnp_ach', 'mnp_target', 'loading_ach', 'loading_target',
        'm0_revenue_ach', 'm0_revenue_target', 'bundle_ach', 'bundle_target',
        'hvc_ach', 'hvc_target', 'evc_active_base', 'evc_retailer',
        'cm_evc_active', 'cm_964_active', 'total_bundles_activated',
        'cell_sites_count', 'female_fca_count', 'cm_ga', 'uload_recharge_ach',
        'loading_ach_site_conv', 'total_site_loading', 'daily_active_served',
        'daily_active_evc', 'npr', 'active_so_daily_avg', 'zr', 'zr_fca',
        'qos_ach', 'sd_bundle', 'dormancy_count', 'cm_disown',
        'new_sim_sale_disowned_cnics', 'fca_within_90d_disowned',
        'active_90d_base_disown', 'fca_m0',
    ]
    metrics = list(dict.fromkeys(metrics if metrics else _all_metrics))

    latest = qs_base.order_by('-date').values('date').first()
    if not latest:
        return {}

    ly       = latest['date'].year
    lm       = latest['date'].month
    prev_y   = ly - 1
    prev_m   = lm - 1 if lm > 1 else 12
    prev_m_y = ly     if lm > 1 else prev_y

    annotations = {}
    for m in metrics:
        annotations[f'{m}_ytd_c'] = Sum(Case(When(date__year=ly,       date__month__lte=lm, then=m), default=0, output_field=FloatField()))
        annotations[f'{m}_ytd_p'] = Sum(Case(When(date__year=prev_y,   date__month__lte=lm, then=m), default=0, output_field=FloatField()))
        annotations[f'{m}_mtd_c'] = Sum(Case(When(date__year=ly,       date__month=lm,      then=m), default=0, output_field=FloatField()))
        annotations[f'{m}_mtd_p'] = Sum(Case(When(date__year=prev_m_y, date__month=prev_m,  then=m), default=0, output_field=FloatField()))
        annotations[f'{m}_yoy_p'] = Sum(Case(When(date__year=prev_y,   date__month=lm,      then=m), default=0, output_field=FloatField()))

    row = qs_base.aggregate(**annotations)

    def pct(c, p):
        return round(((c - p) / p) * 100, 1) if p else 0

    out = {}
    for m in metrics:
        ytd_c = safe(row.get(f'{m}_ytd_c'))
        ytd_p = safe(row.get(f'{m}_ytd_p'))
        mtd_c = safe(row.get(f'{m}_mtd_c'))
        mtd_p = safe(row.get(f'{m}_mtd_p'))
        yoy_c = mtd_c
        yoy_p = safe(row.get(f'{m}_yoy_p'))
        out[m] = {
            'ytd_curr': ytd_c, 'ytd_prev': ytd_p, 'ytd_pct': pct(ytd_c, ytd_p),
            'mtd_curr': mtd_c, 'mtd_prev': mtd_p, 'mtd_pct': pct(mtd_c, mtd_p),
            'yoy_curr': yoy_c, 'yoy_prev': yoy_p, 'yoy_pct': pct(yoy_c, yoy_p),
        }

    # Closing values for stock fields
    _base_metrics = [m for m in [
        'evc_active_base', 'evc_retailer',
        'cm_evc_active', 'cm_evc_active_platinum', 'cm_evc_active_gold', 'cm_evc_active_silver',
        'cm_964_active', 'cm_964_active_platinum', 'cm_964_active_gold', 'cm_964_active_silver',
        'npr', 'active_so_daily_avg', 'daily_active_served', 'daily_active_evc',
    ] if m in out]

    if _base_metrics:
        closing_rows = (
            qs_base
            .filter(
                Q(date__year=ly,       date__month=lm)       |
                Q(date__year=prev_y,   date__month=lm)       |
                Q(date__year=prev_m_y, date__month=prev_m)
            )
            .values('date__year', 'date__month')
            .annotate(**{f: Sum(f) for f in _base_metrics})
        )
        closing = {(r['date__year'], r['date__month']): r for r in closing_rows}

        def _cv(year, month, field):
            return safe(closing.get((year, month), {}).get(field, 0))

        for m in _base_metrics:
            ytd_c = _cv(ly, lm, m);         ytd_p = _cv(prev_y, lm, m)
            mtd_c = ytd_c;                   mtd_p = _cv(prev_m_y, prev_m, m)
            yoy_c = ytd_c;                   yoy_p = ytd_p
            out[m] = {
                'ytd_curr': ytd_c, 'ytd_prev': ytd_p, 'ytd_pct': pct(ytd_c, ytd_p),
                'mtd_curr': mtd_c, 'mtd_prev': mtd_p, 'mtd_pct': pct(mtd_c, mtd_p),
                'yoy_curr': yoy_c, 'yoy_prev': yoy_p, 'yoy_pct': pct(yoy_c, yoy_p),
            }

    return out


def build_monthly_trend(qs, metrics=None):
    _all_metrics = [
        'fca_ach', 'fca_target', 'g4_ach', 'g4_target',
        'mnp_ach', 'mnp_target', 'mbb_ach', 'mbb_target',
        'loading_ach', 'loading_target',
        'm0_revenue_ach', 'bundle_ach', 'hvc_ach',
        'loading_ach_site_conv', 'total_site_loading', 'uload_recharge_ach',
        'data_sim_fca', 'cm_ga',
        'qos_ach', 'sd_bundle', 'zr', 'zr_fca',
        'dormancy_count', 'female_fca_count',
        'cm_disown', 'new_sim_sale_disowned_cnics',
        'fca_within_90d_disowned', 'active_90d_base_disown',
        'evc_active_base', 'cm_evc_active',
        'cm_evc_active_platinum', 'cm_evc_active_gold', 'cm_evc_active_silver',
        'daily_active_evc', 'daily_active_served',
        'npr', 'active_so_daily_avg', 'cm_964_active',
    ]
    metric_list = metrics if metrics else _all_metrics
    # Stock fields: use Sum() per month — each month's value is already the
    # closing snapshot for that month, so summing daily rows within a month is correct.
    _trend_annot = {f: Sum(f) for f in metric_list}
    rows = (qs.exclude(date__isnull=True)
              .values('date__year', 'date__month')
              .annotate(**_trend_annot))

    by_year = defaultdict(lambda: {m: [None]*12 for m in metric_list})
    for r in rows:
        y, mo = r['date__year'], r['date__month']
        for fld in metric_list:
            by_year[y][fld][mo-1] = safe(r[fld])

    years_sorted = sorted(by_year.keys())
    labels = list(range(1, 13))
    return {
        metric: {
            'labels':   labels,
            'datasets': [{'label': str(y), 'data': by_year[y][metric]} for y in years_sorted],
        }
        for metric in metric_list
    }


def build_top_franchises(qs, metric='m0_revenue_ach', limit=10):
    rows = (qs.exclude(franchise_id='')
              .values('franchise_id', 'city', 'business_unit')
              .annotate(value=Sum(metric))
              .order_by('-value')[:limit])
    return [{'franchise': r['franchise_id'], 'city': r['city'],
             'business_unit': r['business_unit'], 'value': safe(r['value'])} for r in rows]


def build_region_breakdown(qs):
    rows = (qs.exclude(region='').values('region')
              .annotate(fca_ach=Sum('fca_ach'), m0_revenue_ach=Sum('m0_revenue_ach'), loading_ach=Sum('loading_ach'))
              .order_by('-m0_revenue_ach'))
    labels, fca, rev, loading = [], [], [], []
    for r in rows:
        labels.append(r['region'])
        fca.append(safe(r['fca_ach']))
        rev.append(safe(r['m0_revenue_ach']))
        loading.append(safe(r['loading_ach']))
    return {'labels': labels, 'fca': fca, 'm0_revenue': rev, 'loading': loading}


def build_bu_breakdown(qs):
    rows = (qs.exclude(business_unit='').values('business_unit')
              .annotate(fca_ach=Sum('fca_ach'), m0_revenue_ach=Sum('m0_revenue_ach'),
                        loading_ach=Sum('loading_ach'), bundle_ach=Sum('bundle_ach'), hvc_ach=Sum('hvc_ach'))
              .order_by('-m0_revenue_ach'))
    labels, fca, rev, loading, bundles, hvc = [], [], [], [], [], []
    for r in rows:
        labels.append(r['business_unit'])
        fca.append(safe(r['fca_ach']))
        rev.append(safe(r['m0_revenue_ach']))
        loading.append(safe(r['loading_ach']))
        bundles.append(safe(r['bundle_ach']))
        hvc.append(safe(r['hvc_ach']))
    return {'labels': labels, 'fca': fca, 'm0_revenue': rev,
            'loading': loading, 'bundles': bundles, 'hvc': hvc}


# ── Franchise table API ───────────────────────────────────────
@login_required(login_url='login')
def channel_franchise_table(request):
    region        = request.GET.get('region')
    franchise     = request.GET.get('franchise')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    month         = request.GET.get('month')
    year          = request.GET.get('year')
    sort_by       = request.GET.get('sort_by', 'm0_revenue_ach_ytd')
    order         = request.GET.get('order', 'top')
    page          = int(request.GET.get('page', 1))
    page_size     = int(request.GET.get('page_size', 10))

    ck = _cache_key('ch_tbl_', {
        'r': region, 'f': franchise, 'bu': business_unit, 'a': arm,
        'm': month, 'y': year, 'sb': sort_by, 'o': order,
        'pg': page, 'ps': page_size, 'uid': request.user.id,
    })
    cached = cache.get(ck)
    if cached is not None:
        return JsonResponse(cached)

    qs = get_scoped_qs(request.user)
    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise_id=franchise)

    if franchise:          group_field, group_label = 'franchise_id', 'Franchise'
    elif arm:              group_field, group_label = 'franchise_id', 'Franchise'
    elif business_unit:    group_field, group_label = 'arm',          'ARM'
    elif region:           group_field, group_label = 'business_unit','BU'
    else:                  group_field, group_label = 'region',       'Region'

    latest = qs.order_by('-date').values('date').first()
    if not latest:
        return JsonResponse({'rows': [], 'total': 0, 'page': 1, 'pages': 0, 'group_label': group_label})

    ly     = int(year)  if year  else latest['date'].year
    lm     = int(month) if month else latest['date'].month
    prev_y = ly - 1

    metric_fields = ['m0_revenue_ach', 'loading_ach', 'fca_ach', 'bundle_ach']
    annotations = {}
    for mf in metric_fields:
        annotations[f'{mf}_ytd']      = Sum(Case(When(date__year=ly,     date__month__lte=lm, then=mf), default=0, output_field=FloatField()))
        annotations[f'{mf}_yoy']      = Sum(Case(When(date__year=prev_y, date__month__lte=lm, then=mf), default=0, output_field=FloatField()))
        annotations[f'{mf}_mtd']      = Sum(Case(When(date__year=ly,     date__month=lm,      then=mf), default=0, output_field=FloatField()))
        annotations[f'{mf}_mtd_prev'] = Sum(Case(When(date__year=prev_y, date__month=lm,      then=mf), default=0, output_field=FloatField()))

    rows_qs = qs.values(group_field).annotate(**annotations)
    rows = []
    for r in rows_qs:
        name = r.get(group_field) or '—'
        row  = {'group': name, 'group_label': group_label}
        for mf in metric_fields:
            ytd      = safe(r.get(f'{mf}_ytd'))
            yoy_prev = safe(r.get(f'{mf}_yoy'))
            mtd      = safe(r.get(f'{mf}_mtd'))
            mtd_prev = safe(r.get(f'{mf}_mtd_prev'))
            row[f'{mf}_ytd']     = ytd
            row[f'{mf}_ytd_pct'] = round((ytd - yoy_prev) / yoy_prev * 100, 1) if yoy_prev else 0
            row[f'{mf}_yoy']     = yoy_prev
            row[f'{mf}_yoy_pct'] = round((mtd - mtd_prev) / mtd_prev * 100, 1) if mtd_prev else 0
            row[f'{mf}_mtd']     = mtd
            row[f'{mf}_mtd_pct'] = round((mtd - mtd_prev) / mtd_prev * 100, 1) if mtd_prev else 0
        if all(row.get(f'{mf}_ytd', 0) == 0 for mf in metric_fields):
            continue
        rows.append(row)

    sort_key = sort_by + '_pct' if not sort_by.endswith('_pct') else sort_by
    rows.sort(key=lambda r: r.get(sort_key, 0), reverse=(order == 'top'))

    total  = len(rows)
    pages  = max(1, (total + page_size - 1) // page_size)
    page   = max(1, min(page, pages))
    paged  = rows[(page-1)*page_size : page*page_size]

    result = {'rows': paged, 'total': total, 'page': page,
              'pages': pages, 'page_size': page_size, 'group_label': group_label}
    cache.set(ck, result, 300)
    return JsonResponse(result)


# ── Throughput retailer table API ─────────────────────────────
@login_required(login_url='login')
def channel_throughput(request):
    region        = request.GET.get('region')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    franchise     = request.GET.get('franchise')
    month_param   = request.GET.get('month')
    year_param    = request.GET.get('year')

    ck = _cache_key('ch_tput_', {
        'r': region, 'bu': business_unit, 'a': arm, 'f': franchise,
        'm': month_param, 'y': year_param, 'uid': request.user.id,
    })
    cached = cache.get(ck)
    if cached is not None:
        return JsonResponse(cached)

    qs = get_scoped_qs(request.user)
    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise_id=franchise)
    if year_param:    qs = qs.filter(date__year=int(year_param))
    if month_param:   qs = qs.filter(date__month=int(month_param))

    # Stock fields — show latest month when no month selected
    if not month_param:
        _latest = qs.aggregate(d=Max('date'))['d']
        if _latest:
            qs = qs.filter(date__year=_latest.year, date__month=_latest.month)

    if franchise:
        group_field = 'key'
        group_label = 'Site'
    elif arm:
        group_field = 'franchise_id'
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

    base_qs = qs.filter(**{f'{group_field}__isnull': False})
    if group_field != 'key':
        base_qs = base_qs.exclude(**{f'{group_field}': ''})

    rows_qs = (base_qs
                 .values(group_field)
                 .annotate(
                     cnt1=Sum('retailer_trans_count_1'),
                     cnt2=Sum('retailer_trans_count_2'),
                     ge3_pct_sum=Sum('trans_ge_3_pct'),
                     total_evc=Sum('evc_retailer'),
                     total_retailers=Sum('retailer_trans_count_1') + Sum('retailer_trans_count_2'),
                     row_count=Count('id'),
                 )
                 .order_by(group_field))

    rows = []
    total_cnt1 = total_cnt2 = total_evc = total_retailers_sum = 0

    for r in rows_qs:
        cnt1      = safe(r['cnt1'])
        cnt2      = safe(r['cnt2'])
        evc       = safe(r['total_evc'])
        retailers = cnt1 + cnt2
        ge3_pct   = round(safe(r['ge3_pct_sum']) / r['row_count'], 1) if r['row_count'] else 0
        cnt3plus  = max(0, evc - cnt1 - cnt2)

        total_cnt1         += cnt1
        total_cnt2         += cnt2
        total_evc          += evc
        total_retailers_sum += retailers

        rows.append({
            'group':      r[group_field] or '—',
            'label':      group_label,
            'cnt1':       int(cnt1),
            'cnt2':       int(cnt2),
            'cnt3plus':   int(cnt3plus),
            'total':      int(evc),
            'retailers':  int(retailers),
            'ge3_pct':    ge3_pct,
        })

    for row in rows:
        t = row['total'] or 1
        row['cnt1_pct']     = round(row['cnt1']    / t * 100, 1)
        row['cnt2_pct']     = round(row['cnt2']    / t * 100, 1)
        row['cnt3plus_pct'] = round(row['cnt3plus']/ t * 100, 1)
        row['retailers_pct']= round(row['retailers']/ t * 100, 1)

    total_cnt3plus = max(0, total_evc - total_cnt1 - total_cnt2)
    tt = total_evc or 1
    totals = {
        'group': 'TOTAL', 'label': group_label,
        'cnt1': int(total_cnt1), 'cnt1_pct': round(total_cnt1/tt*100,1),
        'cnt2': int(total_cnt2), 'cnt2_pct': round(total_cnt2/tt*100,1),
        'cnt3plus': int(total_cnt3plus), 'cnt3plus_pct': round(total_cnt3plus/tt*100,1),
        'total': int(total_evc), 'ge3_pct': 0,
        'retailers': int(total_retailers_sum),
        'retailers_pct': round(total_retailers_sum/tt*100,1),
    }

    result = {
        'rows': rows,
        'totals': totals,
        'group_label': group_label,
    }
    cache.set(ck, result, 300)
    return JsonResponse(result)


@login_required(login_url='login')
def channel_kpi_summary(request):
    profile = get_or_create_profile_local(request.user)
    return render(request, 'channel/kpi_summary.html', {
        'profile': profile,
        'locked':  get_locked_filters(request.user),
    })


@login_required(login_url='login')
def channel_kpi_table(request):
    region        = request.GET.get('region')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    franchise     = request.GET.get('franchise')
    year_param    = request.GET.get('year')
    month_param   = request.GET.get('month')
    period        = request.GET.get('period', 'ytd')

    qs = get_scoped_qs(request.user)
    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise_id=franchise)
    if year_param:    qs = qs.filter(date__year=int(year_param))
    if month_param:   qs = qs.filter(date__month=int(month_param))

    if franchise:
        group_field, group_label = 'franchise_id', 'Franchise'
    elif arm:
        group_field, group_label = 'franchise_id', 'Franchise'
    elif business_unit:
        group_field, group_label = 'arm',          'ARM'
    elif region:
        group_field, group_label = 'business_unit','BU'
    else:
        group_field, group_label = 'region',       'Region'

    KPI_DEFS = [
        ('fca_ach',       'fca_target',       'FCA',        True),
        ('mnp_ach',       'mnp_target',        'MNP',        True),
        ('g4_ach',        'g4_target',         '4G',         True),
        ('loading_ach',   'loading_target',    'Recharge',   True),
        ('hvc_ach',       'hvc_target',        'HVC',        True),
        ('bundle_ach',    'bundle_target',     'Bundle',     True),
        ('m0_revenue_ach','m0_revenue_target', 'M0 Revenue', True),
        ('cm_ga',         None,                'CM GA',      False),
        ('evc_active_base', None,              'EVC Active', False),
        ('cm_evc_active',   None,              'CM EVC',     False),
        ('zr',            'zr_fca',            'ZR',         True),
        ('qos_ach',       None,                'QOS',        False),
    ]
    ach_fields = [d[0] for d in KPI_DEFS]
    tgt_fields = [d[1] for d in KPI_DEFS if d[1]]
    all_fields = list(set(ach_fields + tgt_fields))

    # ── Latest date for growth reference ────────────────────────────
    base_qs = get_scoped_qs(request.user)
    if region:        base_qs = base_qs.filter(region=region)
    if business_unit: base_qs = base_qs.filter(business_unit=business_unit)
    if arm:           base_qs = base_qs.filter(arm=arm)
    if franchise:     base_qs = base_qs.filter(franchise_id=franchise)

    # ── Reference period: honor explicit year/month filters; otherwise
    # fall back to the latest available date (previous behaviour). ──────
    ref_qs = base_qs
    if year_param:  ref_qs = ref_qs.filter(date__year=int(year_param))
    if month_param: ref_qs = ref_qs.filter(date__month=int(month_param))

    latest = ref_qs.order_by('-date').values('date').first()
    if not latest:
        latest = base_qs.order_by('-date').values('date').first()
    if not latest:
        return JsonResponse({'rows': [], 'group_label': group_label, 'kpi_defs': []})

    ly       = latest['date'].year
    lm       = latest['date'].month
    prev_y   = ly - 1
    prev_m   = lm - 1 if lm > 1 else 12
    prev_m_y = ly if lm > 1 else prev_y

    # ── Current period values — mirrors prev_qs's period-aware logic so
    # both sides of the % change comparison are computed the same way
    # (cumulative Jan-through-lm for YTD, single month for GOLM/YOY).
    # Previously this just Summed whatever qs.filter(date__year=...,
    # date__month=...) happened to select — for YTD that meant comparing
    # a single selected month's value against a 5-month CUMULATIVE prior
    # value, and for GOLM/YOY with only a year chosen (no month), it
    # summed the WHOLE YEAR as "current" against one month as "previous".
    if period == 'ytd':
        curr_annot = {
            f: Sum(Case(When(date__year=ly, date__month__lte=lm, then=f),
                        default=0, output_field=FloatField()))
            for f in all_fields
        }
    elif period == 'golm':
        curr_annot = {
            f: Sum(Case(When(date__year=ly, date__month=lm, then=f),
                        default=0, output_field=FloatField()))
            for f in all_fields
        }
    else:  # yoy
        curr_annot = {
            f: Sum(Case(When(date__year=ly, date__month=lm, then=f),
                        default=0, output_field=FloatField()))
            for f in all_fields
        }

    curr_qs = (base_qs
               .exclude(**{f'{group_field}__isnull': True})
               .exclude(**{f'{group_field}': ''})
               .values(group_field)
               .annotate(**curr_annot))
    curr_map = {r[group_field]: r for r in curr_qs}

    # ── Previous period values — 1 query using Case/When ────────────
    if period == 'ytd':
        prev_annot = {
            f: Sum(Case(When(date__year=prev_y, date__month__lte=lm, then=f),
                        default=0, output_field=FloatField()))
            for f in ach_fields
        }
    elif period == 'golm':
        prev_annot = {
            f: Sum(Case(When(date__year=prev_m_y, date__month=prev_m, then=f),
                        default=0, output_field=FloatField()))
            for f in ach_fields
        }
    else:  # yoy
        prev_annot = {
            f: Sum(Case(When(date__year=prev_y, date__month=lm, then=f),
                        default=0, output_field=FloatField()))
            for f in ach_fields
        }

    prev_qs = (base_qs
               .exclude(**{f'{group_field}__isnull': True})
               .exclude(**{f'{group_field}': ''})
               .values(group_field)
               .annotate(**prev_annot))
    prev_map = {r[group_field]: r for r in prev_qs}

    # ── Build rows ───────────────────────────────────────────────────
    def s(v): return float(v) if v else 0.0
    def tva(a, t): return round(a/t*100, 1) if t and t > 0 else None
    def pct_chg(curr, prev):
        if not prev: return None
        return round((curr - prev) / abs(prev) * 100, 1)
    def suggest(label, tva_v, chg):
        out = []
        if tva_v is not None and tva_v < 80:
            out.append(f'{label} TVA critically low ({tva_v}%) — immediate focus needed')
        elif tva_v is not None and tva_v < 90:
            out.append(f'{label} TVA below target ({tva_v}%) — review strategy')
        if chg is not None and chg < -10:
            out.append(f'{label} declining {abs(chg)}% vs prior period')
        return out

    rows = []
    for grp, cr in sorted(curr_map.items()):
        pr = prev_map.get(grp, {})
        if all(s(cr.get(f, 0)) == 0 for f in ach_fields):
            continue
        kpis_row = []
        all_issues = []
        for ach_f, tgt_f, label, has_tva in KPI_DEFS:
            ach   = s(cr.get(ach_f))
            tgt   = s(cr.get(tgt_f)) if tgt_f else None
            tva_v = tva(ach, tgt) if tgt else None
            prev_v = s(pr.get(ach_f, 0))
            chg    = pct_chg(ach, prev_v)
            all_issues += suggest(label, tva_v, chg)
            kpis_row.append({'label': label, 'ach': ach, 'tgt': tgt,
                             'tva': tva_v, 'chg': chg, 'has_tva': has_tva})
        rows.append({'group': grp, 'kpis': kpis_row, 'issues': all_issues[:3]})

    kpi_defs = [{'label': d[2], 'has_tva': d[3]} for d in KPI_DEFS]
    return JsonResponse({
        'rows': rows, 'group_label': group_label,
        'kpi_defs': kpi_defs, 'period': period,
        'ref_year': ly, 'ref_month': lm,
    })