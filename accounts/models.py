from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    """
    Custom user model.

    Future-proof:
    - supports SaaS
    - supports mobile + offline sync
    - allows extension without migrations nightmare
    """

    # Exemplo de campo que pode vir a ser útil
    timezone = models.CharField(max_length=50, default="Europe/Lisbon")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.username