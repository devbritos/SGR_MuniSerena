from django import forms
from django.db.models import Q
from django.utils import timezone

from personal.models import Functionary

from .models import Commitment


class CommitmentForm(forms.ModelForm):
    # Campo oculto opcional para vincular la actividad de origen (RF-07)
    activity_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Commitment
        fields = [
            'origin', 'applic_name', 'territory', 'commitment_date',
            'support', 'state', 'observation', 'measuring', 'functionary',
        ]
        widgets = {
            'origin': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Dirigente junta de vecinos, Concejo, etc.'
            }),
            'applic_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Nombre de la persona o entidad solicitante'
            }),
            'territory': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Sector Las Compañías, Cuadrante 2'
            }),
            'commitment_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'form-control',
            }, format='%Y-%m-%d'),
            'support': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Oficio N° 102 / Correo'
            }),
            'state': forms.Select(attrs={
                'class': 'form-select'
            }),
            'observation': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Detalle del compromiso y acuerdos alcanzados...'
            }),
            'measuring': forms.Select(attrs={
                'class': 'form-select'
            }),
            'functionary': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        labels = {
            'origin': 'Origen de la Solicitud',
            'applic_name': 'Nombre del Solicitante',
            'territory': 'Territorio / Sector',
            'commitment_date': 'Fecha Límite de Cumplimiento',
            'support': 'Respaldo / Medio',
            'state': 'Estado del Compromiso',
            'observation': 'Observación / Compromiso Adquirido',
            'measuring': 'Ítem a Medir Asociado',
            'functionary': 'Responsable del compromiso',
        }

    def __init__(self, *args, delegation=None, **kwargs):
        super().__init__(*args, **kwargs)
        functionary_field = self.fields['functionary']
        functionary_field.queryset = Functionary.objects.none()
        functionary_field.help_text = (
            f'Selecciona un funcionario de la delegación {delegation.name}.'
            if delegation is not None
            else 'No hay una delegación disponible para asignar el responsable.'
        )
        if delegation is not None:
            eligible_functionaries = Functionary.objects.filter(
                delegation=delegation,
                is_active=True,
                deleted_at__isnull=True,
            )
            if self.instance.pk and self.instance.functionary_id:
                eligible_functionaries = Functionary.objects.filter(
                    delegation=delegation,
                ).filter(
                    Q(
                        is_active=True,
                        deleted_at__isnull=True,
                    )
                    | Q(pk=self.instance.functionary_id)
                )
            functionary_field.queryset = eligible_functionaries.select_related(
                'position',
            ).order_by('names', 'lastnames')

        # Si es una creación nueva, establecer estado inicial por defecto
        if not self.instance.pk and 'state' in self.fields:
            self.fields['state'].initial = 'JOINED'

    def clean_origin(self):
        origin = (self.cleaned_data.get('origin') or '').strip()
        if not origin:
            raise forms.ValidationError('Debe indicar el origen de la solicitud.')
        return origin

    def clean_applic_name(self):
        name = (self.cleaned_data.get('applic_name') or '').strip()
        if not name:
            raise forms.ValidationError('Debe ingresar el nombre del solicitante.')
        return name

    def clean_territory(self):
        territory = (self.cleaned_data.get('territory') or '').strip()
        if not territory:
            raise forms.ValidationError('Debe indicar el territorio o sector.')
        return territory

    def clean_commitment_date(self):
        commitment_date = self.cleaned_data.get('commitment_date')
        if (
            not self.instance.pk
            and commitment_date
            and commitment_date < timezone.localdate()
        ):
            raise forms.ValidationError(
                'La fecha del compromiso no puede estar en el pasado.'
            )
        return commitment_date

    def clean_observation(self):
        return (self.cleaned_data.get('observation') or '').strip()