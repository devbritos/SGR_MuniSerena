from django import forms
from django.apps import apps
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import models
from .models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)


class DelegationForm(forms.ModelForm):
    class Meta:
        model = Delegation
        fields = ['code', 'name', 'address', 'commune', 'state', 'field']
        labels = {
            'code': 'Código de delegación',
            'name': 'Nombre de la delegación',
            'address': 'Dirección',
            'commune': 'Comuna',
            'state': 'Estado',
            'field': 'Ámbito territorial',
        }
        help_texts = {
            'code': 'Identificador único para reconocer esta delegación.',
            'name': 'Usa el nombre oficial con el que se identifica la delegación.',
            'address': 'Ingresa la dirección donde funciona la delegación.',
            'commune': 'Comuna en la que se encuentra ubicada.',
            'state': 'Las delegaciones inactivas no estarán disponibles para nuevas asignaciones.',
            'field': 'Selecciona si la delegación corresponde a un ámbito rural o urbano.',
        }
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej.: DEL-001',
                'autocomplete': 'off',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej.: Delegación Centro',
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Calle, número y referencia',
            }),
            'commune': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la comuna',
            }),
            'state': forms.Select(attrs={'class': 'form-select'}),
            'field': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('code', 'address', 'commune'):
            self.fields[field_name].required = True

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre de la delegación.')
        return name

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise forms.ValidationError('Debe ingresar el código de la delegación.')
        return code

    def clean_address(self):
        address = (self.cleaned_data.get('address') or '').strip()
        if not address:
            raise forms.ValidationError('Debe ingresar la dirección de la delegación.')
        return address

    def clean_commune(self):
        commune = (self.cleaned_data.get('commune') or '').strip()
        if not commune:
            raise forms.ValidationError('Debe ingresar la comuna de la delegación.')
        return commune


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['name', 'validity', 'default_role']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'validity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_role': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_role'].queryset = Role.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre del cargo.')
        return name


class RoleForm(forms.ModelForm):
    PERMISSION_ACTION_LABELS = {
        'add': 'Crear',
        'change': 'Editar',
        'delete': 'Eliminar',
        'view': 'Ver',
    }

    role_name = forms.CharField(
        max_length=30,
        label='Nombre del rol',
        help_text=(
            'Escribe un nombre nuevo o selecciona uno de los roles estándar '
            'sugeridos. Los permisos especiales se conservan en los roles estándar.'
        ),
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'list': 'standard-role-names',
                'placeholder': 'Ej.: Analista de proyectos',
                'autocomplete': 'off',
            }
        ),
    )

    class Meta:
        model = Role
        fields = [
            'role_name',
            'description',
            'permissions',
            'authorized_scope',
            'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'authorized_scope': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['role_name'] = self.instance.get_role_name_display()
        permission_queryset = self.fields[
            'permissions'
        ].queryset.select_related('content_type').order_by(
            'content_type__app_label',
            'codename',
        )
        self.fields['permissions'].queryset = permission_queryset

        selected_ids = {
            str(permission_id)
            for permission_id in (self['permissions'].value() or [])
        }
        grouped_permissions = {}
        for permission in permission_queryset:
            content_type = permission.content_type
            app_config = apps.get_app_config(content_type.app_label)
            group = grouped_permissions.setdefault(
                content_type.app_label,
                {
                    'name': app_config.verbose_name,
                    'permissions': [],
                },
            )
            action, separator, _ = permission.codename.partition('_')
            if separator and action in self.PERMISSION_ACTION_LABELS:
                label = (
                    f'{self.PERMISSION_ACTION_LABELS[action]} '
                    f'{content_type.name.lower()}'
                )
            else:
                label = permission.name
            group['permissions'].append({
                'id': permission.pk,
                'label': label,
                'description': permission.name,
                'selected': str(permission.pk) in selected_ids,
            })
        self.permission_groups = [
            {'name': group['name'], 'permissions': group['permissions']}
            for group in grouped_permissions.values()
        ]

    def clean_role_name(self):
        role_name = (self.cleaned_data.get('role_name') or '').strip()
        if not role_name:
            raise forms.ValidationError('Debes ingresar el nombre del rol.')

        if self.instance.pk and role_name == self.instance.role_name:
            return role_name

        standard_names = {
            display_name.casefold(): code
            for code, display_name in Role.ROLE_CHOICES
        }
        role_name = standard_names.get(role_name.casefold(), role_name)
        duplicate = Role.objects.filter(role_name__iexact=role_name)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError(
                'Ya existe un rol con ese nombre. Elige otro nombre.'
            )
        return role_name


class FunctionaryUpdateForm(forms.ModelForm):
    email = forms.EmailField(
        required=False,
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        required=False,
        label='Roles asignados',
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'role-checkbox-list'}
        ),
    )

    class Meta:
        model = Functionary
        fields = ['names', 'lastnames', 'delegation', 'position', 'is_active']
        labels = {
            'names': 'Nombres',
            'lastnames': 'Apellidos',
            'delegation': 'Delegación',
            'position': 'Cargo',
            'is_active': 'Funcionario activo',
        }
        widgets = {
            'names': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ej.: María José'}
            ),
            'lastnames': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ej.: Pérez Soto'}
            ),
            'delegation': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        delegations = Delegation.objects.filter(
            state='ACTIVO',
            deleted_at__isnull=True,
        )
        positions = Position.objects.filter(validity=True, deleted_at__isnull=True)
        if self.instance.pk:
            delegations = Delegation.objects.filter(
                models.Q(state='ACTIVO') | models.Q(pk=self.instance.delegation_id)
            )
            positions = Position.objects.filter(
                models.Q(validity=True) | models.Q(pk=self.instance.position_id)
            )
        self.fields['delegation'].queryset = delegations
        self.fields['position'].queryset = positions
        self.fields['roles'].queryset = Role.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            self.fields['roles'].initial = Role.objects.filter(
                functionaryrole__functionary=self.instance,
                is_active=True,
            )
            if self.instance.user:
                self.fields['email'].initial = self.instance.user.email

    def clean_names(self):
        names = (self.cleaned_data.get('names') or '').strip()
        if not names:
            raise forms.ValidationError('Debe ingresar los nombres del funcionario.')
        return names

    def clean_lastnames(self):
        lastnames = (self.cleaned_data.get('lastnames') or '').strip()
        if not lastnames:
            raise forms.ValidationError('Debe ingresar los apellidos del funcionario.')
        return lastnames

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if self.instance.user and not email:
            raise forms.ValidationError('Debe ingresar el correo electrónico.')
        if email and User.objects.filter(email__iexact=email).exclude(
            pk=getattr(self.instance.user, 'pk', None)
        ).exists():
            raise forms.ValidationError(
                'Este correo ya está asociado a otra cuenta.'
            )
        return email

    @transaction.atomic
    def save(self, commit=True):
        if self.cleaned_data.get('is_active'):
            self.instance.deleted_at = None
        functionary = super().save(commit=commit)
        if commit:
            selected_roles = self.cleaned_data.get('roles')
            FunctionaryRole.objects.filter(functionary=functionary).exclude(
                role__in=selected_roles
            ).delete()
            for role in selected_roles:
                FunctionaryRole.objects.get_or_create(
                    functionary=functionary,
                    role=role,
                )
            if functionary.user:
                functionary.user.email = self.cleaned_data.get('email', '')
                functionary.user.is_active = functionary.is_active
                functionary.user.first_name = functionary.names
                functionary.user.last_name = functionary.lastnames
                functionary.user.save(
                    update_fields=[
                        'email',
                        'is_active',
                        'first_name',
                        'last_name',
                    ]
                )
        return functionary


