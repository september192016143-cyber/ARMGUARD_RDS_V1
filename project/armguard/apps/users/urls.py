from django.urls import path
from . import views

urlpatterns = [
    path('',               views.UserListView.as_view(),                    name='user-list'),
    path('add/',           views.UserCreateView.as_view(),                  name='user-add'),
    path('<int:pk>/edit/', views.UserUpdateView.as_view(),                  name='user-edit'),
    path('<int:pk>/delete/', views.UserDeleteView.as_view(),                name='user-delete'),
    path('<int:pk>/revoke-2fa/', views.UserRevoke2FAView.as_view(),         name='user-revoke-2fa'),
    path('<int:pk>/toggle-2fa/', views.UserToggle2FAView.as_view(),         name='user-toggle-2fa'),
    path('settings/',      views.SystemSettingsView.as_view(),              name='system-settings'),
    path('storage/',       views.storage_status_json,                       name='storage-status'),
    path('storage/cleanup-orphans/', views.cleanup_orphaned_personnel_media, name='storage-cleanup-orphans'),
]
