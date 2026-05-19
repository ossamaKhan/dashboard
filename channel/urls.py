from django.urls import path
from . import views

app_name = 'channel'

urlpatterns = [
    path('',                 views.channel_dashboard,     name='dashboard'),
    path('performance/',     views.channel_performance,   name='performance'),
    path('retailers/',       views.channel_retailers,     name='retailers'),
    path('api/data/',        views.channel_data,          name='data'),
    path('api/filters/',     views.channel_filters,       name='filters'),
    path('api/franchise-table/', views.channel_franchise_table, name='franchise_table'),
]