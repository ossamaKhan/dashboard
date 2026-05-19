"""
Channel views — mirrors marketing/views.py structure.
Filter pattern: Region → BU → Franchise → Year/Month (or date range internally).
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Sum, Avg, Q, Case, When, FloatField, IntegerField
from datetime import date, datetime
from collections import defaultdict
from calendar import monthrange

from .models import ChannelDaily


# ── Helpers ──────────────────────────────────────────────────
def safe(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0


def attainment(ach, target):
    """Achievement as % of target."""
    return round((ach / target) * 100, 1) if target else 0


def get_scoped_qs(user):
    """Apply role-based access. Mirror marketing pattern.
    Adjust based on your existing role logic (e.g. UserProfile model with region/bu lock)."""
    qs = ChannelDaily.objects.all()
    # If you have a profile model that locks region/bu, apply it here:
    # try:
    #     prof = user.profile
    #     if prof.locked_region:        qs = qs.filter(region=prof.locked_region)
    #     if prof.locked_business_unit: qs = qs.filter(business_unit=prof.locked_business_unit)
    # except UserProfile.DoesNotExist:
    #     pass
    return qs


def apply_filters(qs, request):
    """Read filter params from request and apply to queryset."""
    region        = request.GET.get('region')
    franchise     = request.GET.get('franchise')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    month         = request.GET.get('month')
    year          = request.GET.get('year')

    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise_id=franchise)

    if year:
        qs = qs.filter(date__year=int(year))
    if month:
        qs = qs.filter(date__month=int(month))

    return qs


def get_locked_context(user):
    """Returns dict for template lock display. Adjust based on your role model."""
    # Stub — adapt to your existing UserProfile pattern from marketing
    return {
        'category': None,
        'region':   {'locked': False, 'value': None},
        'bu':       {'locked': False, 'value': None},
    }


# ── Pages ────────────────────────────────────────────────────
@login_required
def channel_dashboard(request):
    return render(request, 'channel/index.html', {
        'locked': get_locked_context(request.user),
    })


@login_required
def channel_performance(request):
    return render(request, 'channel/performance.html', {
        'locked': get_locked_context(request.user),
    })


@login_required
def channel_retailers(request):
    return render(request, 'channel/retailers.html', {
        'locked': get_locked_context(request.user),
    })


# ── Filter options API ───────────────────────────────────────
@login_required
def channel_filters(request):
    qs = get_scoped_qs(request.user)
    region        = request.GET.get('region')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)

    # ARM narrows by region + bu; franchise narrows further by arm
    arm_qs = qs
    fr_qs  = qs.filter(arm=arm) if arm else qs

    regions       = sorted(qs.exclude(region='').values_list('region', flat=True).distinct())
    bus           = sorted(qs.exclude(business_unit='').values_list('business_unit', flat=True).distinct())
    arms          = sorted(arm_qs.exclude(arm__isnull=True).exclude(arm='').values_list('arm', flat=True).distinct())
    franchises    = sorted(fr_qs.exclude(franchise_id='').values_list('franchise_id', flat=True).distinct())
    years         = sorted({d.year for d in qs.values_list('date', flat=True).distinct() if d}, reverse=True)
    months        = list(range(1, 13))

    latest_date   = qs.aggregate(d=models_max('date'))['d'] if False else qs.order_by('-date').values_list('date', flat=True).first()
    latest_year   = latest_date.year if latest_date else None
    latest_month  = latest_date.month if latest_date else None

    return JsonResponse({
        'regions':         regions,
        'business_units':  bus,
        'arms':            arms,
        'franchises':      franchises,
        'years':           years,
        'months':          months,
        'latest_year':     latest_year,
        'latest_month':    latest_month,
    })


# Hack-fix import for clarity
from django.db.models import Max as models_max


# ── Main data API ────────────────────────────────────────────
@login_required
def channel_data(request):
    """KPI cards, growth comparisons, monthly trends, top franchises."""
    qs_base = get_scoped_qs(request.user)
    # Apply non-date filters
    region        = request.GET.get('region')
    franchise     = request.GET.get('franchise')
    business_unit = request.GET.get('business_unit')
    arm           = request.GET.get('arm')
    if region:        qs_base = qs_base.filter(region=region)
    if business_unit: qs_base = qs_base.filter(business_unit=business_unit)
    if arm:           qs_base = qs_base.filter(arm=arm)
    if franchise:     qs_base = qs_base.filter(franchise_id=franchise)

    # Now apply year/month for "current" KPIs
    month_param = request.GET.get('month')
    year_param  = request.GET.get('year')
    qs = qs_base
    if year_param:  qs = qs.filter(date__year=int(year_param))
    if month_param: qs = qs.filter(date__month=int(month_param))

    # ── Aggregate KPIs over selected period ──────────────────
    agg_fields = {
        'fca_target': Sum('fca_target'), 'fca_ach': Sum('fca_ach'),
        'g4_target':  Sum('g4_target'),  'g4_ach':  Sum('g4_ach'),
        'mnp_target': Sum('mnp_target'), 'mnp_ach': Sum('mnp_ach'),
        'mbb_target': Sum('mbb_target'), 'mbb_ach': Sum('mbb_ach'),
        'loading_target':   Sum('loading_target'),   'loading_ach':   Sum('loading_ach'),
        'm0_revenue_target':Sum('m0_revenue_target'),'m0_revenue_ach':Sum('m0_revenue_ach'),
        'bundle_target': Sum('bundle_target'), 'bundle_ach': Sum('bundle_ach'),
        'hvc_target':    Sum('hvc_target'),    'hvc_ach':    Sum('hvc_ach'),
        'qos_target':    Sum('qos_target'),    'qos_ach':    Sum('qos_ach'),
        'evc_active_base':       Sum('evc_active_base'),
        'evc_retailer':          Sum('evc_retailer'),
        'daily_active_evc':      Sum('daily_active_evc'),
        'daily_active_served':   Sum('daily_active_served'),
        'cm_evc_active':         Sum('cm_evc_active'),
        'cm_964_active':         Sum('cm_964_active'),
        'cm_evc_active_platinum':Sum('cm_evc_active_platinum'),
        'cm_evc_active_gold':    Sum('cm_evc_active_gold'),
        'cm_evc_active_silver':  Sum('cm_evc_active_silver'),
        'total_bundles_activated': Sum('total_bundles_activated'),
        'female_fca_count':      Sum('female_fca_count'),
        'cell_sites_count':      Sum('cell_sites_count'),
        'mtd_served':            Sum('mtd_served'),
        'retailer_trans_count_1':Sum('retailer_trans_count_1'),
        'retailer_trans_count_2':Sum('retailer_trans_count_2'),
    }
    kpis_raw = qs.aggregate(**agg_fields)
    kpis = {k: safe(v) for k, v in kpis_raw.items()}

    # Compute attainment percentages for paired metrics
    paired = [
        ('fca',         'fca_ach',         'fca_target'),
        ('g4',          'g4_ach',          'g4_target'),
        ('mnp',         'mnp_ach',         'mnp_target'),
        ('loading',     'loading_ach',     'loading_target'),
        ('m0_revenue',  'm0_revenue_ach',  'm0_revenue_target'),
        ('bundle',      'bundle_ach',      'bundle_target'),
        ('hvc',         'hvc_ach',         'hvc_target'),
        ('qos',         'qos_ach',         'qos_target'),
    ]
    for prefix, ach_f, tgt_f in paired:
        kpis[f'{prefix}_attainment'] = attainment(kpis.get(ach_f, 0), kpis.get(tgt_f, 0))

    # 4G Penetration as % — share of FCA acquisitions that are 4G
    fca_ach = kpis.get('fca_ach', 0) or 0
    g4_ach  = kpis.get('g4_ach', 0) or 0
    kpis['g4_penetration_pct'] = round((g4_ach / fca_ach) * 100, 1) if fca_ach else 0

    # Number of distinct franchises in scope
    kpis['total_franchises'] = qs.exclude(franchise_id='').values('franchise_id').distinct().count()

    # ── Growth: YTD / MTD / YOY comparisons ──────────────────
    growth = build_growth_dict(qs_base, year_param, month_param)

    # ── Monthly trend (current year by month) ────────────────
    trend_qs = qs_base
    if year_param: trend_qs = trend_qs.filter(date__year=int(year_param))
    monthly = build_monthly_trend(trend_qs)

    # ── Top franchises by attainment ─────────────────────────
    top_franchises = build_top_franchises(qs, metric='m0_revenue_ach', limit=10)

    # ── Region breakdown ─────────────────────────────────────
    region_breakdown = build_region_breakdown(qs)

    # ── BU breakdown ─────────────────────────────────────────
    bu_breakdown = build_bu_breakdown(qs)

    return JsonResponse({
        'kpis':              kpis,
        'growth':            growth,
        'monthly':           monthly,
        'top_franchises':    top_franchises,
        'region_breakdown':  region_breakdown,
        'bu_breakdown':      bu_breakdown,
    })


def build_growth_dict(qs_base, year_param, month_param):
    """For each metric, compute YTD/MTD/YOY current vs previous with pct."""
    metrics = [
        'fca_ach', 'fca_target',
        'g4_ach', 'g4_target',
        'mnp_ach', 'mnp_target',
        'loading_ach', 'loading_target',
        'm0_revenue_ach', 'm0_revenue_target',
        'bundle_ach', 'bundle_target',
        'hvc_ach', 'hvc_target',
        'evc_active_base', 'evc_retailer',
        'cm_evc_active', 'cm_964_active',
        'total_bundles_activated', 'cell_sites_count',
        'female_fca_count',
    ]

    # Determine reference year/month
    latest = qs_base.order_by('-date').values('date').first()
    if not latest:
        return {}
    ly = int(year_param) if year_param else latest['date'].year
    lm = int(month_param) if month_param else latest['date'].month
    prev_y = ly - 1
    prev_m = lm - 1 if lm > 1 else 12
    prev_m_y = ly if lm > 1 else prev_y

    agg_kwargs = {m: Sum(m) for m in metrics}

    def agg_for(qfilter):
        r = qs_base.filter(qfilter).aggregate(**agg_kwargs)
        return {k: safe(v) for k, v in r.items()}

    ytd_curr_q = Q(date__year=ly, date__month__lte=lm)
    ytd_prev_q = Q(date__year=prev_y, date__month__lte=lm)
    mtd_curr_q = Q(date__year=ly, date__month=lm)
    mtd_prev_q = Q(date__year=prev_m_y, date__month=prev_m)
    yoy_curr_q = Q(date__year=ly, date__month=lm)
    yoy_prev_q = Q(date__year=prev_y, date__month=lm)

    ytd_curr = agg_for(ytd_curr_q)
    ytd_prev = agg_for(ytd_prev_q)
    mtd_curr = agg_for(mtd_curr_q)
    mtd_prev = agg_for(mtd_prev_q)
    yoy_curr = agg_for(yoy_curr_q)
    yoy_prev = agg_for(yoy_prev_q)

    def pct(c, p):
        return round(((c - p) / p) * 100, 1) if p else 0

    out = {}
    for m in metrics:
        out[m] = {
            'ytd_curr': ytd_curr[m], 'ytd_prev': ytd_prev[m], 'ytd_pct': pct(ytd_curr[m], ytd_prev[m]),
            'mtd_curr': mtd_curr[m], 'mtd_prev': mtd_prev[m], 'mtd_pct': pct(mtd_curr[m], mtd_prev[m]),
            'yoy_curr': yoy_curr[m], 'yoy_prev': yoy_prev[m], 'yoy_pct': pct(yoy_curr[m], yoy_prev[m]),
        }
    return out


def build_monthly_trend(qs):
    """Returns datasets keyed by year, with 12 months of FCA, MNP, Loading, M0 Revenue ach values."""
    rows = (qs.exclude(date__isnull=True)
              .annotate(yr=Case(When(date__isnull=False, then='date__year'), output_field=IntegerField()))
              .values('date__year', 'date__month')
              .annotate(
                  fca_ach=Sum('fca_ach'),
                  mnp_ach=Sum('mnp_ach'),
                  mbb_ach=Sum('mbb_ach'),
                  loading_ach=Sum('loading_ach'),
                  m0_revenue_ach=Sum('m0_revenue_ach'),
                  bundle_ach=Sum('bundle_ach'),
                  hvc_ach=Sum('hvc_ach'),
              ))

    by_year = defaultdict(lambda: {m: [None]*12 for m in [
        'fca_ach','mnp_ach','mbb_ach','loading_ach','m0_revenue_ach','bundle_ach','hvc_ach'
    ]})
    for r in rows:
        y, m = r['date__year'], r['date__month']
        for fld in ['fca_ach','mnp_ach','mbb_ach','loading_ach','m0_revenue_ach','bundle_ach','hvc_ach']:
            by_year[y][fld][m-1] = safe(r[fld])

    # Convert to chart-friendly structure
    labels = list(range(1, 13))
    years_sorted = sorted(by_year.keys())
    series = {}
    for metric in ['fca_ach','mnp_ach','mbb_ach','loading_ach','m0_revenue_ach','bundle_ach','hvc_ach']:
        series[metric] = {
            'labels':   labels,
            'datasets': [{'label': str(y), 'data': by_year[y][metric]} for y in years_sorted],
        }
    return series


def build_top_franchises(qs, metric='m0_revenue_ach', limit=10):
    rows = (qs.exclude(franchise_id='')
              .values('franchise_id', 'city', 'business_unit')
              .annotate(value=Sum(metric))
              .order_by('-value')[:limit])
    return [{
        'franchise':     r['franchise_id'],
        'city':          r['city'],
        'business_unit': r['business_unit'],
        'value':         safe(r['value']),
    } for r in rows]


def build_region_breakdown(qs):
    rows = (qs.exclude(region='')
              .values('region')
              .annotate(
                  fca_ach=Sum('fca_ach'),
                  m0_revenue_ach=Sum('m0_revenue_ach'),
                  loading_ach=Sum('loading_ach'),
              )
              .order_by('-m0_revenue_ach'))
    labels, fca, rev, loading = [], [], [], []
    for r in rows:
        labels.append(r['region'])
        fca.append(safe(r['fca_ach']))
        rev.append(safe(r['m0_revenue_ach']))
        loading.append(safe(r['loading_ach']))
    return {'labels': labels, 'fca': fca, 'm0_revenue': rev, 'loading': loading}


def build_bu_breakdown(qs):
    rows = (qs.exclude(business_unit='')
              .values('business_unit')
              .annotate(
                  fca_ach=Sum('fca_ach'),
                  m0_revenue_ach=Sum('m0_revenue_ach'),
                  loading_ach=Sum('loading_ach'),
                  bundle_ach=Sum('bundle_ach'),
                  hvc_ach=Sum('hvc_ach'),
              )
              .order_by('-m0_revenue_ach'))
    labels, fca, rev, loading, bundles, hvc = [], [], [], [], [], []
    for r in rows:
        labels.append(r['business_unit'])
        fca.append(safe(r['fca_ach']))
        rev.append(safe(r['m0_revenue_ach']))
        loading.append(safe(r['loading_ach']))
        bundles.append(safe(r['bundle_ach']))
        hvc.append(safe(r['hvc_ach']))
    return {
        'labels': labels, 'fca': fca, 'm0_revenue': rev,
        'loading': loading, 'bundles': bundles, 'hvc': hvc,
    }


# ── Franchise performance table API ──────────────────────────
@login_required
def channel_franchise_table(request):
    """Paginated, sortable franchise/BU/region ranking by selected metric."""
    qs = get_scoped_qs(request.user)
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

    if region:        qs = qs.filter(region=region)
    if business_unit: qs = qs.filter(business_unit=business_unit)
    if arm:           qs = qs.filter(arm=arm)
    if franchise:     qs = qs.filter(franchise_id=franchise)

    # Determine grouping
    if franchise:
        group_field = 'franchise_id'
        group_label = 'Franchise'
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

    latest = qs.order_by('-date').values('date').first()
    if not latest:
        return JsonResponse({'rows': [], 'total': 0, 'page': 1, 'pages': 0, 'group_label': group_label})

    ly = int(year) if year else latest['date'].year
    lm = int(month) if month else latest['date'].month
    prev_y = ly - 1

    # Single-query conditional aggregation across three periods
    metric_fields = ['m0_revenue_ach', 'loading_ach', 'fca_ach', 'bundle_ach']
    annotations = {}
    for mf in metric_fields:
        annotations[f'{mf}_ytd']  = Sum(Case(When(date__year=ly, date__month__lte=lm, then=mf), default=0, output_field=FloatField()))
        annotations[f'{mf}_yoy']  = Sum(Case(When(date__year=prev_y, date__month__lte=lm, then=mf), default=0, output_field=FloatField()))
        annotations[f'{mf}_mtd']  = Sum(Case(When(date__year=ly, date__month=lm, then=mf), default=0, output_field=FloatField()))
        annotations[f'{mf}_mtd_prev'] = Sum(Case(When(date__year=prev_y, date__month=lm, then=mf), default=0, output_field=FloatField()))

    rows_qs = qs.values(group_field).annotate(**annotations)

    rows = []
    for r in rows_qs:
        name = r.get(group_field) or '—'
        row = {'group': name, 'group_label': group_label}
        for mf in metric_fields:
            ytd      = safe(r.get(f'{mf}_ytd'))
            yoy_prev = safe(r.get(f'{mf}_yoy'))
            mtd      = safe(r.get(f'{mf}_mtd'))
            mtd_prev = safe(r.get(f'{mf}_mtd_prev'))
            row[f'{mf}_ytd']      = ytd
            row[f'{mf}_ytd_pct']  = round((ytd - yoy_prev) / yoy_prev * 100, 1) if yoy_prev else 0
            row[f'{mf}_yoy']      = yoy_prev
            row[f'{mf}_yoy_pct']  = round((mtd - mtd_prev) / mtd_prev * 100, 1) if mtd_prev else 0
            row[f'{mf}_mtd']      = mtd
            row[f'{mf}_mtd_pct']  = round((mtd - mtd_prev) / mtd_prev * 100, 1) if mtd_prev else 0
        # Skip rows with no activity in selected period
        if all(row.get(f'{mf}_ytd', 0) == 0 for mf in metric_fields):
            continue
        rows.append(row)

    # Sort by % change for the chosen metric
    sort_key = sort_by + '_pct' if not sort_by.endswith('_pct') else sort_by
    rows.sort(key=lambda r: r.get(sort_key, 0), reverse=(order == 'top'))

    total = len(rows)
    pages = max(1, (total + page_size - 1) // page_size)
    page  = max(1, min(page, pages))
    start = (page - 1) * page_size
    paged = rows[start:start + page_size]

    return JsonResponse({
        'rows':        paged,
        'total':       total,
        'page':        page,
        'pages':       pages,
        'page_size':   page_size,
        'group_label': group_label,
    })