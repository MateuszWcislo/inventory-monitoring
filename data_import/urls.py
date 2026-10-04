from django.urls import path
from . import views

urlpatterns = [
    path('', views.import_dashboard, name='import_dashboard'),
    path('products/', views.import_products, name='import_products'),
    path('products/template/csv/', views.download_product_template_csv, name='download_product_template_csv'),
    path('products/template/excel/', views.download_product_template_excel, name='download_product_template_excel'),
]
