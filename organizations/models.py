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

    def clean(self):
        super().clean()
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
