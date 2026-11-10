from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Commitment(BaseModel):
    class State(models.TextChoices):
        JOINED = 'JOINED', 'Registrado'
        PENDING = 'PENDING', 'Pendiente'
        IN_PROGRESS = 'IN_PROGRESS', 'En proceso'
        DONE = 'DONE', 'Realizado'

    origin = models.CharField(max_length=100)
    applic_name = models.CharField(max_length=70)
    territory = models.CharField(max_length=60)
    commitment_date = models.DateField()
    support = models.CharField(max_length=200, blank=True)
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.JOINED,
    )
    observation = models.TextField(blank=True)

    functionary = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT,
        related_name='commitments',
    )

    measuring = models.ForeignKey(
        'configuration.Measuring',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='commitments',
    )

    class Meta:
        ordering = ['commitment_date']
        indexes = [models.Index(fields=['state', 'commitment_date'])]

    @property
    def is_overdue(self):
        return self.state != self.State.DONE and self.commitment_date < timezone.localdate()

    def clean(self):
        super().clean()
        # Es una promesa a futuro: al crearla, la fecha no puede estar en el pasado.
        if self._state.adding and self.commitment_date and self.commitment_date < timezone.localdate():
            raise ValidationError(
                {'commitment_date': 'La fecha del compromiso no puede estar en el pasado.'}
            )

    def __str__(self):
        return f"{self.applic_name} – {self.get_state_display()}"