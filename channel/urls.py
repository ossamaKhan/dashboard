from django.urls import path
from channel.views import *

app_name = 'channel'

urlpatterns = [
    path('',                    channel_dashboard,        name='channel_dashboard'),
    path('performance/',        channel_performance,      name='channel_performance'),
    path('retailers/',          channel_retailers,        name='channel_retailers'),
    path('enablers/',           channel_enablers,         name='channel_enablers'),
    path('api/data/',           channel_data,             name='channel_data'),
    path('api/filters/',        channel_filters,          name='channel_filters'),
    path('api/franchise-table/',channel_franchise_table,  name='channel_franchise_table'),
    path('api/throughput/',     channel_throughput,       name='channel_throughput'),  # ← add this
    path('quality/', channel_quality, name='channel_quality'),
    path('kpi-summary/',      channel_kpi_summary, name='channel_kpi_summary'),
    path('api/kpi-table/',    channel_kpi_table,   name='channel_kpi_table'),
]