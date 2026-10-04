from django.db import models
import uuid

class ImportJob(models.Model):
    """Śledzenie postępu i statusu masowego importu danych."""
    STATUS_CHOICES = [
        ('PENDING', 'Oczekuje'),
        ('PROCESSING', 'Przetwarzanie'),
        ('COMPLETED', 'Zakończono'),
        ('FAILED', 'Błąd'),
    ]
    
    FILE_TYPE_CHOICES = [
        ('PRODUCTS', 'Produkty'),
        ('SUPPLIERS', 'Dostawcy'),
        ('PRICES', 'Cenniki/Powiązania'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='import_jobs')
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    file_name = models.CharField(max_length=255)
    records_total = models.IntegerField(default=0)
    records_imported = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    
    error_log = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Zadanie importu"
        verbose_name_plural = "Zadania importu"

    def __str__(self):
        return f"{self.file_type} - {self.file_name} ({self.status})"
