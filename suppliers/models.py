import uuid
from django.db import models


class Supplier(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='suppliers')

    # Dane firmy
    name = models.CharField(max_length=255, verbose_name="Nazwa dostawcy")
    nip = models.CharField(max_length=15, blank=True, null=True, verbose_name="NIP")
    address = models.TextField(blank=True, null=True, verbose_name="Adres")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Telefon główny")
    website = models.CharField(max_length=255, blank=True, null=True, verbose_name="Strona WWW")

    # Dane kontaktowe (Osoba)
    representative = models.CharField(max_length=255, blank=True, null=True, verbose_name="Opiekun / Osoba kontaktowa")
    email = models.EmailField(blank=True, null=True, verbose_name="E-mail do zamówień")

    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.representative:
            return f"{self.name} (Opiekun: {self.representative})"
        return self.name

    class Meta:
        verbose_name = "Dostawca"
        verbose_name_plural = "Dostawcy"
        unique_together = ('tenant', 'name')