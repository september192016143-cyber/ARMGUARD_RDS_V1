from django.urls import path
from . import views

app_name = 'print_handler'

urlpatterns = [
    # Personnel ID Card Print Manager (new default)
    path('', views.print_id_cards, name='index'),
    path('id-cards/', views.print_id_cards, name='print_id_cards'),
    path('id-cards/regenerate/<str:personnel_id>/', views.regenerate_id_card, name='regenerate_id_card'),
    path('id-cards/generate-missing/', views.generate_missing_cards, name='generate_missing_cards'),
    path('id-cards/print/', views.print_id_cards_view, name='print_id_cards_view'),
    path('id-cards/image/<str:personnel_id>/<str:side>/', views.serve_id_card_image, name='serve_id_card_image'),
    path('id-cards/diagnostics/', views.id_card_diagnostics, name='id_card_diagnostics'),

    # Item Tag Printer
    path('item-tags/', views.print_item_tags, name='print_item_tags'),
    path('item-tags/image/<str:item_id>/', views.serve_item_tag_image, name='serve_item_tag_image'),
    path('item-tags/generate/', views.generate_item_tags, name='generate_item_tags'),
    path('item-tags/regenerate/<str:item_id>/', views.regenerate_item_tag, name='regenerate_item_tag'),
    path('item-tags/delete/<str:item_id>/', views.delete_item_tag, name='delete_item_tag'),
    path('item-tags/print/', views.print_item_tags_view, name='print_item_tags_view'),

    # Transaction printing
    path('transaction/<int:transaction_id>/', views.print_transaction_form, name='print_transaction_form'),
    path('transaction/<int:transaction_id>/pdf/', views.download_transaction_pdf, name='download_transaction_pdf'),
    path('transaction/<int:transaction_id>/print/', views.print_transaction_pdf, name='print_transaction_pdf'),
    path('transactions/', views.print_transactions, name='print_transactions'),

    # TR Reprint
    path('reprint-tr/', views.reprint_tr, name='reprint_tr'),
]
