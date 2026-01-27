from django.db import models
from django.utils import timezone
from suppliers.models import Supplier
from inventory.models import Product

class Order(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'Otwarte'),
        ('CLOSED', 'Zamknięte'),
        ('CANCELLED', 'Anulowane'),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    id = models.AutoField(primary_key=True)

    class Meta:
        # Sortujemy malejąco po statusie (OPEN -> CLOSED -> CANCELLED)
        # a następnie malejąco po dacie utworzenia (najnowsze najpierw)
        ordering = ['-status', '-id']

    def save(self, *args, **kwargs):
        # 1. Sprawdzamy, czy status to CLOSED lub CANCELLED
        # 2. Sprawdzamy, czy completed_at nie zostało jeszcze ustawione
        if self.status in ['CLOSED', 'CANCELLED'] and not self.completed_at:
            self.completed_at = timezone.now()

        # 3. Jeśli status wróciłby na OPEN (o ile na to pozwalasz),
        #    można opcjonalnie czyścić tę datę:
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