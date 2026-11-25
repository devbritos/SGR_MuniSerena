import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from core.models import BaseModel


class Organization(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activa'
        FORMING = 'FORMING', 'En formación'
        INACTIVE = 'INACTIVE', 'Inactiva'

    delegation = models.ForeignKey('personal.Delegation', on_delete=models.PROTECT, related_name='organizations', verbose_name='Delegación')
    name = models.CharField(max_length=150, verbose_name='Nombre de la organización')
    rut = models.CharField(max_length=12, null=True, blank=True, verbose_name='RUT (opcional)')
    registry_number = models.CharField(max_length=60, blank=True, verbose_name='Número de registro (opcional)')
    organization_type = models.CharField(max_length=100, blank=True, verbose_name='Tipo de organización (opcional)')
    territory = models.CharField(max_length=150, blank=True, verbose_name='Sector o territorio (opcional)')
    address = models.CharField(max_length=200, blank=True, verbose_name='Dirección (opcional)')
    phone = models.CharField(max_length=30, blank=True, verbose_name='Teléfono (opcional)')
    email = models.EmailField(blank=True, verbose_name='Correo electrónico (opcional)')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE, verbose_name='Estado')
    observations = models.TextField(blank=True, verbose_name='Observaciones (opcional)')
    created_by = models.ForeignKey('personal.Functionary', on_delete=models.PROTECT, related_name='organizations_registered')

    class Meta:
        ordering = ['name', 'pk']
        verbose_name = 'Organización comunitaria'
        verbose_name_plural = 'Organizaciones comunitarias'
        constraints = [models.UniqueConstraint(fields=['delegation', 'rut'], name='unique_org_rut_delegation')]

    def __str__(self):
        return self.name


class OrganizationLeader(BaseModel):
    class BoardPosition(models.TextChoices):
        PRESIDENT = 'PRESIDENT', 'Presidente'
        SECRETARY = 'SECRETARY', 'Secretario'
        TREASURER = 'TREASURER', 'Tesorero'

    member = models.OneToOneField('NeighborhoodMember', on_delete=models.PROTECT, null=True, blank=True, related_name='leadership')
    board_position = models.CharField(max_length=12, choices=BoardPosition.choices, null=True, blank=True, verbose_name='Cargo de la directiva')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='leaders')
    name = models.CharField(max_length=150, verbose_name='Nombre del dirigente')
    position = models.CharField(max_length=100, verbose_name='Cargo en la organización')
    phone = models.CharField(max_length=30, blank=True, verbose_name='Teléfono (opcional)')
    email = models.EmailField(blank=True, verbose_name='Correo electrónico (opcional)')
    starts_on = models.DateField(null=True, blank=True, verbose_name='Inicio del período (opcional)')
    ends_on = models.DateField(null=True, blank=True, verbose_name='Término del período (opcional)')
    is_active = models.BooleanField(default=True, verbose_name='Dirigente en funciones')
    observations = models.TextField(blank=True, verbose_name='Observaciones (opcional)')

    class Meta:
        ordering = ['-is_active', 'name', 'pk']
        verbose_name = 'Dirigente'
        constraints = [models.UniqueConstraint(fields=['organization', 'board_position'], name='unique_board_position_per_org')]

    def clean(self):
        super().clean()
        if self.member_id and self.member.organization_id != self.organization_id:
            raise ValidationError({'member': 'El vecino debe pertenecer a esta junta.'})
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({'ends_on': 'El término no puede ser anterior al inicio.'})

    @property
    def validity_label(self):
        today = timezone.localdate()
        if not self.is_active:
            return 'Fuera de funciones'
        if self.starts_on and self.starts_on > today:
            return 'Período por iniciar'
        if self.ends_on and self.ends_on < today:
            return 'Período vencido'
        if not self.ends_on:
            return 'Sin término registrado'
        return 'Período vigente'

    def __str__(self):
        return f'{self.name} · {self.position}'


class NeighborhoodMember(BaseModel):
    submission_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='neighbors')
    user = models.OneToOneField('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='neighborhood_member')
    role = models.ForeignKey('personal.Role', on_delete=models.PROTECT, related_name='neighborhood_members')
    names = models.CharField(max_length=75, verbose_name='Nombres')
    lastnames = models.CharField(max_length=100, verbose_name='Apellidos')
    email = models.EmailField(blank=True, verbose_name='Correo electrónico')
    phone = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    is_active = models.BooleanField(default=True, verbose_name='Integrante activo')

    class Meta:
        ordering = ['lastnames', 'names', 'pk']
        verbose_name = 'Vecino de la junta'
        permissions = [('manage_board', 'Administrar integrantes y directiva de la propia junta')]

    @property
    def full_name(self):
        return f'{self.names} {self.lastnames}'.strip()

    @property
    def portal_active(self):
        return bool(self.is_active and not self.deleted_at and self.role.is_active and not self.role.deleted_at
                    and self.role.role_name in ('NEIGHBORHOOD_MEMBER', 'NEIGHBORHOOD_ADMIN')
                    and self.organization.status != Organization.Status.INACTIVE and not self.organization.deleted_at
                    and self.organization.delegation.state == 'ACTIVO' and not self.organization.delegation.deleted_at)

    @property
    def is_manager(self):
        return self.portal_active and self.role.role_name == 'NEIGHBORHOOD_ADMIN'

    @property
    def board_title(self):
        leader = getattr(self, 'leadership', None)
        today = timezone.localdate()
        if (leader and leader.board_position and leader.is_active and not leader.deleted_at
                and (not leader.starts_on or leader.starts_on <= today)
                and (not leader.ends_on or leader.ends_on >= today)):
            return leader.get_board_position_display()
        return ''

    @property
    def can_send_letters(self):
        return self.portal_active and bool(self.user_id and self.board_title)

    def __str__(self):
        return f'{self.full_name} · {self.organization.name}'
