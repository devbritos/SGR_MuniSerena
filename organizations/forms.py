from django import forms
from django.db.models import Q
from events.validators import normalize_chilean_rut
from personal.models import Delegation
from .models import Organization, OrganizationLeader

class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3

class OrganizationForm(StyledForm):
    class Meta:
        model = Organization
        fields = ['delegation', 'name', 'rut', 'registry_number', 'organization_type', 'territory', 'address', 'phone', 'email', 'status', 'observations']
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        fn = user.functionary
        allowed = Q(state='ACTIVO', deleted_at__isnull=True)
        if self.instance.pk:
            allowed |= Q(pk=self.instance.delegation_id)
        self.fields['delegation'].queryset = Delegation.objects.filter(allowed)
        self.fixed_delegation = None
        if not (user.is_staff or user.is_superuser or fn.has_global_scope):
            self.fields['delegation'].queryset = self.fields['delegation'].queryset.filter(pk=fn.delegation_id)
            self.fields['delegation'].disabled = True
            self.initial['delegation'] = fn.delegation_id
            self.fixed_delegation = fn.delegation
        elif not self.instance.pk:
            self.initial.setdefault('delegation', fn.delegation_id)
        if self.instance.pk:
            self.fields['delegation'].disabled = True
            self.fixed_delegation = self.instance.delegation
        self.fields['rut'].help_text = 'Si se informa, se valida su dígito verificador. No es obligatorio para organizaciones en formación.'
        self.fields['organization_type'].widget.attrs['placeholder'] = 'Ej.: Junta de vecinos, club deportivo o agrupación cultural'
    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Ingresa el nombre de la organización.')
        return name
    def clean_rut(self):
        value = (self.cleaned_data.get('rut') or '').strip()
        return normalize_chilean_rut(value) if value else None
    def clean(self):
        data = super().clean()
        if data.get('rut') and data.get('delegation'):
            if Organization.objects.filter(delegation=data['delegation'], rut=data['rut']).exclude(pk=self.instance.pk).exists():
                self.add_error('rut', 'Ya existe una organización con este RUT en la delegación.')
        return data

class LeaderForm(StyledForm):
    class Meta:
        model = OrganizationLeader
        fields = ['name', 'position', 'phone', 'email', 'starts_on', 'ends_on', 'is_active', 'observations']
        widgets = {name: forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}) for name in ['starts_on', 'ends_on']}
