from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class OfficeLetter(BaseModel):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, null=True, blank=True, related_name='submitted_letters', verbose_name='Junta remitente')
    submitted_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True, blank=True, related_name='neighborhood_letters')
    submission_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    public_response = models.TextField(blank=True, verbose_name='Respuesta visible para la junta de vecinos')
    attention = models.ForeignKey(
        'atenciones.Attention', on_delete=models.PROTECT, null=True, blank=True,
        related_name='office_letters', verbose_name='Atención vinculada',
    )
    class State(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'En proceso'
        APPROVED = 'APPROVED', 'Aprobada'
        FINALIZED = 'FINALIZED', 'Finalizada'
        NOT_APPLICABLE = 'NOT_APPLICABLE', 'No aplica'

    delegation = models.ForeignKey(
        'personal.Delegation',
        on_delete=models.PROTECT,
        related_name='office_letters',
        verbose_name='Delegación',
    )
    received_at = models.DateField(verbose_name='Fecha de ingreso')
    registry_number = models.CharField(
        max_length=40,
        blank=True,
        verbose_name='Número de registro',
    )
    recipient = models.CharField(max_length=100, verbose_name='Destinatario')
    sender = models.CharField(max_length=150, verbose_name='Remitente')
    contact_phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='Teléfono de contacto',
    )
    subject = models.TextField(verbose_name='Actividad o tema')
    activity_date = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Fecha de actividad',
        help_text='Admite fechas, rangos o referencias como “por confirmar”.',
    )
    responsible = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT,
        related_name='office_letters_to_follow',
        verbose_name='Encargado del seguimiento',
    )
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.IN_PROGRESS,
        verbose_name='Estado',
    )
    pronouncement = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Pronunciamiento',
    )
    referred_to = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Derivada a',
    )
    observation = models.TextField(blank=True, verbose_name='Observación')
    registered_by = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='office_letters_registered',
        verbose_name='Registrada por',
    )

    class Meta:
        ordering = ['-received_at', '-pk']
        indexes = [
            models.Index(
                fields=['delegation', 'state', 'received_at'],
                name='letter_del_state_date_idx',
            ),
        ]
        verbose_name = 'Carta de oficina de partes'
        verbose_name_plural = 'Cartas de oficina de partes'

    def clean(self):
        super().clean()
        if self.organization_id and self.delegation_id and self.organization.delegation_id != self.delegation_id:
            raise ValidationError({'organization': 'La carta debe dirigirse a la delegación de la junta.'})
        if self.attention_id and self.delegation_id and self.attention.delegation_id != self.delegation_id:
            raise ValidationError({'delegation': 'La carta y su atención vinculada deben pertenecer a la misma delegación.'})
        if (
            self.delegation_id
            and self.responsible_id
            and self.responsible.delegation_id != self.delegation_id
        ):
            raise ValidationError({
                'responsible': (
                    'El encargado del seguimiento debe pertenecer a la delegación.'
                )
            })
    def __str__(self):
        reference = f' N.º {self.registry_number}' if self.registry_number else ''
        return f'Carta{reference} · {self.sender}'
