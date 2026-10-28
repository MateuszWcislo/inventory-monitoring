from django.contrib import admin
from .models import Product, ProductBatch, ProductSupplier, ActivityLog, Location, Stocktake, StocktakeItem


class ProductBatchInline(admin.TabularInline):
    model = ProductBatch
    extra = 1  # Ile pustych wierszy na nowe partie pokazać domyślnie
    fields = ('location', 'current_stock', 'net_price', 'gross_price', 'created_at')
    readonly_fields = ('created_at',)


class ProductSupplierInline(admin.TabularInline):
    model = ProductSupplier
    extra = 1
    fields = ('supplier', 'supplier_sku')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'address', 'is_default', 'tenant', 'created_at')
    list_filter = ('tenant', 'is_default')
    search_fields = ('name', 'code', 'address')


class StocktakeItemInline(admin.TabularInline):
    model = StocktakeItem
    extra = 0
    fields = ('product', 'batch', 'system_quantity', 'counted_quantity', 'notes')


@admin.register(Stocktake)
class StocktakeAdmin(admin.ModelAdmin):
    list_display = ('title', 'location', 'status', 'created_by', 'created_at', 'completed_at', 'tenant')
    list_filter = ('tenant', 'status', 'location')
    search_fields = ('title', 'notes')
    inlines = [StocktakeItemInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('local_id', 'name', 'total_stock', 'min_threshold', 'vat_rate', 'is_favourite')
    list_display_links = ('local_id', 'name')
    search_fields = ('name', 'supplier_mappings__supplier_sku')
    list_filter = ('is_favourite', 'vat_rate')
    inlines = [ProductSupplierInline, ProductBatchInline]

    def save_model(self, request, obj, form, change):
        if not obj.tenant:
            obj.tenant = request.user.tenant
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.tenant = request.user.tenant
            if hasattr(instance, 'product') and not instance.product_id:
                instance.product = form.instance
            instance.save()

        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()


@admin.register(ProductBatch)
class ProductBatchAdmin(admin.ModelAdmin):
    list_display = ('product', 'location', 'current_stock', 'net_price', 'gross_price', 'tenant')
    list_filter = ('tenant', 'location', 'product')


@admin.register(ProductSupplier)
class ProductSupplierAdmin(admin.ModelAdmin):
    list_display = ('product', 'supplier', 'supplier_sku', 'tenant')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'product', 'user', 'created_at', 'tenant')
    list_filter = ('tenant', 'action')