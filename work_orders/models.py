import uuid
from django.db import models
from decimal import Decimal


class WorkOrder(models.Model):
    STATUS_CHOICES = [
        ('IN_PROGRESS', 'W trakcie'),
        ('COMPLETED', 'Zakończone'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)

    name = models.CharField(max_length=255, verbose_name="Nazwa zlecenia")
    description = models.TextField(blank=True, verbose_name="Opis")
    client = models.CharField(max_length=255, verbose_name="Klient")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS', verbose_name="Status")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def total_net(self):
        p_net = sum(item.total_price_net for item in self.items.all())
        s_net = sum(item.price_net for item in self.services.all())
        return p_net + s_net

    @property
    def total_gross(self):
        p_gross = sum(item.total_price_gross for item in self.items.all())
        s_gross = sum(item.price_gross for item in self.services.all())
        return p_gross + s_gross

    @property
    def total_vat(self):
        """Zwraca łączną kwotę VAT dla całego zlecenia"""
        return self.total_gross - self.total_net


class WorkOrderProduct(models.Model):
    order = models.ForeignKey(WorkOrder, related_name='items', on_delete=models.CASCADE)
    product_batch = models.ForeignKey('inventory.ProductBatch', on_delete=models.SET_NULL, null=True)

    # SNAPSHOTY danych:
    name_snapshot = models.CharField(max_length=255)  # Nazwa produktu w momencie zakupu
    unit_price_net = models.DecimalField(max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)
    quantity = models.PositiveIntegerField()

    @property
    def total_price_net(self):
        return self.unit_price_net * self.quantity

    @property
    def total_price_gross(self):
        factor = 1 + (self.vat_rate / Decimal(100))
        return (self.total_price_net * factor).quantize(Decimal('0.01'))


class WorkOrderService(models.Model):
    order = models.ForeignKey(WorkOrder, related_name='services', on_delete=models.CASCADE)
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True)

    # SNAPSHOTY danych:
    quantity = models.PositiveIntegerField(default=1)
    name_snapshot = models.CharField(max_length=255)
    price_net = models.DecimalField(max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)

    @property
    def total_price_net(self):
        return self.price_net * self.quantity

    @property
    def price_gross(self):
        factor = 1 + (self.vat_rate / Decimal(100))
        return (self.price_net * factor).quantize(Decimal('0.01'))