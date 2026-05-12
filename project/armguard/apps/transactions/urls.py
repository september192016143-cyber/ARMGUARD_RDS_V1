from django.urls import path
from . import views

urlpatterns = [
    path('', views.TransactionListView.as_view(), name='transaction-list'),
    path('new/', views.create_transaction, name='transaction-create'),
    path('new/tr-preview/', views.tr_preview, name='transaction-tr-preview'),
    path('api/personnel-status/', views.personnel_status, name='transaction-personnel-status'),
    path('api/personnel-search/', views.personnel_search, name='transaction-personnel-search'),
    path('api/item-status/', views.item_status_check, name='transaction-item-status'),
    path('api/overdue-tr/', views.overdue_tr_check, name='transaction-overdue-tr'),
    path('api/purpose-config/', views.purpose_config_json, name='transaction-purpose-config'),
    path('<int:transaction_id>/', views.TransactionDetailView.as_view(), name='transaction-detail'),
]
