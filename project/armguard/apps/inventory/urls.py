from django.urls import path
from . import views

urlpatterns = [
    # ── Pistol ──────────────────────────────────────────────────────────────
    path('pistols/', views.PistolListView.as_view(), name='pistol-list'),
    path('pistols/add/', views.PistolCreateView.as_view(), name='pistol-add'),
    path('pistols/<str:pk>/edit/', views.PistolUpdateView.as_view(), name='pistol-edit'),
    path('pistols/<str:pk>/delete/', views.PistolDeleteView.as_view(), name='pistol-delete'),

    # ── Rifle ────────────────────────────────────────────────────────────────
    path('rifles/', views.RifleListView.as_view(), name='rifle-list'),
    path('rifles/add/', views.RifleCreateView.as_view(), name='rifle-add'),
    path('rifles/<str:pk>/edit/', views.RifleUpdateView.as_view(), name='rifle-edit'),
    path('rifles/<str:pk>/delete/', views.RifleDeleteView.as_view(), name='rifle-delete'),

    # ── Magazine ─────────────────────────────────────────────────────────────
    path('magazines/', views.MagazineListView.as_view(), name='magazine-list'),
    path('magazines/add/', views.MagazineCreateView.as_view(), name='magazine-add'),
    path('magazines/<int:pk>/edit/', views.MagazineUpdateView.as_view(), name='magazine-edit'),
    path('magazines/<int:pk>/delete/', views.MagazineDeleteView.as_view(), name='magazine-delete'),

    # ── Ammunition ───────────────────────────────────────────────────────────
    path('ammunition/', views.AmmunitionListView.as_view(), name='ammunition-list'),
    path('ammunition/add/', views.AmmunitionCreateView.as_view(), name='ammunition-add'),
    path('ammunition/<int:pk>/edit/', views.AmmunitionUpdateView.as_view(), name='ammunition-edit'),
    path('ammunition/<int:pk>/delete/', views.AmmunitionDeleteView.as_view(), name='ammunition-delete'),
    path('ammunition/stock.json', views.ammunition_stock_json, name='ammunition-stock-json'),

    # ── Accessory ────────────────────────────────────────────────────────────
    path('accessories/', views.AccessoryListView.as_view(), name='accessory-list'),
    path('accessories/add/', views.AccessoryCreateView.as_view(), name='accessory-add'),
    path('accessories/<int:pk>/edit/', views.AccessoryUpdateView.as_view(), name='accessory-edit'),
    path('accessories/<int:pk>/delete/', views.AccessoryDeleteView.as_view(), name='accessory-delete'),
]
