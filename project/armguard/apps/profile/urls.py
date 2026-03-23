"""
Profile app URL configuration.
"""
from django.urls import path
from . import views

app_name = 'profile'

urlpatterns = [
    path('', views.profile_view, name='view'),
    path('edit/', views.profile_edit, name='edit'),
    path('password/', views.password_change, name='password_change'),
]
