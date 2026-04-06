import uuid
from django.db import models
from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP
from suppliers.models import Supplier

class Product(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='products')
    local_id = models.PositiveIntegerField(editable=False)  # Lokalny licznik

    name = models.CharField(max_length=200, verbose_name="Nazwa produktu")
    description = models.TextField(blank=True, null=True, verbose_name="Opis")
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=23.00, verbose_name="VAT %")
    min_threshold = models.IntegerField(default=5, verbose_name="Próg alarmowy (Limit)")
    target_stock = models.IntegerField(null=True, blank=True, verbose_name="Stan docelowy")
    is_favourite = models.BooleanField(default=False, verbose_name="Ulubiony")
    created = models.DateTimeField(auto_now_add=True)

    @property
    def total_stock(self):
        """Oblicza sumaryczny stan ze wszystkich partii."""
        return self.batches.aggregate(models.Sum('current_stock'))['current_stock__sum'] or 0

    def get_virtual_stock(self):
        """Stan fizyczny + to, co jest już zamówione/utworzone."""
        actual = self.total_stock
        # Zakładamy, że model Order ma pole 'product' (ForeignKey)
        pending = self.orders.filter(
            status__in=['CREATED', 'ORDERED']
        ).aggregate(Sum('quantity'))['quantity__sum'] or 0

        return actual + pending

    def save(self, *args, **kwargs):
        if not self.local_id:
            max_num = Product.objects.filter(tenant=self.tenant).aggregate(models.Max('local_id'))['local_id__max']
            self.local_id = (max_num or 0) + 1
        # Jeśli użytkownik nie podał target_stock, ustawiamy go na równi z min_threshold
        if self.target_stock is None:
            self.target_stock = self.min_threshold

        super().save(*args, **kwargs)

    def active_batches(self):
        """Zwraca partie z dodatnim stanem, od najstarszych (FIFO)."""
        return self.batches.filter(current_stock__gt=0).order_by('created_at')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"
        unique_together = ('tenant', 'name')


class ProductBatch(models.Model):
    """Tu trzymamy konkretne ilości w konkretnych cenach."""
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='batches')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    current_stock = models.PositiveIntegerField(verbose_name="Ilość",default=0,
                                                null=True, blank=True)
    net_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                    null=True, blank=True, verbose_name="Cena netto")
    gross_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                      null=True, blank=True, verbose_name="Cena brutto")
    created_at = models.DateTimeField(auto_now_add=True)

    processed_orders = models.ManyToManyField('orders.Order', blank=True)

    def save(self, *args, **kwargs):
        # Logika przeliczania cen w obie strony
        vat_mult = 1 + (self.product.vat_rate / Decimal('100'))

        # Podajemy tylko netto, to oblicz brutto
        if self.net_price and not self.gross_price:
            self.gross_price = (self.net_price * vat_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # Podajemy tylko brutto, to oblicz netto
        elif self.gross_price and not self.net_price:
            self.net_price = (self.gross_price / vat_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # Podajemy obie, to zweryfikuj
        elif self.net_price and self.gross_price:
            # Weryfikacja spójności - priorytet dla netto przy rozbieżnościach
            self.gross_price = (self.net_price * vat_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        super().save(*args, **kwargs)


class ProductSupplier(models.Model):
    """Mapowanie: u którego dostawcy produkt ma jaki kod SKU."""
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='supplier_mappings')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE,related_name='product_mappings')
    supplier_sku = models.CharField(max_length=100, null=True, blank=True,
                                    verbose_name="SKU u dostawcy")

    class Meta:
        unique_together = ('tenant', 'product', 'supplier')
