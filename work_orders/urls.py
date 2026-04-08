from django.urls import path
from . import views

urlpatterns = [
    path('', views.work_order_list, name='work_order_list'),
    path('create/', views.work_order_create, name='work_order_create'),  # DODAJ TO
    path('<uuid:pk>/', views.work_order_detail, name='work_order_detail'),
    path('<uuid:pk>/add-product/', views.add_product_item, name='add_product_item'),
    path('<uuid:pk>/add-service/', views.add_service_item, name='add_service_item'),
    path('remove-product/<int:item_id>/', views.remove_product_item, name='remove_product_item'),
    path('complete/<uuid:pk>/', views.work_order_complete, name='work_order_complete'),
    path('<uuid:pk>/picker/products/', views.get_product_picker, name='get_product_picker'),
    path('<uuid:pk>/picker/services/', views.get_service_picker, name='get_service_picker'),
    path('<uuid:pk>/add-multiple-products/', views.add_multiple_products, name='add_multiple_products'),
    path('<uuid:pk>/add-multiple-services/', views.add_multiple_services, name='add_multiple_services'),
    path('remove-service/<int:item_id>/', views.remove_service_item, name='remove_service_item'),
    path('delete/<uuid:pk>/', views.work_order_delete, name='work_order_delete'),
]