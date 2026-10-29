import re
import uuid
from django import forms
from django.utils import timezone
from .models import Activity, Evidence


class ActivityForm(forms.ModelForm):
    upload_evidence = forms.BooleanField(
        required=False,
        label='Subir evidencia ahora',
        help_text=(
            'Al guardar la actividad, continuarás al formulario de evidencias '
            'con esta actividad ya seleccionada.'
        ),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = Activity
        fields = [
            'date',
            'measuring',
            'application',
            'taken_action',
            'quantity',
            'name_contact',
            'telephone_contact',
            'enters_pipe',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'required': True}),
            'measuring': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'application': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej: Atención de vecinos por junta de agua',
                    'required': True,
                }
            ),
            'taken_action': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Describa brevemente la solución o gestión realizada...',
                    'required': True,
                }
            ),
            'quantity': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1,
                    'value': 1,
                    'required': True,
                }
            ),
            'name_contact': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre del beneficiario o contacto',
                    'required': True,
                }
            ),
            'telephone_contact': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '+56 9 1234 5678',
                    'required': True,
                }
            ),
            'enters_pipe': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }
        labels = {
            'date': 'Fecha de Registro',
            'measuring': 'Ítem a Medir',
            'application': 'Solicitud / Requerimiento',
            'taken_action': 'Acción Realizada',
            'quantity': 'Cantidad / Personas Atendidas',
            'name_contact': 'Nombre de Contacto',
            'telephone_contact': 'Teléfono de Contacto',
            'enters_pipe': '¿Ingresa al Tubo de Trabajo?',
        }
        help_texts = {
            'quantity': 'Indica cuántas personas o atenciones representa este registro (mínimo 1).'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop('upload_evidence')
            self.fields['date'].disabled = True
            self.fields['date'].help_text = (
                'La fecha original del registro no se puede cambiar al editar.'
            )
        else:
            self.fields['submission_key'] = forms.UUIDField(
                initial=uuid.uuid4,
                widget=forms.HiddenInput,
            )
        active_measurings = self.fields['measuring'].queryset.filter(
            validity=True,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            active_measurings = active_measurings | self.fields[
                'measuring'
            ].queryset.filter(pk=self.instance.measuring_id)
        self.fields['measuring'].queryset = active_measurings.distinct()

    def clean_application(self):
        application = (self.cleaned_data.get('application') or '').strip()
        if not application:
            raise forms.ValidationError('Debe describir la solicitud o requerimiento.')
        return application

    def clean_taken_action(self):
        taken_action = (self.cleaned_data.get('taken_action') or '').strip()
        if not taken_action:
            raise forms.ValidationError('Debe indicar la acción realizada.')
        return taken_action

    def clean_name_contact(self):
        name = (self.cleaned_data.get('name_contact') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre de contacto.')
        return name

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is None or quantity < 1:
            raise forms.ValidationError('La cantidad debe ser mayor o igual a 1.')
        return quantity

    def clean_telephone_contact(self):
        telephone = (self.cleaned_data.get('telephone_contact') or '').strip()
        if not telephone:
            raise forms.ValidationError('Debe ingresar un teléfono de contacto.')
        if not re.fullmatch(r'^[+0-9()\s-]{8,20}$', telephone):
            raise forms.ValidationError('El teléfono no tiene un formato válido.')
        return telephone

    def clean_date(self):
        date_value = self.cleaned_data.get('date')
        if date_value and date_value > timezone.localdate():
            raise forms.ValidationError('La fecha no puede ser futura.')
        return date_value


class EvidenceForm(forms.ModelForm):
    class Meta:
        model = Evidence
        fields = [
            'activity',
            'name',
            'author',
            'date_evidence',
            'file',
            'metadata',
        ]
        widgets = {
            'activity': forms.Select(
                attrs={'class': 'form-select'}
            ),
            'name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: Registro fotográfico de la actividad',
                }
            ),
            'author': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre de quien elaboró el documento',
                }
            ),
            'date_evidence': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'file': forms.ClearableFileInput(
                attrs={'class': 'form-control'}
            ),
            'metadata': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Describe brevemente qué muestra o acredita el archivo.',
                }
            ),
        }
        labels = {
            'activity': 'Actividad relacionada',
            'name': 'Nombre de la evidencia',
            'author': 'Autor de la evidencia',
            'date_evidence': 'Fecha de la evidencia',
            'file': 'Archivo de respaldo',
            'metadata': 'Descripción o información adicional',
        }
        help_texts = {
            'activity': 'Selecciona la actividad que respalda este archivo.',
            'name': 'Usa un nombre breve que permita reconocer la evidencia.',
            'author': 'Indica quién elaboró o emitió la evidencia.',
            'date_evidence': 'No puede ser una fecha futura.',
            'file': 'Selecciona el archivo que quieres adjuntar como respaldo.',
            'metadata': 'Agrega contexto para facilitar la revisión de la evidencia.',
        }
        error_messages = {
            'activity': {'required': 'Selecciona la actividad relacionada.'},
            'name': {'required': 'Ingresa el nombre de la evidencia.'},
            'author': {'required': 'Ingresa el autor de la evidencia.'},
            'date_evidence': {'required': 'Indica la fecha de la evidencia.'},
            'file': {'required': 'Selecciona un archivo de respaldo.'},
            'metadata': {
                'required': 'Agrega una descripción o información adicional.'
            },
        }

    def __init__(self, *args, activities=None, **kwargs):
        super().__init__(*args, **kwargs)
        if activities is not None:
            self.fields['activity'].queryset = activities

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre de la evidencia.')
        return name

    def clean_author(self):
        author = (self.cleaned_data.get('author') or '').strip()
        if not author:
            raise forms.ValidationError('Debe ingresar el autor de la evidencia.')
        return author

    def clean_date_evidence(self):
        evidence_date = self.cleaned_data.get('date_evidence')
        if evidence_date and evidence_date > timezone.localdate():
            raise forms.ValidationError('La fecha de la evidencia no puede ser futura.')
        return evidence_date

    def clean_metadata(self):
        metadata = (self.cleaned_data.get('metadata') or '').strip()
        if not metadata:
            raise forms.ValidationError('Debe ingresar información adicional de la evidencia.')
        return metadata


class EvidenceValidationForm(forms.ModelForm):
    """Formulario aparte, solo para que el verificador apruebe/rechace."""
    class Meta:
        model = Evidence
        fields = ['validity_state', 'observations_validity']
        widgets = {
            'validity_state': forms.Select(attrs={'class': 'form-select'}),
            'observations_validity': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, verificator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['validity_state'].choices = [
            choice
            for choice in Evidence.Validity.choices
            if choice[0] in {
                Evidence.Validity.APPROVED,
                Evidence.Validity.REJECTED,
            }
        ]
        if self.instance:
            self.instance.verificator = verificator

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get('validity_state') == Evidence.Validity.REJECTED
            and not (cleaned_data.get('observations_validity') or '').strip()
        ):
            self.add_error(
                'observations_validity',
                'Debe indicar el motivo cuando rechaza una evidencia.',
            )
        return cleaned_data