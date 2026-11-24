from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from .validators import normalize_chilean_rut, validate_event_image


class DelegationPerson(BaseModel):
    delegation = models.ForeignKey(
        'personal.Delegation',
        on_delete=models.PROTECT,
        related_name='community_people',
        verbose_name='Delegación',
    )
    full_name = models.CharField(max_length=150, verbose_name='Nombre completo')
    rut = models.CharField(max_length=12, verbose_name='RUT')
    email = models.EmailField(verbose_name='Correo electrónico')
    phone = models.CharField(max_length=30, verbose_name='Teléfono')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delegation_people_created',
        verbose_name='Registrado por',
    )

    class Meta:
        ordering = ['full_name', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['delegation', 'rut'],
                name='unique_person_rut_per_delegation',
            ),
        ]
        indexes = [
            models.Index(
                fields=['delegation', 'is_active', 'rut'],
                name='person_del_active_rut_idx',
            ),
        ]
        verbose_name = 'Persona de la comunidad'
        verbose_name_plural = 'Padrón de personas'

    def clean(self):
        super().clean()
        try:
            self.rut = normalize_chilean_rut(self.rut)
        except ValidationError as error:
            raise ValidationError({'rut': error.messages}) from error

    def __str__(self):
        return f'{self.full_name} · {self.delegation.name}'


class CommunityEvent(BaseModel):
    class EventType(models.TextChoices):
        REGISTRATION = 'REGISTRATION', 'Requiere inscripción'
        INFORMATION = 'INFORMATION', 'Solo informativo'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        PUBLISHED = 'PUBLISHED', 'Publicado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    delegation = models.ForeignKey(
        'personal.Delegation',
        on_delete=models.PROTECT,
        related_name='community_events',
        verbose_name='Delegación',
    )
    title = models.CharField(max_length=150, verbose_name='Nombre del evento')
    event_type = models.CharField(
        max_length=12,
        choices=EventType.choices,
        default=EventType.REGISTRATION,
        verbose_name='Tipo de evento',
    )
    description = models.TextField(verbose_name='Descripción')
    what_to_expect = models.TextField(
        blank=True,
        verbose_name='Qué habrá',
        help_text='Describe actividades, servicios, horarios u otros detalles.',
    )
    starts_at = models.DateTimeField(verbose_name='Fecha y hora de inicio')
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha y hora de término',
    )
    location = models.CharField(max_length=200, verbose_name='Lugar')
    image = models.ImageField(
        upload_to='event_images/%Y/%m/',
        blank=True,
        validators=[validate_event_image],
        verbose_name='Imagen de portada',
        help_text='JPG, PNG o WebP; máximo 5 MiB y 20 megapíxeles.',
    )
    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Cupos disponibles',
        help_text='Solo aplica si el evento requiere inscripción.',
    )
    registration_deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Cierre de inscripciones',
        help_text='Solo aplica si el evento requiere inscripción.',
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Estado',
    )

    class Meta:
        ordering = ['starts_at', 'pk']
        indexes = [
            models.Index(
                fields=['delegation', 'status', 'starts_at'],
                name='event_del_state_start_idx',
            ),
        ]
        verbose_name = 'Evento comunitario'
        verbose_name_plural = 'Eventos comunitarios'

    def clean(self):
        super().clean()
        if self.pk and self.organization_invitations.exclude(organization__delegation_id=self.delegation_id).exists():
            raise ValidationError({'delegation': 'La delegación no puede cambiar mientras haya organizaciones convocadas de otra delegación.'})
        if self.pk and self.starts_at and self.starts_at > timezone.now() and self.organization_invitations.filter(status='PARTICIPATED').exists():
            raise ValidationError({'starts_at': 'El evento tiene participaciones registradas; no puede trasladarse al futuro.'})
        if self.capacity is not None and self.capacity < 1:
            raise ValidationError({
                'capacity': 'Los cupos deben ser al menos uno.'
            })
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError({
                'ends_at': 'El término debe ser posterior al inicio.'
            })
        if (
            self.registration_deadline
            and self.starts_at
            and self.registration_deadline > self.starts_at
        ):
            raise ValidationError({
                'registration_deadline': (
                    'El cierre de inscripciones debe ser anterior al evento.'
                )
            })

    @property
    def requires_registration(self):
        return self.event_type == self.EventType.REGISTRATION

    @property
    def is_open_for_registration(self):
        now = timezone.now()
        return (
            self.requires_registration
            and self.status == self.Status.PUBLISHED
            and self.starts_at > now
            and (
                self.registration_deadline is None
                or self.registration_deadline >= now
            )
        )

    def __str__(self):
        return f'{self.title} · {self.starts_at:%d-%m-%Y}'


