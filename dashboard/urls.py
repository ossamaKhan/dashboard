from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from marketing.views import (
    login_view, register_view, logout_view,
    dashboard, base_page, profile_view,
    dashboard_data, filter_options, map_data,
    nearby_sites, chat_page, chat_messages, chat_users, chat_rooms,
    push_subscribe, push_vapid_public,
    revenue_page, export_kml, bu_boundaries_json, site_performance_table,
    site_search, setup_chat_rooms, delete_chat_room, chat_room_members,
    site_map_page, performance_ranking_page,
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
    path('site-map/',           site_map_page,           name='site_map_page'),
    path('performance-ranking/', performance_ranking_page, name='performance_ranking_page'),
    path('chat/',               chat_page,               name='chat'),
    path('api/data/',           dashboard_data,          name='dashboard_data'),
    path('api/filters/',        filter_options,          name='filter_options'),
    path('api/map/',            map_data,                name='map_data'),
    path('api/site-search/', site_search,        name='site_search'),
    path('api/nearby/',         nearby_sites,            name='nearby_sites'),
    path('api/chat/messages/',  chat_messages,           name='chat_messages'),
    path('api/chat/rooms/',     chat_rooms,              name='chat_rooms'),
    path('api/chat/members/',   chat_room_members,       name='chat_room_members'),
    path('api/chat/users/',     chat_users,              name='chat_users'),
    path('api/push/subscribe/', push_subscribe,          name='push_subscribe'),
    path('api/push/vapid/',     push_vapid_public,       name='push_vapid'),
    path('api/sites.kml/',      export_kml,              name='export_kml'),
    path('api/bu-boundaries/',  bu_boundaries_json,      name='bu_boundaries'),
    path('api/site-table/',     site_performance_table,  name='site_table'),
    path('api/export/',         include('exports.urls')),
    path('admin-panel/',        include('admin_panel.urls')),
    path('channel/',            include('channel.urls')),
    path('tools/setup-chat-rooms/', setup_chat_rooms, name='setup_chat_rooms'),
    path('tools/delete-room/<slug:slug>/', delete_chat_room, name='delete_chat_room'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)