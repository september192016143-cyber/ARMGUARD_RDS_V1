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
    # Personnel group management
    path('settings/groups/add/',             views.group_add,               name='group-add'),
    path('settings/groups/<int:pk>/rename/', views.group_rename,            name='group-rename'),
    path('settings/groups/<int:pk>/delete/', views.group_delete,            name='group-delete'),
    # Personnel squadron management
    path('settings/squadrons/add/',             views.squadron_add,            name='squadron-add'),
    path('settings/squadrons/<int:pk>/rename/', views.squadron_rename,         name='squadron-rename'),
    path('settings/squadrons/<int:pk>/delete/', views.squadron_delete,         name='squadron-delete'),
    path('settings/truncate/',       views.truncate_data,                    name='settings-truncate'),
    path('settings/simulate-orex/',   views.simulate_orex_run,               name='settings-simulate-orex'),
    path('storage/',       views.storage_status_json,                       name='storage-status'),
    path('storage/cleanup-orphans/', views.cleanup_orphaned_personnel_media, name='storage-cleanup-orphans'),
    path('ping/',          views.session_ping,                              name='session-ping'),
]