class EventRegistration(BaseModel):
    class Status(models.TextChoices):
        PENDING_EMAIL = 'PENDING_EMAIL', 'Pendiente de correo'
        PENDING_REVIEW = 'PENDING_REVIEW', 'Pendiente de revisión'
        CONFIRMED = 'CONFIRMED', 'Confirmada'
        REJECTED = 'REJECTED', 'Rechazada'
        CANCELLED = 'CANCELLED', 'Cancelada'

    event = models.ForeignKey(
        CommunityEvent,
        on_delete=models.PROTECT,
        related_name='registrations',
        verbose_name='Evento',
    )
    full_name = models.CharField(max_length=150, verbose_name='Nombre completo')
    rut = models.CharField(max_length=12, verbose_name='RUT')
    email = models.EmailField(verbose_name='Correo electrónico')
    phone = models.CharField(max_length=30, verbose_name='Teléfono')
    adult_attends = models.BooleanField(
        default=True,
        verbose_name='El adulto también asistirá',
    )
    guardian_person = models.ForeignKey(
        DelegationPerson,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='child_event_registrations',
        verbose_name='Tutor del padrón',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_EMAIL,
        verbose_name='Estado',
    )
    email_verification_token_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name='Hash del token de verificación',
    )
    email_verification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Correo de verificación enviado',
    )
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Correo verificado',
    )
    consented_at = models.DateTimeField(verbose_name='Consentimiento otorgado')

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'rut'],
                name='unique_event_registration_rut',
            ),
        ]
        indexes = [
            models.Index(
                fields=['event', 'status'],
                name='registration_event_status_idx',
            ),
        ]
        verbose_name = 'Inscripción a evento'
        verbose_name_plural = 'Inscripciones a eventos'

    def clean(self):
        super().clean()
        try:
            self.rut = normalize_chilean_rut(self.rut)
        except ValidationError as error:
            raise ValidationError({'rut': error.messages}) from error
        if (
            self.guardian_person_id
            and self.event_id
            and self.guardian_person.delegation_id != self.event.delegation_id
        ):
            raise ValidationError({
                'guardian_person': (
                    'El tutor debe estar registrado en la delegación del evento.'
                )
            })

    @property
    def attendee_count(self):
        return int(self.adult_attends) + self.children.count()

    @property
    def verification_expired(self):
        return (
            self.email_verification_sent_at is None
            or self.email_verification_sent_at
            < timezone.now() - timedelta(hours=24)
        )

    def __str__(self):
        return f'{self.full_name} · {self.event.title}'


class RegistrationChild(BaseModel):
    registration = models.ForeignKey(
        EventRegistration,
        on_delete=models.CASCADE,
        related_name='children',
        verbose_name='Inscripción',
    )
    full_name = models.CharField(max_length=150, verbose_name='Nombre completo')

    class Meta:
        ordering = ['full_name', 'pk']
        verbose_name = 'Menor inscrito'
        verbose_name_plural = 'Menores inscritos'

    def __str__(self):
        return self.full_name


class EventOrganization(BaseModel):
    class Status(models.TextChoices):
        INVITED = 'INVITED', 'Invitada'
        CONFIRMED = 'CONFIRMED', 'Asistencia confirmada'
        PARTICIPATED = 'PARTICIPATED', 'Participó'
        DECLINED = 'DECLINED', 'No participará'

    event = models.ForeignKey(CommunityEvent, on_delete=models.PROTECT, related_name='organization_invitations')
    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='event_invitations')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INVITED, verbose_name='Participación')
    observations = models.TextField(blank=True, verbose_name='Observaciones (opcional)')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['event', 'organization'], name='unique_event_organization')]
        verbose_name = 'Convocatoria a organización'
        verbose_name_plural = 'Convocatorias a organizaciones'

    def clean(self):
        super().clean()
        if self.event_id and self.organization_id and self.event.delegation_id != self.organization.delegation_id:
            raise ValidationError('El evento y la organización deben pertenecer a la misma delegación.')
        if self.status == self.Status.PARTICIPATED and self.event_id and self.event.starts_at > timezone.now():
            raise ValidationError({'status': 'La participación se registra desde la fecha de inicio del evento.'})
