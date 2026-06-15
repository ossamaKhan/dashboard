from django.urls import path
from . import views

# Mounted at /api/export/ in main urls.py
# Routes:
#   /api/export/channel/excel/   → source=channel, type=excel
#   /api/export/channel/pdf/     → source=channel, type=pdf
#   /api/export/marketing/excel/ → source=marketing, type=excel
#   /api/export/marketing/pdf/   → source=marketing, type=pdf
#   /api/export/excel/           → fallback (uses Referer header)
#   /api/export/pdf/             → fallback (uses Referer header)
urlpatterns = [
    path('<str:source>/<str:export_type>/', views.export_view, name='export_sourced'),
    path('<str:export_type>/',             views.export_view_legacy, name='export_legacy'),
]