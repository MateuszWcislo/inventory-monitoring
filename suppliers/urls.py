from django.urls import path
from . import views

urlpatterns = [
    path('', views.supplier_list, name="supplier_list"),
    path('create/', views.supplier_create, name='supplier_create'),
    path('edit/<uuid:pk>/', views.supplier_edit, name='supplier_edit'),
    path('delete/<uuid:pk>/', views.supplier_delete, name='supplier_delete'),
]