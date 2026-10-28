from django.urls import path
from . import views

urlpatterns = [
    # --- LISTA I GŁÓWNE ---
    path('', views.product_list, name="product_list"),
    path('home/', views.home_redirect, name="home_redirect"),
    path('logs/', views.activity_log_list, name='activity_log_list'),

    # --- CRUD PRODUKTU ---
    path('create/', views.product_create, name='product_create'),
    path('edit/<uuid:pk>/', views.product_edit, name='product_edit'),
    path('delete/<uuid:pk>/', views.product_delete, name='product_delete'),
    path('bulk-delete/', views.product_bulk_delete, name='product_bulk_delete'),

    # --- AKCJE POMOCNICZE ---
    path('toggle_favourite/<uuid:pk>/', views.toggle_favourite, name='toggle_favourite'),
    path('batch/update/<int:batch_id>/', views.quick_update_batch_stock, name='quick_update_batch_stock'),

    # --- ZAMÓWIENIA (INDYWIDUALNE) ---
    path('add-to-order-modal/<uuid:pk>/', views.add_to_order_modal, name='add_to_order_modal'),
    path('add-to-order-save/<uuid:pk>/', views.add_to_order_save, name='add_to_order_save'),

    path('add-supplier-row/', views.add_supplier_row, name='add_supplier_row'),
    path('add-batch-row/', views.add_batch_row, name='add_batch_row'),

    # --- MAGAZYNY (LOCATIONS) ---
    path('locations/', views.location_list, name='location_list'),
    path('locations/create/', views.location_create, name='location_create'),
    path('locations/edit/<uuid:pk>/', views.location_edit, name='location_edit'),
    path('locations/delete/<uuid:pk>/', views.location_delete, name='location_delete'),

    # --- INWENTARYZACJA (STOCKTAKES) ---
    path('stocktakes/', views.stocktake_list, name='stocktake_list'),
    path('stocktakes/create/', views.stocktake_create, name='stocktake_create'),
    path('stocktakes/<uuid:pk>/', views.stocktake_detail, name='stocktake_detail'),
    path('stocktakes/item/<uuid:item_id>/update/', views.stocktake_item_update, name='stocktake_item_update'),
    path('stocktakes/<uuid:pk>/complete/', views.stocktake_complete, name='stocktake_complete'),
    path('stocktakes/<uuid:pk>/cancel/', views.stocktake_cancel, name='stocktake_cancel'),
]