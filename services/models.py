import uuid
from django.db import models
from decimal import Decimal


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='services')

    name = models.CharField(max_length=255, verbose_name="Nazwa usługi")
    net_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena netto")
    # Zwykłe pole do wpisania liczby
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=23.00, verbose_name="Stawka VAT %")
    gross_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena brutto")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if self.net_price is not None:
            # Obliczamy: netto * (1 + vat/100)
            vat_factor = Decimal(1) + (self.vat_rate / Decimal(100))
            self.gross_price = (self.net_price * vat_factor).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.vat_rate}%)"