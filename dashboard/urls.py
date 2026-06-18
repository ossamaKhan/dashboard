from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from marketing.views import (
    login_view, register_view, logout_view,
    dashboard, base_page, profile_view,
    dashboard_data, filter_options, map_data,
    nearby_sites, chat_page, chat_messages, chat_users,
    revenue_page, export_kml, bu_boundaries_json, site_performance_table,site_search,
)

urlpatterns = [
    path('admin/',              admin.site.urls),
    path('',                    login_view,              name='login'),
    path('register/',           register_view,           name='register'),
    path('logout/',             logout_view,             name='logout'),
    path('dashboard/',          dashboard,               name='dashboard'),
    path('base/',               base_page,               name='base_page'),
    path('profile/',            profile_view,            name='profile'),
    path('revenue/',            revenue_page,            name='revenue'),
    path('chat/',               chat_page,               name='chat'),
    path('api/data/',           dashboard_data,          name='dashboard_data'),
    path('api/filters/',        filter_options,          name='filter_options'),
    path('api/map/',            map_data,                name='map_data'),
    path('api/site-search/',  site_search, name='site_search'),
    path('api/nearby/',         nearby_sites,            name='nearby_sites'),
    path('api/chat/messages/',  chat_messages,           name='chat_messages'),
    path('api/chat/users/',     chat_users,              name='chat_users'),
    path('api/sites.kml/',      export_kml,              name='export_kml'),
    path('api/bu-boundaries/',  bu_boundaries_json,      name='bu_boundaries'),
    path('api/site-table/',     site_performance_table,  name='site_table'),
    path('api/export/',         include('exports.urls')),
    path('admin-panel/',        include('admin_panel.urls')),
    path('channel/',            include('channel.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)