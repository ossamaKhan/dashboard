"""
add_indexes.py — run once from your project root:
    python add_indexes.py

Creates all performance indexes on Neon PostgreSQL via Django's DB connection.
Safe to re-run — all use IF NOT EXISTS.
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
django.setup()

from django.db import connection

INDEXES = [
    # ── marketing SiteData ────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_sd_year            ON site_data(year)",
    "CREATE INDEX IF NOT EXISTS idx_sd_region          ON site_data(region)",
    "CREATE INDEX IF NOT EXISTS idx_sd_bu              ON site_data(business_unit)",
    "CREATE INDEX IF NOT EXISTS idx_sd_franchise       ON site_data(franchise)",
    "CREATE INDEX IF NOT EXISTS idx_sd_arm             ON site_data(arm)",
    "CREATE INDEX IF NOT EXISTS idx_sd_month           ON site_data(month)",
    "CREATE INDEX IF NOT EXISTS idx_sd_technology      ON site_data(technology)",
    "CREATE INDEX IF NOT EXISTS idx_sd_year_month      ON site_data(year, month)",
    "CREATE INDEX IF NOT EXISTS idx_sd_region_year     ON site_data(region, year)",
    "CREATE INDEX IF NOT EXISTS idx_sd_bu_year         ON site_data(business_unit, year)",
    "CREATE INDEX IF NOT EXISTS idx_sd_region_bu_year  ON site_data(region, business_unit, year)",

    # ── channel ChannelDaily ──────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_ch_date            ON channel_channeldaily(date)",
    "CREATE INDEX IF NOT EXISTS idx_ch_date_year       ON channel_channeldaily((EXTRACT(YEAR  FROM date)::int))",
    "CREATE INDEX IF NOT EXISTS idx_ch_date_month      ON channel_channeldaily((EXTRACT(MONTH FROM date)::int))",
    "CREATE INDEX IF NOT EXISTS idx_ch_region          ON channel_channeldaily(region)",
    "CREATE INDEX IF NOT EXISTS idx_ch_bu              ON channel_channeldaily(business_unit)",
    "CREATE INDEX IF NOT EXISTS idx_ch_arm             ON channel_channeldaily(arm)",
    "CREATE INDEX IF NOT EXISTS idx_ch_franchise       ON channel_channeldaily(franchise_id)",
    "CREATE INDEX IF NOT EXISTS idx_ch_region_date     ON channel_channeldaily(region, date)",
    "CREATE INDEX IF NOT EXISTS idx_ch_bu_date         ON channel_channeldaily(business_unit, date)",
    "CREATE INDEX IF NOT EXISTS idx_ch_arm_date        ON channel_channeldaily(arm, date)",
    "CREATE INDEX IF NOT EXISTS idx_ch_region_bu_date  ON channel_channeldaily(region, business_unit, date)",

    # ── Partial indexes for common filter combos ──────────────
    "CREATE INDEX IF NOT EXISTS idx_sd_year_2025       ON site_data(region, business_unit, arm, franchise) WHERE year = 2025",
    "CREATE INDEX IF NOT EXISTS idx_sd_year_2026       ON site_data(region, business_unit, arm, franchise) WHERE year = 2026",
]

with connection.cursor() as cursor:
    ok = 0
    for sql in INDEXES:
        name = sql.split('idx_')[1].split(' ')[0] if 'idx_' in sql else sql[:40]
        try:
            cursor.execute(sql)
            print(f"  ✓ {name}")
            ok += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")

print(f"\n{ok}/{len(INDEXES)} indexes created successfully.")
print("\nRun ANALYZE to update query planner statistics:")
print("  python -c \"import os,django; os.environ['DJANGO_SETTINGS_MODULE']='dashboard.settings'; django.setup(); from django.db import connection; cursor=connection.cursor(); cursor.execute('ANALYZE site_data'); cursor.execute('ANALYZE channel_channeldaily'); print('ANALYZE done')\"")