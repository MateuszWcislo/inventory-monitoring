import uuid
from django.db import models, transaction
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
    # Automatyczny numer zamówienia w ramach firmy (Tenanta)
    order_number = models.PositiveIntegerField(editable=False, null=True)

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='orders')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='orders')

    # --- SNAPSHOTY (Historia - zachowanie danych nawet po usunięciu produktu) ---
    product_name_snapshot = models.CharField("Nazwa produktu", max_length=255, blank=True)
    supplier_sku_snapshot = models.CharField("SKU u dostawcy", max_length=100, blank=True)
    representative_snapshot = models.CharField("Opiekun u dostawcy", max_length=255, blank=True, null=True)

    # --- DANE FINANSOWE I ILOŚCIOWE ---
    quantity = models.PositiveIntegerField("Ilość", default=1)
    net_price = models.DecimalField("Cena netto", max_digits=10, decimal_places=2, default=0)
    gross_price = models.DecimalField("Cena brutto", max_digits=10, decimal_places=2, null=True, blank=True)

    order_type = models.CharField(max_length=10, choices=ORDER_TYPES, default='MANUAL')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='CREATED')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding  # Sprawdza czy to pierwsze zapisanie do bazy

        # 1. Przeliczanie Brutto/Netto (zawsze gdy brakuje jednego z nich)
        if self.product:
            vat_rate = getattr(self.product, 'vat_rate', Decimal('23.00'))
            vat_factor = 1 + (vat_rate / Decimal('100'))

            if self.net_price and not self.gross_price:
                self.gross_price = (self.net_price * vat_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            elif self.gross_price and not self.net_price:
                self.net_price = (self.gross_price / vat_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 2. Logika dla NOWYCH rekordów
        if is_new:
            # A. Nadawanie numeru zamówienia (licznik w ramach Tenanta)
            last_order = Order.objects.filter(tenant=self.tenant).order_by('-order_number').first()
            self.order_number = (last_order.order_number + 1) if last_order and last_order.order_number else 1

            # B. Snapshoty danych produktu
            if self.product:
                if not self.product_name_snapshot:
                    self.product_name_snapshot = self.product.name

                # Snapshot SKU dostawcy
                if self.supplier:
                    mapping = ProductSupplier.objects.filter(
                        product=self.product,
                        supplier=self.supplier
                    ).first()
                    if mapping:
                        self.supplier_sku_snapshot = mapping.supplier_sku

                # C. Wyliczenie ilości dla zamówień AUTO
                # (Jeśli quantity nie zostało podane wcześniej przez metodę check_auto_order)
                if self.order_type == 'AUTO' and self.quantity <= 1:
                    current_total = self.product.total_stock
                    limit = self.product.min_threshold
                    self.quantity = max(1, limit - current_total)

            # D. Snapshot opiekuna
            if self.supplier and self.supplier.representative:
                self.representative_snapshot = self.supplier.representative

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Zamówienie"
        verbose_name_plural = "Zamówienia"
        # Sortowanie będzie realizowane w widoku przez status_group,
        # ale tutaj ustawiamy domyślne po dacie.
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.order_number} - {self.product_name_snapshot}"