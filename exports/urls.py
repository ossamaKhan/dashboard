from django.urls import path
from . import views

urlpatterns = [
    path('excel/', views.export_excel, name='export_excel'),
    path('pdf/',   views.export_pdf,   name='export_pdf'),
]