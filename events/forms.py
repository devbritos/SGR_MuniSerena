import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from personal.models import Delegation

from .models import (
    CommunityEvent,
    DelegationPerson,
    EventRegistration,
    RegistrationChild,
)
from .validators import normalize_chilean_rut


PHONE_PATTERN = re.compile(r'^[+0-9()\s-]{8,30}$')


def normalize_phone(value):
    phone = ' '.join((value or '').split())
    digit_count = sum(character.isdigit() for character in phone)
    if not PHONE_PATTERN.fullmatch(phone) or not 8 <= digit_count <= 15:
        raise forms.ValidationError('Ingresa un teléfono con formato válido.')
    return phone


class CommunityEventForm(forms.ModelForm):
    class Meta:
        model = CommunityEvent
        fields = [
            'delegation',
            'title',
            'event_type',
            'description',
            'what_to_expect',
            'starts_at',
            'ends_at',
            'location',
            'image',
            'capacity',
            'registration_deadline',
            'status',
        ]
        widgets = {
            'delegation': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 4}
            ),
            'what_to_expect': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 4}
            ),
            'starts_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'ends_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': 'image/jpeg,image/png,image/webp',
                }
            ),
            'capacity': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1}
            ),
            'registration_deadline': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('starts_at', 'ends_at', 'registration_deadline'):
            self.fields[field_name].input_formats = [
                '%Y-%m-%dT%H:%M',
                '%Y-%m-%dT%H:%M:%S',
            ]
        functionary = getattr(user, 'functionary', None)
        is_global = user.is_staff or user.is_superuser or (
            functionary is not None and functionary.has_global_scope
        )
        self.fields['delegation'].queryset = Delegation.objects.filter(
            deleted_at__isnull=True,
            state='ACTIVO',
        )
        if not is_global and functionary is not None:
            self.fields['delegation'].queryset = self.fields[
                'delegation'
            ].queryset.filter(pk=functionary.delegation_id)
            self.fields['delegation'].initial = functionary.delegation_id
            self.fields['delegation'].disabled = True


class DelegationPersonForm(forms.ModelForm):
    class Meta:
        model = DelegationPerson
        fields = [
            'delegation',
            'full_name',
            'rut',
            'email',
            'phone',
            'is_active',
        ]
        widgets = {
            'delegation': forms.Select(attrs={'class': 'form-select'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'rut': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '12.345.678-5',
                    'autocomplete': 'off',
                }
            ),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '+56 9 1234 5678',
                    'inputmode': 'tel',
                }
            ),
            'is_active': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        functionary = getattr(user, 'functionary', None)
        is_global = user.is_staff or user.is_superuser or (
            functionary is not None and functionary.has_global_scope
        )
        delegations = Delegation.objects.filter(
            deleted_at__isnull=True,
            state='ACTIVO',
        )
        if not is_global and functionary is not None:
            delegations = delegations.filter(pk=functionary.delegation_id)
            self.fields['delegation'].initial = functionary.delegation_id
            self.fields['delegation'].disabled = True
        self.fields['delegation'].queryset = delegations

    def clean_full_name(self):
        name = ' '.join((self.cleaned_data.get('full_name') or '').split())
        if not name:
            raise forms.ValidationError('Ingresa el nombre completo.')
        return name

    def clean_rut(self):
        return normalize_chilean_rut(self.cleaned_data.get('rut'))

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip().lower()

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))


class PublicEventRegistrationForm(forms.ModelForm):
    consent = forms.BooleanField(
        required=True,
        label='Acepto que estos datos se utilicen para gestionar esta inscripción.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = EventRegistration
        fields = ['full_name', 'rut', 'email', 'phone', 'adult_attends']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'rut': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '12.345.678-5',
                    'autocomplete': 'off',
                }
            ),
            'email': forms.EmailInput(
                attrs={'class': 'form-control', 'autocomplete': 'email'}
            ),
            'phone': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '+56 9 1234 5678',
                    'inputmode': 'tel',
                }
            ),
            'adult_attends': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }
        labels = {
            'adult_attends': 'Yo también asistiré al evento',
        }
        help_texts = {
            'rut': (
                'Se valida el formato y el dígito verificador; no se consulta '
                'una base de identidad externa.'
            ),
            'phone': 'El teléfono se valida por formato; no se envía un SMS.',
        }

    def clean_full_name(self):
        name = ' '.join((self.cleaned_data.get('full_name') or '').split())
        if not name:
            raise forms.ValidationError('Ingresa tu nombre completo.')
        return name

    def clean_rut(self):
        return normalize_chilean_rut(self.cleaned_data.get('rut'))

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip().lower()

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.consented_at = timezone.now()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RegistrationChildForm(forms.ModelForm):
    class Meta:
        model = RegistrationChild
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {'full_name': 'Nombre completo del menor'}

    def clean_full_name(self):
        return ' '.join((self.cleaned_data.get('full_name') or '').split())


class RegistrationChildFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        child_count = sum(
            1
            for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get('DELETE', False)
            and form.cleaned_data.get('full_name')
        )
        if child_count == 0 and not self.instance.adult_attends:
            raise ValidationError(
                'Inscríbete tú o agrega al menos un menor participante.'
            )


RegistrationChildFormSetFactory = inlineformset_factory(
    EventRegistration,
    RegistrationChild,
    form=RegistrationChildForm,
    formset=RegistrationChildFormSet,
    extra=1,
    max_num=10,
    validate_max=True,
    can_delete=True,
)
