import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Commitment(BaseModel):
    source_attention = models.ForeignKey(
        'atenciones.Attention', on_delete=models.PROTECT, null=True, blank=True,
        related_name='commitments', verbose_name='Atención de origen',
    )
    submission_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    class State(models.TextChoices):
        JOINED = 'JOINED', 'Ingresado'
        PENDING = 'PENDING', 'Pendiente'
        IN_PROGRESS = 'IN_PROGRESS', 'En gestión'
        DONE = 'DONE', 'Cumplido'

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
        if self.source_attention_id and self.functionary_id and self.source_attention.delegation_id != self.functionary.delegation_id:
            raise ValidationError({'functionary': 'El responsable debe pertenecer a la delegación de la atención de origen.'})
        # Es una promesa a futuro: al crearla, la fecha no puede estar en el pasado.
        if self._state.adding and self.commitment_date and self.commitment_date < timezone.localdate():
            raise ValidationError(
                {'commitment_date': 'La fecha del compromiso no puede estar en el pasado.'}
            )

    def __str__(self):
        return f"{self.applic_name} – {self.get_state_display()}"


class Meeting(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Programada'
        HELD = 'HELD', 'Realizada'
        CANCELLED = 'CANCELLED', 'Cancelada'
    delegation = models.ForeignKey('personal.Delegation', on_delete=models.PROTECT)
    title = models.CharField(max_length=150, verbose_name='Tema de la reunión')
    starts_at = models.DateTimeField(verbose_name='Fecha y hora')
    location = models.CharField(max_length=200, verbose_name='Lugar o enlace')
    participants = models.ManyToManyField('personal.Functionary', blank=True, related_name='meetings', verbose_name='Funcionarios participantes')
    external_participants = models.TextField(blank=True, verbose_name='Otros participantes (opcional)')
    notes = models.TextField(blank=True, verbose_name='Temas tratados y conclusiones (opcional)')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SCHEDULED, verbose_name='Estado')
    created_by = models.ForeignKey('personal.Functionary', on_delete=models.PROTECT, related_name='meetings_registered')
    submission_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    class Meta:
        ordering = ['-starts_at', '-pk']
        verbose_name = 'Reunión'

    def clean(self):
        super().clean()
        if self.status == self.Status.HELD and self.starts_at and self.starts_at > timezone.now():
            raise ValidationError({'starts_at': 'Una reunión futura debe mantenerse como programada.'})


class MeetingAgreement(BaseModel):
    meeting = models.ForeignKey(Meeting, on_delete=models.PROTECT, related_name='agreements')
    description = models.TextField(verbose_name='¿Qué se acordó hacer?')
    responsible = models.ForeignKey('personal.Functionary', on_delete=models.PROTECT, related_name='meeting_agreements')
    due_date = models.DateField(verbose_name='Fecha acordada de cumplimiento')
    commitment = models.OneToOneField(Commitment, on_delete=models.PROTECT, blank=True, null=True, related_name='meeting_agreement')
    class Meta:
        ordering = ['due_date', 'pk']
        verbose_name = 'Acuerdo de reunión'
    def clean(self):
        super().clean()
        if self.meeting_id and self.responsible_id and self.meeting.delegation_id != self.responsible.delegation_id:
            raise ValidationError({'responsible': 'El responsable debe pertenecer a la delegación de la reunión.'})
        if self.commitment_id and self.commitment.functionary.delegation_id != self.meeting.delegation_id:
            raise ValidationError('El compromiso debe pertenecer a la delegación de la reunión.')
