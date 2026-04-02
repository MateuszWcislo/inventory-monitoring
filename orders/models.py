import uuid
from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from inventory.models import Product, ProductSupplier
from suppliers.models import Supplier


class Order(models.Model):
    ORDER_TYPES = (
        ('MANUAL', 'Ręczne'),
        ('AUTO', 'Automatyczne'),
    )

    STATUS_CHOICES = (
        ('CREATED', 'Utworzone'),
        ('ORDERED', 'Zamówione'),
        ('COMPLETED', 'Zakończone'),
        ('CANCELLED', 'Anulowane'),
    )

    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='orders')

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='orders')

    # --- SNAPSHOTY (Historia) ---
    product_name_snapshot = models.CharField("Nazwa produktu", max_length=255)
    supplier_sku_snapshot = models.CharField("SKU u dostawcy", max_length=100, blank=True)
    representative_snapshot = models.CharField("Opiekun u dostawcy", max_length=255, blank=True, null=True)

    # --- DANE FINANSOWE I ILOŚCIOWE ---
    quantity = models.PositiveIntegerField("Ilość")
    net_price = models.DecimalField("Cena netto", max_digits=10, decimal_places=2)
    gross_price = models.DecimalField("Cena brutto", max_digits=10, decimal_places=2, null=True, blank=True)

    order_type = models.CharField(max_length=10, choices=ORDER_TYPES, default='MANUAL')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='CREATED')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # 1. Przeliczanie Brutto/Netto przed zapisem (jeśli mamy produkt i stawki)
        if self.product:
            vat_factor = 1 + (self.product.vat_rate / Decimal('100'))
            if self.net_price and not self.gross_price:
                self.gross_price = (self.net_price * vat_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            elif self.gross_price and not self.net_price:
                self.net_price = (self.gross_price / vat_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 2. Logika tylko dla NOWYCH zamówień
        if not self.pk:
            if self.product:
                # Snapshot nazwy
                self.product_name_snapshot = self.product.name

                # Snapshot SKU dostawcy
                mapping = ProductSupplier.objects.filter(
                    product=self.product,
                    supplier=self.supplier
                ).first()
                if mapping:
                    self.supplier_sku_snapshot = mapping.supplier_sku

                # Wyliczenie ilości dla AUTO: Limit - Stan
                if self.order_type == 'AUTO':
                    current_total = self.product.total_stock
                    limit = self.product.min_threshold
                    self.quantity = max(0, limit - current_total)

            # Snapshot opiekuna
            if self.supplier and self.supplier.representative:
                self.representative_snapshot = self.supplier.representative

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Zamówienie"
        verbose_name_plural = "Zamówienia"
        ordering = ['-created_at']