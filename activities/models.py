import uuid

from django.db.models import OuterRef, Subquery
from django.db import models

from core.models import BaseModel


class Activity(BaseModel):
    STATE_CHOICES = [
        ('PENDING', 'Pendiente'),
        ('VALIDATED', 'Validado'),
        ('REJECTED', 'Rechazado'),
    ]
    date = models.DateField()
    submission_token = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )
    application = models.CharField(max_length=100)
    taken_action = models.TextField()
    name_contact = models.CharField(max_length=70)
    telephone_contact = models.CharField(max_length=20)
    state_validity = models.CharField(max_length=20, choices=STATE_CHOICES, default='PENDING')
    functionary = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT
    )
    measuring = models.ForeignKey(
        'configuration.Measuring',
        on_delete=models.PROTECT
    )
    commitment = models.ForeignKey(
        'agenda.Commitment',
        on_delete=models.PROTECT,
        related_name='activities',
        null=True,
        blank=True  # Commitment es opcional
    )

    quantity = models.PositiveIntegerField(
        default=1, 
        verbose_name="Cantidad / Personas atendidas",
        help_text="Número de atenciones o ejecuciones realizadas en este registro"
    )

    enters_pipe = models.BooleanField(
    default=False,
    verbose_name="¿Ingresa al Tubo de Trabajo?",
    help_text="Marcar si esta actividad genera un compromiso futuro con el vecino"
    )
    def __str__(self):
        return f"{self.date} – {self.application}"


class Evidence(BaseModel):
    class Validity(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    name = models.CharField(max_length=50)
    author = models.CharField(max_length=50)
    date_evidence = models.DateField()
    metadata = models.CharField(max_length=500)
    validity_state = models.CharField(
        max_length=20,
        choices=Validity.choices,
        default=Validity.PENDING,
    )
    date_validity = models.DateField(null=True, blank=True)
    observations_validity = models.TextField(blank=True)
    file = models.FileField(upload_to='evidences/%Y/%m/')
    verificator = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='evidences_verified',
    )
    #Se borra la actividad, Se borra la evidencia
    activity = models.ForeignKey(
        'activities.Activity',
        on_delete=models.CASCADE,
        related_name='evidences'
    )
    functionary = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT,
        related_name='evidences_uploaded',
    )

    def __str__(self):
        return self.name


def approved_activity_queryset(queryset=None):
    activities = queryset if queryset is not None else Activity.objects.all()
    latest_evidence = Evidence.objects.filter(
        activity_id=OuterRef('pk'),
    ).order_by('-created_at', '-pk')
    return activities.annotate(
        latest_evidence_state=Subquery(
            latest_evidence.values('validity_state')[:1],
        ),
    ).filter(
        latest_evidence_state=Evidence.Validity.APPROVED,
        state_validity='VALIDATED',
    )