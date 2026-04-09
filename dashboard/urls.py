from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from marketing.views import *

urlpatterns = [
    path('admin/', admin.site.urls),  # Django built-in admin
    path('', login_view, name='login'),  # Regular user login
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('profile/', profile_view, name='profile'),
    path('api/data/', dashboard_data, name='dashboard_data'),
    path('api/filters/', filter_options, name='filter_options'),
    path('admin-panel/', include('admin_panel.urls')),  # Custom admin panel with its own login
    path('api/map/', map_data, name='map_data'),
    path('api/nearby/', nearby_sites, name='nearby_sites'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)