class FunctionaryRoleForm(forms.ModelForm):
    class Meta:
        model = FunctionaryRole
        fields = ['functionary', 'role']
        widgets = {
            'functionary': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['functionary'].queryset = Functionary.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        self.fields['role'].queryset = Role.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )

    def clean(self):
        cleaned_data = super().clean()
        functionary = cleaned_data.get('functionary')
        role = cleaned_data.get('role')
        if (
            functionary
            and role
            and FunctionaryRole.objects.filter(
                functionary=functionary,
                role=role,
            ).exclude(pk=self.instance.pk).exists()
        ):
            self.add_error('role', 'Este funcionario ya tiene asignado ese rol.')
        return cleaned_data


class FunctionaryCustomForm(forms.ModelForm):
    # Campos para la cuenta de acceso Django
    username = forms.CharField(
        max_length=150,
        label="Nombre de usuario",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej.: jperez",
                "autocomplete": "username",
            }
        )
    )
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "nombre@laserena.cl",
                "autocomplete": "email",
            }
        )
    )
    password = forms.CharField(
        label="Contraseña",
        help_text="Debe cumplir las reglas de seguridad definidas para las contraseñas.",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Crea una contraseña segura",
                "autocomplete": "new-password",
            }
        )
    )

    # Selección múltiple de roles
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "role-checkbox-list"}
        ),
        required=False,
        label="Roles del sistema"
    )

    class Meta:
        model = Functionary
        fields = ["names", "lastnames", "delegation", "position"]
        labels = {
            "names": "Nombres",
            "lastnames": "Apellidos",
            "delegation": "Delegación",
            "position": "Cargo",
        }
        widgets = {
            "names": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej.: María José",
                    "autocomplete": "given-name",
                }
            ),
            "lastnames": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej.: Pérez Soto",
                    "autocomplete": "family-name",
                }
            ),
            "delegation": forms.Select(attrs={"class": "form-select"}),
            "position": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['delegation'].queryset = Delegation.objects.filter(
            state='ACTIVO',
            deleted_at__isnull=True,
        )
        self.fields['position'].queryset = Position.objects.filter(
            validity=True,
            deleted_at__isnull=True,
        )
        self.fields['roles'].queryset = Role.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("El nombre de usuario ya está registrado.")
        return username

    def clean_names(self):
        names = (self.cleaned_data.get("names") or "").strip()
        if not names:
            raise forms.ValidationError("Debe ingresar los nombres del funcionario.")
        return names

    def clean_lastnames(self):
        lastnames = (self.cleaned_data.get("lastnames") or "").strip()
        if not lastnames:
            raise forms.ValidationError("Debe ingresar los apellidos del funcionario.")
        return lastnames

    def clean_password(self):
        password = self.cleaned_data.get("password")
        try:
            validate_password(password)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        return password

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if not email:
            raise forms.ValidationError("Debe ingresar un correo electrónico.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este correo ya está registrado.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        # 1. Crear el usuario en auth_user
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["names"],
            last_name=self.cleaned_data["lastnames"],
        )

        # 2. Asociar al modelo Functionary
        functionary = super().save(commit=False)
        functionary.user = user

        if commit:
            functionary.save()
            # 3. Guardar las relaciones en FunctionaryRole
            selected_roles = self.cleaned_data.get("roles")
            if selected_roles:
                for role in selected_roles:
                    FunctionaryRole.objects.get_or_create(
                        functionary=functionary,
                        role=role,
                    )

        return functionary