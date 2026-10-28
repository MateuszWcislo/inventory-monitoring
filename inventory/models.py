import uuid
from django.db import models
from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP
from suppliers.models import Supplier

class Location(models.Model):
    """Magazyn / lokalizacja fizyczna dla tenanta."""
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(max_length=150, verbose_name="Nazwa magazynu")
    code = models.CharField(max_length=50, blank=True, null=True, verbose_name="Kod magazynu")
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name="Adres")
    is_default = models.BooleanField(default=False, verbose_name="Domyślny magazyn")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Magazyn"
        verbose_name_plural = "Magazyny"
        unique_together = ('tenant', 'name')
        ordering = ['-is_default', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            Location.objects.filter(tenant=self.tenant, is_default=True).exclude(pk=self.pk).update(is_default=False)
        elif not Location.objects.filter(tenant=self.tenant).exclude(pk=self.pk).exists():
            self.is_default = True
        super().save(*args, **kwargs)

    @classmethod
    def get_default_location(cls, tenant):
        """Zwraca lub tworzy domyślny magazyn dla danego tenanta."""
        loc = cls.objects.filter(tenant=tenant, is_default=True).first()
        if not loc:
            loc = cls.objects.filter(tenant=tenant).first()
        if not loc:
            loc = cls.objects.create(
                tenant=tenant,
                name="Główny",
                code="MAG-01",
                is_default=True
            )
        return loc

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
        """Stan fizyczny + to, co jest już zamówione/utworzone. Wyklucza anulowane."""
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
        # Używamy prefetchowanych batches jeśli są dostępne, żeby uniknąć N+1
        if hasattr(self, '_prefetched_objects_cache') and 'batches' in self._prefetched_objects_cache:
            return sorted(
                [b for b in self.batches.all() if (b.current_stock or 0) > 0],
                key=lambda x: x.created_at
            )
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
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='batches', null=True, blank=True, verbose_name="Magazyn")
    current_stock = models.PositiveIntegerField(verbose_name="Ilość",default=0,
                                                null=True, blank=True)
    net_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                    null=True, blank=True, verbose_name="Cena netto")
    gross_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                      null=True, blank=True, verbose_name="Cena brutto")
    created_at = models.DateTimeField(auto_now_add=True)

    processed_orders = models.ManyToManyField('orders.Order', blank=True)

    def save(self, *args, **kwargs):
        if not self.location and self.tenant:
            self.location = Location.get_default_location(self.tenant)

        # Logika przeliczania cen w obie strony
        vat_rate_dec = Decimal(str(self.product.vat_rate)) if self.product and self.product.vat_rate is not None else Decimal('23.00')
        vat_mult = 1 + (vat_rate_dec / Decimal('100'))

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


class Stocktake(models.Model):
    """Arkusz / Sesja Inwentaryzacji."""
    STATUS_CHOICES = [
        ('DRAFT', 'W trakcie'),
        ('COMPLETED', 'Zatwierdzona'),
        ('CANCELLED', 'Anulowana'),
    ]

    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='stocktakes')
    title = models.CharField(max_length=200, verbose_name="Tytuł / Numer inwentaryzacji")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='stocktakes', verbose_name="Magazyn", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Status")
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Utworzył")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data utworzenia")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Data zatwierdzenia")
    notes = models.TextField(blank=True, null=True, verbose_name="Uwagi")

    class Meta:
        verbose_name = "Inwentaryzacja"
        verbose_name_plural = "Inwentaryzacje"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class StocktakeItem(models.Model):
    """Pozycja inwentaryzacji dla danego produktu / partii."""
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)
    stocktake = models.ForeignKey(Stocktake, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stocktake_items', verbose_name="Produkt")
    batch = models.ForeignKey(ProductBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='stocktake_items', verbose_name="Partia")
    system_quantity = models.IntegerField(default=0, verbose_name="Stan systemowy")
    counted_quantity = models.IntegerField(default=0, verbose_name="Stan faktyczny")
    notes = models.CharField(max_length=255, blank=True, null=True, verbose_name="Komentarz do różnicy")

    @property
    def difference(self):
        return (self.counted_quantity or 0) - (self.system_quantity or 0)

    class Meta:
        verbose_name = "Pozycja inwentaryzacji"
        verbose_name_plural = "Pozycje inwentaryzacji"
        unique_together = ('stocktake', 'product', 'batch')


class ProductSupplier(models.Model):
    """Mapowanie: u którego dostawcy produkt ma jaki kod SKU."""
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='supplier_mappings')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE,related_name='product_mappings')
    supplier_sku = models.CharField(max_length=100, null=True, blank=True,
                                    verbose_name="SKU u dostawcy")

    class Meta:
        unique_together = ('tenant', 'product', 'supplier')


class ActivityLog(models.Model):
    """Śledzenie zmian w stanach magazynowych i innych istotnych zdarzeń."""
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='activity_logs')
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='activity_logs', null=True, blank=True)
    product_batch = models.ForeignKey(ProductBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    
    action = models.CharField(max_length=50)  # np. STOCK_UPDATE, BATCH_CREATED, MANUAL_ADJUSTMENT
    description = models.TextField()
    
    old_value = models.CharField(max_length=255, null=True, blank=True)
    new_value = models.CharField(max_length=255, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Log aktywności"
        verbose_name_plural = "Logi aktywności"
