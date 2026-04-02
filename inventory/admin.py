from django.contrib import admin
from .models import Product, ProductBatch, ProductSupplier


class ProductBatchInline(admin.TabularInline):
    model = ProductBatch
    extra = 1  # Ile pustych wierszy na nowe partie pokazać domyślnie
    fields = ('current_stock', 'net_price', 'gross_price', 'created_at')
    readonly_fields = ('created_at',)
    # Możemy dodać przeliczanie w JS w przyszłości,
    # na razie model sam przeliczy ceny po kliknięciu "Save"


class ProductSupplierInline(admin.TabularInline):
    model = ProductSupplier
    extra = 1
    fields = ('supplier', 'supplier_sku')


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
        """
        Nadpisujemy zapisywanie inline'ów, by wymusić tenant_id.
        """
        # 1. Pobieramy instancje, ale jeszcze ich nie zapisujemy w bazie (commit=False)
        instances = formset.save(commit=False)

        # 2. Obsługa nowych i zmienionych rekordów
        for instance in instances:
            # Wymuszamy tenanta z zalogowanego użytkownika
            instance.tenant = request.user.tenant

            # Wymuszamy przypisanie do produktu (rodzica), jeśli to inline
            if hasattr(instance, 'product') and not instance.product_id:
                instance.product = form.instance

            instance.save()

        # 3. Obsługa usuwania rekordów (jeśli zaznaczono "Delete")
        for obj in formset.deleted_objects:
            obj.delete()

        # 4. Zapisujemy relacje ManyToMany, jeśli istnieją
        formset.save_m2m()


# Rejestrujemy też pozostałe modele, żeby mieć do nich wgląd osobno
@admin.register(ProductBatch)
class ProductBatchAdmin(admin.ModelAdmin):
    list_display = ('product', 'current_stock', 'net_price', 'gross_price', 'tenant')
    list_filter = ('tenant', 'product')


@admin.register(ProductSupplier)
class ProductSupplierAdmin(admin.ModelAdmin):
    list_display = ('product', 'supplier', 'supplier_sku', 'tenant')