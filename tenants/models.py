from django.db import models

class Tenant(models.Model):
    name = models.CharField(max_length=255, verbose_name="Nazwa firmy")
    subdomain = models.SlugField(unique=True, help_text="Unikalny identyfikator w URL")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name