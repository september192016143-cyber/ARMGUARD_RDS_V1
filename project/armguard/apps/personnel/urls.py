from django.urls import path
from .views import (
    PersonnelListView, PersonnelDetailView, PersonnelCreateView, PersonnelUpdateView,
    PersonnelDeleteView, PersonnelCardPreviewView
)

urlpatterns = [
    path('', PersonnelListView.as_view(), name='personnel-list'),
    path('create/', PersonnelCreateView.as_view(), name='personnel-create'),
    path('preview-card/', PersonnelCardPreviewView.as_view(), name='personnel-card-preview'),
    path('<str:pk>/', PersonnelDetailView.as_view(), name='personnel-detail'),
    path('<str:pk>/update/', PersonnelUpdateView.as_view(), name='personnel-update'),
    path('<str:pk>/delete/', PersonnelDeleteView.as_view(), name='personnel-delete'),
]
