from django.contrib import admin
from .models import Product, ActivityLog

admin.site.register(ActivityLog)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # 1. Jakie kolumny widać w tabeli
    list_display = ('name', 'sku', 'current_stock', 'min_threshold')
    # 2. Klikalne linki (nie tylko nazwa)
    list_display_links = ('name', 'sku')
    # 3. Wyszukiwarka (szuka po nazwie i kodzie SKU)
    search_fields = ('name', 'sku')
    # 4. Filtry po prawej stronie (np. pokaż tylko te z niskim stanem)
    list_filter = ('current_stock',)
    # 5. Edycja stanu prosto z listy (bez wchodzenia w produkt!)
    list_editable = ('current_stock',)

