from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name="product_list"),
    path('create/', views.product_create, name='product_create'),

    path('quick_update/<uuid:pk>/', views.quick_update_stock, name='product_quick_update'),
    path('edit/<uuid:pk>/', views.product_edit, name='product_edit'),
    path('delete/<uuid:pk>/', views.product_delete, name='product_delete'),
    path('toggle_favourite/<uuid:pk>/', views.toggle_favourite, name='toggle_favourite'),
    path('add_to_order_modal/<uuid:pk>/', views.add_to_order_modal, name='add_to_order_modal'),
    path('add_to_order_save/<uuid:pk>/', views.add_to_order_save, name='add_to_order_save'),

    path('bulk-add-to-order/', views.bulk_add_to_order_modal, name='bulk_add_to_order_modal'),
    path('bulk-add-to-order/save/', views.bulk_add_to_order_save, name='bulk_add_to_order_save'),

    path('logs/', views.activity_logs, name='activity_logs'),
]