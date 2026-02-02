from django.contrib.auth.models import AbstractUser
from django.db import models
from tenants.models import Tenant


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrator'
        STAFF = 'STAFF', 'Pracownik'

    # Pola username, first_name, last_name są już w AbstractUser.
    # Nadpisujemy email, aby był unikatowy w skali całego systemu.
    email = models.EmailField(unique=True, verbose_name="Adres e-mail")

    # Nasze powiązanie z firmą (tenantem)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True
    )

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STAFF,
        verbose_name="Rola"
    )

    # Opcjonalnie: ustawiamy, że to email ma być głównym identyfikatorem (zamiast loginu)
    # Jeśli wolisz tradycyjny login (username), zostaw tak jak jest.

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"

    def is_tenant_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser