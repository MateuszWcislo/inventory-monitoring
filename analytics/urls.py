from django.urls import path
from . import views

urlpatterns = [
    path('', views.analytics_dashboard, name='analytics_dashboard'),
    path('restock-report/', views.restock_cost_report, name='restock_cost_report'),
    path('export/stock/csv/', views.export_stock_csv, name='export_stock_csv'),
    path('export/stock/excel/', views.export_stock_excel, name='export_stock_excel'),
    path('export/restock/csv/', views.export_restock_csv, name='export_restock_csv'),
    path('export/restock/excel/', views.export_restock_excel, name='export_restock_excel'),
    path('export/consumption/csv/', views.export_consumption_csv, name='export_consumption_csv'),
    path('export/consumption/excel/', views.export_consumption_excel, name='export_consumption_excel'),
    path('export/orders/csv/', views.export_orders_csv, name='export_orders_csv'),
    path('export/orders/excel/', views.export_orders_excel, name='export_orders_excel'),
]
