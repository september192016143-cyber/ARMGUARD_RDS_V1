from django.urls import path
from . import views

app_name = 'camera'

urlpatterns = [
    # ── Phone-facing ──────────────────────────────────────────────────────────
    path('',                              views.camera_upload_page,    name='upload_page'),
    path('upload/',                       views.upload_image,           name='upload_image'),
    path('activate/<str:token>/',         views.activate_device_view,   name='activate_device'),
    path('no-device/',                    views.no_device_view,         name='no_device'),

    # ── Admin (System Administrator only) ─────────────────────────────────────
    path('admin/devices/',                views.device_list_view,       name='device_list'),
    path('admin/pair/<int:user_pk>/',     views.pair_device_view,       name='pair_device'),
    path('admin/revoke/<int:device_pk>/', views.revoke_device_view,     name='revoke_device'),
]
