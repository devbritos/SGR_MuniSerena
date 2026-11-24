from django import forms
from django.db.models import Q
from django.utils import timezone

from personal.models import Functionary
from agenda.forms import CommitmentForm
from organizations.models import Organization

from .models import Attention, AttentionType, SubAttention


class AttentionTypeForm(forms.ModelForm):
    class Meta:
        model = AttentionType
        fields = ['code', 'name', 'description', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise forms.ValidationError('Debe ingresar el código del tipo de atención.')
        return code

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre del tipo de atención.')
        return name


class SubAttentionForm(forms.ModelForm):
    class Meta:
        model = SubAttention
        fields = ['code', 'name', 'description', 'attention_type', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'attention_type': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise forms.ValidationError('Debe ingresar el código de la subatención.')
        return code

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre de la subatención.')
        return name


class AttentionForm(forms.ModelForm):
    class Meta:
        model = Attention
        fields = [
            'requester_name',
            'requester_contact',
            'organization',
            'attention_type',
            'sub_attention',
            'description',
        ]
        widgets = {
            'requester_name': forms.TextInput(attrs={'class': 'form-control'}),
            'requester_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'organization': forms.Select(attrs={'class': 'form-select'}),
            'attention_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_attention_type'}),
            'sub_attention': forms.Select(attrs={'class': 'form-select', 'id': 'id_sub_attention'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        delegation = kwargs.pop('delegation', None)
        super().__init__(*args, **kwargs)
        delegation_id = delegation.pk if delegation else None
        if self.instance.pk:
            delegation_id = self.instance.delegation_id
        elif delegation is None and user and getattr(user, 'functionary', None):
            delegation_id = user.functionary.delegation_id
        organizations = Organization.objects.filter(
            deleted_at__isnull=True,
            status__in=[Organization.Status.ACTIVE, Organization.Status.FORMING],
        )
        if delegation_id:
            organizations = organizations.filter(delegation_id=delegation_id)
        if self.instance.pk and self.instance.organization_id:
            organizations = Organization.objects.filter(
                Q(pk__in=organizations.values('pk')) | Q(pk=self.instance.organization_id),
            ).filter(delegation_id=self.instance.delegation_id)
        self.fields['organization'].queryset = organizations.select_related('delegation').order_by('name')
        self.fields['organization'].required = False
        self.fields['organization'].label = 'Organización comunitaria'
        self.fields['organization'].empty_label = 'Sin organización vinculada'
        attention_types = AttentionType.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        sub_attentions = SubAttention.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            attention_types = AttentionType.objects.filter(
                Q(is_active=True, deleted_at__isnull=True)
                | Q(pk=self.instance.attention_type_id)
            )
            sub_attentions = SubAttention.objects.filter(
                Q(is_active=True, deleted_at__isnull=True)
                | Q(pk=self.instance.sub_attention_id)
            )
        self.fields['attention_type'].queryset = attention_types
        self._available_sub_attentions = sub_attentions.filter(attention_type__in=attention_types)
        self.fields['sub_attention'].queryset = SubAttention.objects.none()
        type_id = self.data.get('attention_type') or self.initial.get('attention_type')
        if type_id and str(type_id).isdigit():
            self.fields['sub_attention'].queryset = sub_attentions.filter(
                attention_type_id=type_id,
            )

    @property
    def subattention_catalog(self):
        catalog = {}
        for item in self._available_sub_attentions.values('id', 'name', 'attention_type_id'):
            catalog.setdefault(str(item['attention_type_id']), []).append({'id': item['id'], 'name': item['name']})
        return catalog

    def clean(self):
        cleaned_data = super().clean()
        attention_type = cleaned_data.get('attention_type')
        sub_attention = cleaned_data.get('sub_attention')
        organization = cleaned_data.get('organization')
        if organization and getattr(self.instance, 'delegation_id', None) and organization.delegation_id != self.instance.delegation_id:
            self.add_error('organization', 'La organización comunitaria debe pertenecer a la delegación de la atención.')
        if (
            attention_type
            and sub_attention
            and sub_attention.attention_type_id != attention_type.pk
        ):
            self.add_error(
                'sub_attention',
                'Selecciona una subatención correspondiente al tipo elegido.',
            )
        return cleaned_data


class AttentionCommitmentForm(CommitmentForm):
    activity_id = None
    creation_token = forms.UUIDField(widget=forms.HiddenInput)

    class Meta(CommitmentForm.Meta):
        fields = ['applic_name', 'territory', 'functionary', 'commitment_date', 'observation']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['observation'].required = True
        self.fields['observation'].label = '¿Qué se acordó hacer?'
        self.fields['commitment_date'].label = 'Fecha de cumplimiento'
        self.fields['applic_name'].label = 'Solicitante'
        self.fields['territory'].help_text = 'Confirma el sector donde se realizará la gestión.'


class AttentionFollowUpForm(forms.Form):
    version = forms.CharField(widget=forms.HiddenInput)
    note = forms.CharField(label='¿Qué gestión realizaste?', max_length=5000, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Ej.: Llamé a la vecina y confirmé la visita técnica.'}))
    status = forms.ChoiceField(label='Estado de la atención', choices=[choice for choice in Attention.Status.choices if choice[0] != Attention.Status.UNCLASSIFIED], widget=forms.Select(attrs={'class': 'form-select'}))
    followup_responsible = forms.ModelChoiceField(label='Responsable del seguimiento', queryset=Functionary.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    next_action = forms.CharField(label='Próxima acción', max_length=250, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Informar al vecino sobre la respuesta recibida'}))
    next_contact_date = forms.DateField(label='Fecha de próxima acción', required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}))
    closure_outcome = forms.ChoiceField(label='Resultado del cierre', required=False, choices=[('', 'Selecciona un resultado')] + Attention.Outcome.choices, widget=forms.Select(attrs={'class': 'form-select'}))
    closure_details = forms.CharField(label='¿Cómo terminó la atención?', max_length=5000, required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

    def __init__(self, *args, attention, **kwargs):
        super().__init__(*args, **kwargs)
        self.attention = attention
        self.fields['followup_responsible'].queryset = Functionary.objects.filter(
            delegation_id=attention.delegation_id, is_active=True, deleted_at__isnull=True,
        ).select_related('position').order_by('names', 'lastnames')
        self.initial.update({
            'version': attention.updated_at.isoformat(),
            'status': Attention.Status.PENDING if attention.status == Attention.Status.UNCLASSIFIED else attention.status,
            'followup_responsible': attention.followup_responsible_id or attention.functionary_id,
            'next_action': attention.next_action,
            'next_contact_date': attention.next_contact_date,
        })

    def clean(self):
        data = super().clean()
        if data.get('status') == Attention.Status.CLOSED:
            if not data.get('closure_outcome'):
                self.add_error('closure_outcome', 'Selecciona cómo terminó la atención.')
            if not data.get('closure_details'):
                self.add_error('closure_details', 'Describe el resultado para conservarlo en el historial.')
            data['next_action'] = ''
            data['next_contact_date'] = None
        else:
            if not data.get('next_action'):
                self.add_error('next_action', 'Indica qué falta hacer antes de guardar.')
            next_date = data.get('next_contact_date')
            if not next_date:
                self.add_error('next_contact_date', 'Indica cuándo debe realizarse la próxima acción.')
            elif next_date < timezone.localdate():
                self.add_error('next_contact_date', 'Selecciona hoy o una fecha futura.')
            data['closure_outcome'] = ''
            data['closure_details'] = ''
        return data
