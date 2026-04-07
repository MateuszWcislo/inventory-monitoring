from django.urls import path
from . import views

urlpatterns = [
    path('', views.order_list, name="order_list"),
    path('create/', views.order_create, name='order_create'),
    path('edit/<uuid:pk>/', views.order_edit, name='order_edit'),
    path('delete/<uuid:pk>/', views.order_delete, name='order_delete'),
    path('get-options/', views.get_filtered_options, name='get_filtered_options'),
    path('status-update/<uuid:pk>/', views.order_status_update, name='order_status_update'),
    path('reorder/<uuid:pk>/', views.order_reorder, name='order_reorder'),
]