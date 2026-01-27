from django.urls import path
from . import views

urlpatterns = [
    path('', views.order_list, name="order_list"),
    path('create/', views.order_create, name='order_create'),
    path('edit/<int:pk>/', views.order_edit, name='order_edit'),
    path('delete/<int:pk>/', views.order_delete, name='order_delete'),
    path('preview/<int:pk>/', views.order_preview, name='order_preview'),
    path('<int:pk>/copy/', views.order_copy, name='order_copy'),
    path('count/', views.order_count, name='order_count'),
    path('order_bulk_delete/', views.order_bulk_delete, name='order_bulk_delete'),
]