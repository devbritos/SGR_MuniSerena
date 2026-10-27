from django import forms
from django.db.models import Q

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
            'attention_type',
            'sub_attention',
            'description',
        ]
        widgets = {
            'requester_name': forms.TextInput(attrs={'class': 'form-control'}),
            'requester_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'attention_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_attention_type'}),
            'sub_attention': forms.Select(attrs={'class': 'form-select', 'id': 'id_sub_attention'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        self.fields['sub_attention'].queryset = SubAttention.objects.none()
        type_id = self.data.get('attention_type') or self.initial.get('attention_type')
        if type_id and str(type_id).isdigit():
            self.fields['sub_attention'].queryset = sub_attentions.filter(
                attention_type_id=type_id,
            )

    def clean(self):
        cleaned_data = super().clean()
        attention_type = cleaned_data.get('attention_type')
        sub_attention = cleaned_data.get('sub_attention')
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
