from django import forms
from django.db.models import Q
from django.utils import timezone

from personal.models import Delegation, Functionary

from .models import OfficeLetter
from atenciones.forms import AttentionForm
from atenciones.models import Attention


class LetterAttentionCreateForm(AttentionForm):
    class Meta(AttentionForm.Meta):
        fields = AttentionForm.Meta.fields + ['followup_responsible']
        widgets = {**AttentionForm.Meta.widgets, 'followup_responsible': forms.Select(attrs={'class': 'form-select'})}

    def __init__(self, *args, delegation, **kwargs):
        super().__init__(*args, delegation=delegation, **kwargs)
        self.fields['followup_responsible'].required = True
        self.fields['followup_responsible'].queryset = Functionary.objects.filter(
            delegation=delegation, is_active=True, deleted_at__isnull=True,
        ).select_related('position').order_by('names', 'lastnames')
        self.fields['followup_responsible'].help_text = 'Responsable de continuar la atención dentro de esta delegación.'


class LetterAttentionLinkForm(forms.Form):
    attention = forms.ModelChoiceField(queryset=Attention.objects.none(), label='Atención existente')

    def __init__(self, *args, queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attention'].queryset = queryset


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
                attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe brevemente qué solicita o informa la carta.'},
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
            'received_at': 'Fecha de recepción',
            'registry_number': 'Número de registro',
            'recipient': 'Destinatario',
            'sender': 'Remitente',
            'subject': 'Asunto de la carta',
            'responsible': 'Responsable de la carta',
            'pronouncement': 'Respuesta o pronunciamiento',
            'referred_to': 'Área a la que se derivó',
            'observation': 'Observaciones internas',
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        functionary = getattr(user, 'functionary', None)
        is_global = user.is_staff or user.is_superuser or (
            functionary is not None and functionary.has_global_scope
        )

        delegation_field = self.fields['delegation']
        available_delegations = Q(deleted_at__isnull=True, state='ACTIVO')
        if self.instance.pk:
            available_delegations |= Q(pk=self.instance.delegation_id)
        delegation_field.queryset = Delegation.objects.filter(available_delegations)
        if not self.instance.pk:
            self.initial.setdefault('received_at', timezone.localdate())
            self.initial['state'] = OfficeLetter.State.IN_PROGRESS
            self.fields['state'].disabled = True
            self.fields['state'].widget = forms.HiddenInput()
            if functionary is not None:
                self.initial.setdefault('delegation', functionary.delegation_id)
                self.initial.setdefault('responsible', functionary.pk)

        if (not is_global and functionary is not None) or self.instance.attention_id:
            fixed_id = self.instance.delegation_id if self.instance.pk else functionary.delegation_id
            delegation_field.queryset = delegation_field.queryset.filter(pk=fixed_id)
            delegation_field.disabled = True
            self.initial['delegation'] = fixed_id
        self.fixed_delegation = delegation_field.queryset.first() if delegation_field.disabled else None

        allowed_responsibles = Q(is_active=True, deleted_at__isnull=True,
                                 delegation__deleted_at__isnull=True, delegation__state='ACTIVO')
        if self.instance.pk:
            allowed_responsibles |= Q(pk=self.instance.responsible_id, delegation_id=self.instance.delegation_id)
        self._available_responsibles = Functionary.objects.filter(allowed_responsibles, delegation__in=delegation_field.queryset)
        if not is_global and functionary is not None and not functionary.is_delegate:
            self._available_responsibles = self._available_responsibles.filter(Q(pk=functionary.pk) | Q(pk=self.instance.responsible_id))

        delegation_id = self.initial.get('delegation')
        if self.is_bound and not delegation_field.disabled:
            delegation_id = self.data.get(self.add_prefix('delegation'))
        responsible_field = self.fields['responsible']
        responsible_field.queryset = Functionary.objects.none()
        if delegation_id and str(delegation_id).isdigit():
            responsible_field.queryset = self._available_responsibles.filter(delegation_id=delegation_id).select_related('position').order_by('names', 'lastnames')
        responsible_field.label_from_instance = lambda person: person.full_name + (' (registro histórico)' if not person.is_active or person.deleted_at else '')
        responsible_field.help_text = 'Se muestran los funcionarios autorizados de la delegación seleccionada.'
        self.fields['received_at'].help_text = 'Fecha en que se recibió la carta; puede ser distinta a la fecha de registro.'
        self.fields['registry_number'].help_text = 'Número asignado por Oficina de Partes. Déjalo vacío si aún no lo tiene.'
        self.fields['recipient'].widget.attrs['placeholder'] = 'Ej.: Delegación La Serena o Alcaldía'
        self.fields['sender'].widget.attrs['placeholder'] = 'Persona u organización que envía la carta'
        self.fields['pronouncement'].help_text = 'Completa este dato cuando exista una respuesta o decisión municipal.'
        self.fields['referred_to'].help_text = 'Ej.: Aseo y Ornato. Completa solo si la carta ya fue derivada.'
        self.fields['activity_date'].help_text = 'Solo si corresponde: una fecha, un rango o “por confirmar”.'
        for name in ('registry_number', 'contact_phone', 'activity_date', 'pronouncement', 'referred_to', 'observation'):
            self.fields[name].label += ' (opcional)'

    @property
    def responsible_catalog(self):
        catalog = {}
        for person in self._available_responsibles.order_by('names', 'lastnames').values('id', 'names', 'lastnames', 'delegation_id', 'is_active', 'deleted_at'):
            label = f"{person['names']} {person['lastnames']}"
            if not person['is_active'] or person['deleted_at']:
                label += ' (registro histórico)'
            catalog.setdefault(str(person['delegation_id']), []).append({'id': person['id'], 'name': label})
        return catalog

    @property
    def additional_open(self):
        return any(self[name].value() or self[name].errors for name in ('activity_date', 'pronouncement', 'referred_to', 'observation'))


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
