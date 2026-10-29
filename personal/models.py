from django.contrib.auth.models import User
from django.db import models
from core.models import BaseModel
from .validators import validate_person_name


class Delegation(BaseModel):
    STATES_CHOICES = [('ACTIVO', 'Activo'), ('INACTIVO', 'Inactivo')]

    FIELD_CHOICES = [('RURAL', 'Rural'), ('URBANO', 'Urbano')]

    code = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Código',
    )
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')
    address = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Dirección',
    )
    commune = models.CharField(
        max_length=80,
        blank=True,
        verbose_name='Comuna',
    )
    state = models.CharField(
        max_length=15, choices=STATES_CHOICES, default='ACTIVO'
    )
    field = models.CharField(max_length=50, choices=FIELD_CHOICES)

    class Meta:
        verbose_name = 'Delegación'
        verbose_name_plural = 'Delegaciones'

    def __str__(self):
        return self.name


class Position(BaseModel):
    name = models.CharField(max_length=50)
    validity = models.BooleanField(default=True)
    default_role = models.ForeignKey(
        'Role',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Rol por defecto',
        help_text='Rol asignado automáticamente al seleccionar este cargo.',
    )

    class Meta:
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'

    def __str__(self):
        return self.name


class Role(BaseModel):
    # Nombres estandarizados según requerimientos SGR (RF-002)
    ADMIN = 'ADMIN'
    COORDINATOR = 'COORDINATOR'
    DELEGATE = 'DELEGATE'
    FUNCTIONARY = 'FUNCTIONARY'
    VERIFIER = 'VERIFIER'
    READONLY = 'READONLY'

    ROLE_CHOICES = [
        (ADMIN, 'Administrador'),
        (COORDINATOR, 'Coordinador del Sistema'),
        (DELEGATE, 'Delegado / Jefatura'),
        (FUNCTIONARY, 'Funcionario Operativo'),
        (VERIFIER, 'Verificador'),
        (READONLY, 'Usuario de Consulta'),
    ]

    role_name = models.CharField(
        max_length=30,
        unique=True,
        verbose_name='Nombre del rol',
    )
    description = models.TextField(blank=True, verbose_name='Descripción')
    AUTHORIZED_SCOPE_CHOICES = [
        ('DELEGATION', 'Delegación asignada'),
        ('GLOBAL', 'Todas las delegaciones'),
    ]
    authorized_scope = models.CharField(
        max_length=20,
        choices=AUTHORIZED_SCOPE_CHOICES,
        default='DELEGATION',
        verbose_name='Alcance autorizado',
    )
    permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='sgr_roles',
        verbose_name='Permisos',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.get_role_name_display()

    def get_role_name_display(self):
        standard_names = dict(self.ROLE_CHOICES)
        return standard_names.get(self.role_name, self.role_name)

    @property
    def badge_style(self):
        role_styles = {
            self.ADMIN: 'admin',
            'Administrador': 'admin',
            self.COORDINATOR: 'coordinator',
            'Coordinador': 'coordinator',
            'Coordinador del Sistema': 'coordinator',
            self.DELEGATE: 'delegate',
            'Delegado': 'delegate',
            'Delegado / Jefatura': 'delegate',
            self.FUNCTIONARY: 'functionary',
            'Funcionario': 'functionary',
            'Funcionario Operativo': 'functionary',
            self.VERIFIER: 'verifier',
            'Verificador': 'verifier',
            self.READONLY: 'readonly',
            'Usuario de Consulta': 'readonly',
        }
        return role_styles.get(self.role_name, 'custom')


class Functionary(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        related_name='functionary',
        null=True,
        blank=True,
    )
    delegation = models.ForeignKey(Delegation, on_delete=models.PROTECT)
    position = models.ForeignKey(Position, on_delete=models.PROTECT)
    names = models.CharField(max_length=50, validators=[validate_person_name])
    lastnames = models.CharField(max_length=50, validators=[validate_person_name])
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        verbose_name = 'Funcionario'
        verbose_name_plural = 'Funcionarios'

    @property
    def full_name(self):
        return f'{self.names} {self.lastnames}'

    # --- Helpers de Verificación de Roles para Vistas y Permisos (RBAC) ---
# En personal/models.py, dentro de class Functionary(BaseModel):


    def has_role(self, role_name):
        return self.functionaryrole_set.filter(
            role__role_name__iexact=role_name,
            role__is_active=True,
        ).exists()


    @property
    def is_admin(self):
        return self.has_role('ADMIN') or self.has_role('Administrador')


    @property
    def is_delegate(self):
        return (
            self.has_role('DELEGATE')
            or self.has_role('Delegado')
            or self.has_role('COORDINATOR')
        )


    @property
    def is_verifier(self):
        return (
            self.has_role('VERIFIER')
            or self.has_role('Verificador')
            or self.is_delegate
            or self.is_admin
        )

    @property
    def has_global_scope(self):
        return self.is_admin or self.functionaryrole_set.filter(
            role__authorized_scope='GLOBAL',
            role__is_active=True,
        ).exists()

    @property
    def roles_list(self):
        """Retorna lista con los códigos de roles asignados."""
        return list(
            self.functionaryrole_set.filter(
                role__is_active=True
            ).values_list('role__role_name', flat=True)
        )

    @property
    def active_roles(self):
        return self.functionaryrole_set.filter(
            role__is_active=True
        ).select_related('role')

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Si es un funcionario nuevo y su cargo tiene un rol por defecto, se le asigna automáticamente
        if (
            is_new
            and self.position
            and self.position.default_role
            and self.position.default_role.is_active
        ):
            FunctionaryRole.objects.get_or_create(
                functionary=self, role=self.position.default_role
            )

    def __str__(self):
        return f'{self.full_name} - {self.position.name}'


class FunctionaryRole(BaseModel):
    functionary = models.ForeignKey(Functionary, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Asignación de rol'
        verbose_name_plural = 'Asignaciones de roles'
        constraints = [
            models.UniqueConstraint(
                fields=['functionary', 'role'], name='unique_functionary_role'
            )
        ]

    def __str__(self):
        return f'{self.functionary.full_name} -> {self.role}'