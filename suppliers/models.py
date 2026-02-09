from django.db import models
import uuid

class Supplier(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='suppliers')

    name = models.CharField("Nazwa dostawcy", max_length=255)
    nip = models.CharField("NIP", max_length=15, blank=True, null=True)
    address = models.TextField("Adres", blank=True, null=True)
    phone = models.CharField("Numer telefonu", max_length=20, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True,
                          primary_key=True, editable=False)


    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Dostawca"
        verbose_name_plural = "Dostawcy"
        unique_together = ('tenant', 'name')