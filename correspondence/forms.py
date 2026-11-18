from django import forms
from django.db.models import Q

from personal.models import Delegation, Functionary

from .models import OfficeLetter


class OfficeLetterForm(forms.ModelForm):
    class Meta:
        model = OfficeLetter
        fields = [
            'delegation',
            'received_at',
            'registry_number',
            'recipient',
            'sender',
            'contact_phone',
            'subject',
            'activity_date',
            'responsible',
            'state',
            'pronouncement',
            'referred_to',
            'observation',
        ]
        widgets = {
            'delegation': forms.Select(attrs={'class': 'form-select'}),
            'received_at': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
                format='%Y-%m-%d',
            ),
            'registry_number': forms.TextInput(
                attrs={'class': 'form-control', 'autocomplete': 'off'},
            ),
            'recipient': forms.TextInput(attrs={'class': 'form-control'}),
            'sender': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(
                attrs={'class': 'form-control', 'inputmode': 'tel'},
            ),
            'subject': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3},
            ),
            'activity_date': forms.TextInput(attrs={'class': 'form-control'}),
            'responsible': forms.Select(attrs={'class': 'form-select'}),
            'state': forms.Select(attrs={'class': 'form-select'}),
            'pronouncement': forms.TextInput(attrs={'class': 'form-control'}),
            'referred_to': forms.TextInput(attrs={'class': 'form-control'}),
            'observation': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3},
            ),
        }
        labels = {
            'recipient': 'Para',
            'sender': 'Remite',
            'subject': 'Actividad o tema',
            'responsible': 'Encargado del seguimiento',
            'referred_to': 'Derivada a',
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        functionary = getattr(user, 'functionary', None)
        is_global = user.is_staff or user.is_superuser or (
            functionary is not None and functionary.has_global_scope
        )

        self.fields['delegation'].queryset = Delegation.objects.filter(
            deleted_at__isnull=True,
            state='ACTIVO',
        )
        self.fields['responsible'].queryset = Functionary.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
            delegation__deleted_at__isnull=True,
            delegation__state='ACTIVO',
        ).select_related('delegation', 'position')

        if not is_global and functionary is not None:
            self.fields['delegation'].queryset = Delegation.objects.filter(
                Q(pk=functionary.delegation_id)
                | Q(pk=self.instance.delegation_id)
            )
            self.fields['delegation'].initial = functionary.delegation_id
            self.fields['delegation'].disabled = True
            self.fields['responsible'].queryset = (
                self.fields['responsible'].queryset.filter(
                    delegation=functionary.delegation,
                )
            )
            if not functionary.is_delegate:
                self.fields['responsible'].queryset = (
                    self.fields['responsible'].queryset.filter(
                        Q(pk=functionary.pk)
                        | Q(pk=self.instance.responsible_id)
                    )
                )
            if not self.instance.pk:
                self.fields['responsible'].initial = functionary.pk


class OfficeLetterFilterForm(forms.Form):
    search = forms.CharField(
        required=False,
        label='Buscar',
        widget=forms.SearchInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Número, remitente, tema o responsable',
            }
        ),
    )
    state = forms.ChoiceField(
        required=False,
        label='Estado',
        choices=[('', 'Todos los estados'), *OfficeLetter.State.choices],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    received_from = forms.DateField(
        required=False,
        label='Desde',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    received_to = forms.DateField(
        required=False,
        label='Hasta',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('received_from')
        end = cleaned_data.get('received_to')
        if start and end and end < start:
            self.add_error(
                'received_to',
                'La fecha final no puede ser anterior a la fecha inicial.',
            )
        return cleaned_data
