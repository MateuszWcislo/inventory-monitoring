from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name="product_list"),
    path('create/', views.product_create, name='product_create'),

    path('quick_update/<uuid:pk>/', views.quick_update_stock, name='product_quick_update'),
    path('edit/<uuid:pk>/', views.product_edit, name='product_edit'),
    path('delete/<uuid:pk>/', views.product_delete, name='product_delete'),

    path('logs/', views.activity_logs, name='activity_logs'),
]