from django.core.exceptions import ValidationError
from django.db import models
from core.models import BaseModel


class Period(BaseModel):
    start_date = models.DateField()
    end_date = models.DateField()
    computable_days = models.IntegerField()
    status = models.BooleanField(default=True)
    version_parameter = models.CharField(max_length=10)
    minimum_threshold = models.IntegerField()
    maximum_computable_days = models.IntegerField()
    semaphore = models.CharField(max_length=10)

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "La fecha de término no puede ser anterior a la de inicio."}
            )

    def __str__(self):
        return f"{self.start_date} – {self.end_date}"

    @property
    def quarter_label(self):
        from calendar import monthrange
        from datetime import date
        quarter = (self.start_date.month - 1) // 3 + 1
        start = date(self.start_date.year, (quarter - 1) * 3 + 1, 1)
        end_month = quarter * 3
        end = date(start.year, end_month, monthrange(start.year, end_month)[1])
        return f'{quarter}.º trimestre de {start.year}' if self.start_date == start and self.end_date == end else ''


class Measuring(BaseModel):
    class Calculation(models.TextChoices):
        ACTIVITIES = 'ACTIVITIES', 'Cantidad de actividades validadas'
        COMMITMENTS_DONE = 'COMMITMENTS_DONE', 'Porcentaje de compromisos cumplidos'
        COMMITMENTS_PENDING = 'COMMITMENTS_PENDING', 'Porcentaje de compromisos pendientes'

    calculation_method = models.CharField(
        max_length=24, choices=Calculation.choices, default=Calculation.ACTIVITIES,
        verbose_name='Cómo se obtiene el avance',
    )
    code = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Código',
    )
    service = models.CharField(max_length=100, verbose_name='Nombre')
    measurable_item = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Descripción',
    )
    validity = models.BooleanField(default=True, verbose_name='Activo')

    @property
    def is_commitment_percentage(self):
        return self.calculation_method in (self.Calculation.COMMITMENTS_DONE, self.Calculation.COMMITMENTS_PENDING)

    class Meta:
        verbose_name = 'Ítem de medición'
        verbose_name_plural = 'Ítems de medición'

    def __str__(self):
        return f"{self.service} – {self.measurable_item}"


from decimal import Decimal

class Goal(BaseModel):
    #meta
    target_value = models.DecimalField(max_digits=10, decimal_places=2)
    #ponderator
    weight = models.DecimalField(max_digits=5, decimal_places=2)
    unity = models.CharField(max_length=50)
    validity = models.BooleanField(default=True)

    position = models.ForeignKey('personal.Position', on_delete=models.PROTECT, related_name='goals')
    period = models.ForeignKey('Period', on_delete=models.PROTECT, related_name='goals')
    measuring = models.ForeignKey('Measuring', on_delete=models.PROTECT, related_name='goals')
    group_id = models.UUIDField(null=True, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'
        constraints = [
            models.UniqueConstraint(
                fields=['position', 'measuring', 'period'],
                name='unique_goal_per_position_measuring_period',
            )
        ]

    def clean(self):
        super().clean()
        if self.position_id and self.period_id:
            otras_metas = Goal.objects.filter(
                position=self.position,
                period=self.period,
                deleted_at__isnull=True,
            ).exclude(pk=self.pk)
            if self.group_id:
                otras_metas = otras_metas.exclude(group_id=self.group_id)
            suma_actual = sum(g.weight for g in otras_metas) + (self.weight or Decimal('0'))
            if suma_actual > Decimal('100'):
                raise ValidationError(
                    {'weight': f'La suma de ponderadores para este cargo y período supera 100% (actual: {suma_actual}%).'}
                )

    def __str__(self):
        return f"{self.position} · {self.measuring} · {self.period}"
