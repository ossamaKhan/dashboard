from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/',     views.admin_login_view, name='admin_login'),
    path('',           views.admin_dashboard,  name='admin_dashboard'),

    # Site Data CRUD
    path('sites/',              views.site_data_list,   name='admin_site_data_list'),
    path('sites/create/',       views.site_data_create, name='admin_site_data_create'),
    path('sites/<int:pk>/edit/', views.site_data_edit,  name='admin_site_data_edit'),
    path('sites/<int:pk>/delete/', views.site_data_delete, name='admin_site_data_delete'),

    # User CRUD
    path('users/',                          views.user_list,          name='admin_user_list'),
    path('users/create/',                   views.user_create,        name='admin_user_create'),
    path('users/<int:pk>/edit/',            views.user_edit,          name='admin_user_edit'),
    path('users/<int:pk>/delete/',          views.user_delete,        name='admin_user_delete'),
    path('users/<int:pk>/toggle-active/',   views.user_toggle_active, name='admin_user_toggle_active'),

    # Import / Export / Logs
    path('import/', views.import_data,  name='import_data'),
    path('import/', views.import_data,  name='admin_import_data'),
    path('wipe/',   views.wipe_data,    name='wipe_data'),
    path('export/', views.export_data,  name='export_data'),
    path('logs/',            views.admin_logs,       name='admin_logs'),
    path('login-activity/',  views.login_activity,  name='login_activity'),
]