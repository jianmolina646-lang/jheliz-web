from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        SELLER = "seller", "Vendedor"
        VIEWER = "viewer", "Solo lectura"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VIEWER)

    @property
    def can_manage_inventory(self) -> bool:
        return self.is_superuser or self.role in {self.Role.ADMIN, self.Role.SELLER}
