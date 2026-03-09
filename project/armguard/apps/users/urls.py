from django.urls import path
from . import views

urlpatterns = [
    path('',               views.UserListView.as_view(),   name='user-list'),
    path('add/',           views.UserCreateView.as_view(), name='user-add'),
    path('<int:pk>/edit/', views.UserUpdateView.as_view(), name='user-edit'),
    path('<int:pk>/delete/', views.UserDeleteView.as_view(), name='user-delete'),
]
