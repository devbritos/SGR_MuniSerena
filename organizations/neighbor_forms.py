from django import forms

from events.validators import normalize_chilean_rut
from .models import Neighbor


class NeighborForm(forms.ModelForm):
    class Meta:
        model = Neighbor
        fields = ['rut', 'name', 'phone', 'email', 'organizations']
        widgets = {
            'phone': forms.TextInput(attrs={'type': 'tel'}),
            'organizations': forms.SelectMultiple(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, delegation, organizations, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.delegation = delegation
        self.fields['organizations'].queryset = organizations.filter(delegation=delegation)
        self.fields['organizations'].help_text = 'Opcional. Usa Ctrl o Cmd para seleccionar varias juntas.'
        for name in ('rut', 'name', 'phone', 'email'):
            self.fields[name].widget.attrs['class'] = 'form-control'

    def clean_rut(self):
        rut = normalize_chilean_rut(self.cleaned_data['rut'])
        existing = Neighbor.objects.filter(delegation=self.instance.delegation, rut=rut)
        if existing.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe un vecino con este RUT en la delegación.')
        return rut
