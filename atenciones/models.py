from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class AttentionType(BaseModel):
    code = models.CharField(max_length=30, unique=True, verbose_name='Código')
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        ordering = ['name']
        verbose_name = 'Tipo de atención'
        verbose_name_plural = 'Tipos de atención'

    def __str__(self):
        return f'{self.code} - {self.name}'


class SubAttention(BaseModel):
    code = models.CharField(max_length=30, unique=True, verbose_name='Código')
    name = models.CharField(max_length=100, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name='sub_attentions',
        verbose_name='Tipo de atención',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        ordering = ['attention_type__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['attention_type', 'name'],
                name='unique_subattention_name_per_type',
            )
        ]
        verbose_name = 'Subatención'
        verbose_name_plural = 'Subatenciones'

    def __str__(self):
        return f'{self.attention_type.name} - {self.name}'


class Attention(BaseModel):
    class Status(models.TextChoices):
        UNCLASSIFIED = 'UNCLASSIFIED', 'Sin clasificar'
        PENDING = 'PENDING', 'Pendiente'
        IN_PROGRESS = 'IN_PROGRESS', 'En gestión'
        CLOSED = 'CLOSED', 'Cerrada'

    class Outcome(models.TextChoices):
        RESOLVED = 'RESOLVED', 'Solicitud resuelta'
        GUIDANCE = 'GUIDANCE', 'Orientación entregada'
        REFERRED = 'REFERRED', 'Derivación informada'
        OTHER = 'OTHER', 'Otro resultado'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    followup_responsible = models.ForeignKey(
        'personal.Functionary', on_delete=models.PROTECT, null=True, blank=True,
        related_name='assigned_attentions', verbose_name='Responsable del seguimiento',
    )
    next_action = models.CharField(max_length=250, blank=True, verbose_name='Próxima acción')
    next_contact_date = models.DateField(null=True, blank=True, verbose_name='Fecha de próxima acción')
    closure_outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True, verbose_name='Resultado del cierre')
    closure_details = models.TextField(blank=True, verbose_name='Detalle del cierre')
    closed_at = models.DateTimeField(null=True, blank=True)

    requester_name = models.CharField(
        max_length=150,
        verbose_name='Nombre del solicitante',
    )
    requester_contact = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Contacto del solicitante',
    )
    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Tipo de atención',
    )
    sub_attention = models.ForeignKey(
        SubAttention,
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Subatención',
    )
    description = models.TextField(verbose_name='Descripción de la atención')
    delegation = models.ForeignKey(
        'personal.Delegation',
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Delegación',
    )
    functionary = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Usuario responsable',
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='attentions',
        verbose_name='Organización comunitaria',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'next_contact_date'], name='attention_status_next_idx')]
        verbose_name = 'Atención ciudadana'
        verbose_name_plural = 'Atenciones ciudadanas'

    def clean(self):
        super().clean()
        if (
            self.organization_id
            and self.delegation_id
            and self.organization.delegation_id != self.delegation_id
        ):
            raise ValidationError({
                'organization': 'La organización comunitaria debe pertenecer a la delegación de la atención.'
            })
        if self.followup_responsible_id and self.delegation_id and self.followup_responsible.delegation_id != self.delegation_id:
            raise ValidationError({'followup_responsible': 'El responsable debe pertenecer a la delegación de la atención.'})
        if self.status == self.Status.CLOSED and (not self.closure_outcome or not self.closure_details.strip() or not self.closed_at):
            raise ValidationError('Para cerrar la atención debes indicar el resultado, el detalle y la fecha de cierre.')
        if (
            self.sub_attention_id
            and self.attention_type_id
            and self.sub_attention.attention_type_id != self.attention_type_id
        ):
            raise ValidationError({
                'sub_attention': (
                    'La subatención debe pertenecer al tipo de atención seleccionado.'
                )
            })
        if (
            self.functionary_id
            and self.delegation_id
            and self.functionary.delegation_id != self.delegation_id
        ):
            author = self.functionary
            user = author.user
            if not (author.has_global_scope or (user and (user.is_staff or user.is_superuser))):
                raise ValidationError({
                    'delegation': 'La delegación debe coincidir con la del funcionario.'
                })

    def __str__(self):
        return f'{self.requester_name} - {self.attention_type.name}'

    @property
    def is_overdue(self):
        return bool(self.status != self.Status.CLOSED and self.next_contact_date and self.next_contact_date < timezone.localdate())


class AttentionFollowUp(models.Model):
    attention = models.ForeignKey(Attention, on_delete=models.PROTECT, related_name='followups')
    author = models.ForeignKey('personal.Functionary', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(verbose_name='Gestión realizada')
    status = models.CharField(max_length=20, choices=Attention.Status.choices)
    responsible = models.ForeignKey('personal.Functionary', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    next_action = models.CharField(max_length=250, blank=True)
    next_contact_date = models.DateField(null=True, blank=True)
    closure_outcome = models.CharField(max_length=20, choices=Attention.Outcome.choices, blank=True)
    closure_details = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Seguimiento de atención'
        verbose_name_plural = 'Seguimientos de atenciones'
