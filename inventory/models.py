from django.db import models
import uuid
from suppliers.models import Supplier
from django.conf import settings

class Product(models.Model):
    # FK do Tenanta - podstawa izolacji
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='products')
    # Lokalne ID dla Tenanta (np. 1, 2, 3...)
    number = models.PositiveIntegerField(editable=False)

    name = models.CharField(max_length=200, verbose_name="Nazwa produktu", null=False, blank=False)
    sku = models.CharField(max_length=50, verbose_name="Kod SKU", null=True, blank=True)
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

    def save(self, *args, **kwargs):
        # Automatyczne nadawanie numeru wewnątrz Tenanta
        if not self.number:
            max_num = Product.objects.filter(tenant=self.tenant).aggregate(models.Max('number'))['number__max']
            self.number = (max_num or 0) + 1
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"
        # ZAPEWNIA UNIKALNOŚĆ NAZWY I SKU TYLKO W RAMACH JEDNEJ FIRMY
        unique_together = (('tenant', 'name'), ('tenant', 'sku'))


class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ('CREATE', 'Utworzenie'),
        ('UPDATE', 'Edycja'),
        ('DELETE', 'Usunięcie'),
        ('STOCK_ADJ', 'Zmiana stanu'),
    )

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    previous_stock = models.IntegerField(default=None,verbose_name="Poprzedni stan", null=True)
    current_stock = models.IntegerField(default=None,verbose_name="Aktualny stan", null=True)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']