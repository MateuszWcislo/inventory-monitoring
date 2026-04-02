from django.urls import path
from . import views

urlpatterns = [
    # --- LISTA I GŁÓWNE ---
    path('', views.product_list, name="product_list"),
    path('home/', views.home_redirect, name="home_redirect"),

    # --- CRUD PRODUKTU ---
    path('create/', views.product_create, name='product_create'),
    path('edit/<uuid:pk>/', views.product_edit, name='product_edit'),
    path('delete/<uuid:pk>/', views.product_delete, name='product_delete'),  # DODANE
    path('bulk-delete/', views.product_bulk_delete, name='product_bulk_delete'),

    # --- AKCJE POMOCNICZE ---
    path('toggle_favourite/<uuid:pk>/', views.toggle_favourite, name='toggle_favourite'),
    path('batch/update/<int:batch_id>/', views.quick_update_batch_stock, name='quick_update_batch_stock'),

    # --- ZAMÓWIENIA (INDYWIDUALNE) ---
    # Usunięto duplikat add_to_order_modal
    path('add-to-order-modal/<uuid:pk>/', views.add_to_order_modal, name='add_to_order_modal'),
    path('add-to-order-save/<uuid:pk>/', views.add_to_order_save, name='add_to_order_save'),

    # --- ZAMÓWIENIA (ZBIORCZE) ---
    path('bulk-add-to-order/', views.bulk_add_to_order_modal, name='bulk_add_to_order_modal'),
    path('bulk-add-to-order/save/', views.bulk_add_to_order_save, name='bulk_add_to_order_save'),

    path('add-supplier-row/', views.add_supplier_row, name='add_supplier_row'),
    path('add-batch-row/', views.add_batch_row, name='add_batch_row'),
]