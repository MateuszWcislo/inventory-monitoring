from django.db import models
import uuid
from suppliers.models import Supplier
from django.conf import settings

class Product(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name="Nazwa produktu", null=False, blank=False)
    sku = models.CharField(max_length=50, unique=True, verbose_name="Kod SKU", null=True, blank=True)
    description = models.TextField(blank=True, verbose_name="Opis", null=True)
    current_stock = models.IntegerField(default=0, verbose_name="Aktualny stan", null=True)
    min_threshold = models.IntegerField(default=5, verbose_name="Próg alarmowy", null=True)
    is_favourite = models.BooleanField(default=False, verbose_name="Ulubiony", null=True)

    # Wielu dostawców (Many-to-Many)
    suppliers = models.ManyToManyField(
        Supplier,
        related_name='products',
        blank=True,
        verbose_name="Dostawcy"
    )

    created = models.DateTimeField(auto_now_add=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True,
                          primary_key=True, editable=False)

    def __str__(self):
        return f"{self.name} ({self.sku})"

    class Meta:
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"


class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ('CREATE', 'Utworzenie'),
        ('UPDATE', 'Edycja'),
        ('DELETE', 'Usunięcie'),
        ('STOCK_ADJ', 'Zmiana stanu'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255) # Przechowujemy nazwę, nawet jeśli produkt zostanie usunięty
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    previous_stock = models.IntegerField(default=None,verbose_name="Poprzedni stan", null=True)
    current_stock = models.IntegerField(default=None,verbose_name="Aktualny stan", null=True)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']