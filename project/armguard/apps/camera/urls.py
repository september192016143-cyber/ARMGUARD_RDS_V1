from django.urls import path
from . import views

app_name = 'camera'

urlpatterns = [
    # ── Phone-facing ──────────────────────────────────────────────────────────
    path('',                              views.camera_upload_page,    name='upload_page'),
    path('upload/',                       views.upload_image,           name='upload_image'),
    path('activate/<str:token>/',         views.activate_device_view,   name='activate_device'),
    path('no-device/',                    views.no_device_view,         name='no_device'),
    path('api/key/',                      views.key_refresh_api,        name='key_refresh'),
    path('api/pin/',                      views.pin_api,                name='pin_api'),
    path('api/task/',                     views.camera_task_api,        name='task_api'),

    # ── Admin (System Administrator only) ─────────────────────────────────────
    path('admin/devices/',                views.device_list_view,       name='device_list'),
    path('my-device/',                    views.my_device_view,         name='my_device'),
    path('admin/pair/<int:user_pk>/',     views.pair_device_view,       name='pair_device'),
    path('admin/pair/<int:user_pk>/status/', views.device_status_api,   name='device_status'),
    path('admin/pair/<int:user_pk>/pin/', views.pair_pin_api,           name='pair_pin'),
    path('admin/feed/devices/',           views.devices_feed_api,       name='devices_feed'),
    path('admin/feed/logs/',              views.logs_feed_api,          name='logs_feed'),
    path('admin/revoke/<int:device_pk>/', views.revoke_device_view,     name='revoke_device'),
    path('upload/<int:log_pk>/delete-image/', views.delete_upload_image, name='delete_upload_image'),
]
