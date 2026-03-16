from django.urls import path
from .views import dashboard_view, dashboard_cards_json, dashboard_tables_json

urlpatterns = [
    path('', dashboard_view, name='dashboard'),
    path('cards-json/', dashboard_cards_json, name='dashboard-cards-json'),
    path('tables-json/', dashboard_tables_json, name='dashboard-tables-json'),
]