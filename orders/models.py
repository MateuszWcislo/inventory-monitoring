from django.db import models
from django.utils import timezone
import uuid
from suppliers.models import Supplier
from inventory.models import Product

class Order(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'Otwarte'),
        ('CLOSED', 'Zamknięte'),
        ('CANCELLED', 'Anulowane'),
    ]

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='orders')
    # Numeracja lokalna dla każdej firmy osobno
    number = models.PositiveIntegerField(editable=False)

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)

    class Meta:
        ordering = ['-status', '-number']
        # Unikalność numeru w obrębie firmy
        unique_together = ('tenant', 'number')

    def save(self, *args, **kwargs):
        # 1. Automatyczne nadawanie lokalnego numeru zamówienia
        if not self.number:
            max_num = Order.objects.filter(tenant=self.tenant).aggregate(models.Max('number'))['number__max']
            self.number = (max_num or 0) + 1

        # 2. Logika daty zakończenia
        if self.status in ['CLOSED', 'CANCELLED'] and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status == 'OPEN':
            self.completed_at = None

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Zamówienie #{self.id} ({self.supplier.name})"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"