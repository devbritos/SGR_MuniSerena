from django import forms
from django.db.models import Q

from personal.models import Position

from .models import Goal, Measuring, Period


class MeasuringForm(forms.ModelForm):
    class Meta:
        model = Measuring
        fields = ['code', 'service', 'measurable_item', 'validity']
        widgets = {
            'code': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: MED-001',
                    'autocomplete': 'off',
                }
            ),
            'service': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: Atención de solicitudes vecinales',
                }
            ),
            'measurable_item': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Describe qué se contará o evaluará con este ítem.',
                }
            ),
            'validity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'code': 'Código del ítem',
            'service': 'Nombre del ítem de medición',
            'measurable_item': 'Descripción',
            'validity': 'Ítem activo',
        }
        help_texts = {
            'code': 'Identificador único para reconocer este ítem en reportes y metas.',
            'service': 'Nombre breve que verán los funcionarios al registrar actividades.',
            'measurable_item': 'Indica qué resultado o actividad se medirá.',
            'validity': 'Solo los ítems activos estarán disponibles para nuevos registros.',
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise forms.ValidationError('Debe ingresar el código del ítem.')
        return code

    def clean_service(self):
        service = (self.cleaned_data.get('service') or '').strip()
        if not service:
            raise forms.ValidationError('Debe ingresar el nombre del ítem.')
        return service


class GoalForm(forms.ModelForm):
    positions = forms.ModelMultipleChoiceField(
        queryset=Position.objects.none(),
        label='Cargos responsables',
        help_text=(
            'Los cargos marcados comparten esta meta. En edición se cargan '
            'automáticamente los cargos asociados.'
        ),
        widget=forms.CheckboxSelectMultiple(
            attrs={
                'class': 'form-check-input',
                'aria-describedby': 'id_positions_helptext',
            }
        ),
        error_messages={
            'required': 'Selecciona al menos un cargo responsable.',
        },
    )

    class Meta:
        model = Goal
        fields = [
            'measuring',
            'period',
            'weight',
            'validity',
            'target_value',
            'unity',
        ]
        widgets = {
            'measuring': forms.Select(
                attrs={
                    'class': 'form-select',
                    'aria-describedby': 'id_measuring_helptext',
                }
            ),
            'period': forms.Select(
                attrs={
                    'class': 'form-select',
                    'aria-describedby': 'id_period_helptext',
                }
            ),
            'weight': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': '0',
                    'max': '100',
                    'step': '0.01',
                    'placeholder': 'Ej.: 25',
                }
            ),
            'validity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'target_value': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': '0.01',
                    'step': '0.01',
                    'placeholder': 'Ej.: 120',
                }
            ),
            'unity': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: atenciones',
                }
            ),
        }
        labels = {
            'measuring': 'Ítem de medición',
            'period': 'Período de medición',
            'weight': 'Ponderación (%)',
            'validity': 'Meta activa',
            'target_value': 'Valor de la meta',
            'unity': 'Unidad de medida',
        }
        help_texts = {
            'measuring': 'Ítem cuyo avance se calculará para cada cargo seleccionado.',
            'period': 'Período en el que se evaluará el cumplimiento.',
            'weight': 'Importancia de esta meta en el resultado total. La suma por cargo y período no puede superar 100%.',
            'validity': 'Las metas inactivas se conservan en el historial, pero no se consideran en el cálculo.',
            'target_value': 'Cantidad que se espera alcanzar durante el período.',
            'unity': 'Unidad usada para interpretar el valor objetivo, por ejemplo: atenciones o actividades.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        position_ids = []
        if self.instance.pk:
            grouped_goals = (
                Goal.objects.filter(group_id=self.instance.group_id)
                if self.instance.group_id
                else Goal.objects.filter(pk=self.instance.pk)
            )
            position_ids = list(grouped_goals.values_list('position_id', flat=True))
            self.fields['positions'].initial = position_ids
        self.fields['positions'].queryset = Position.objects.filter(
            Q(validity=True, deleted_at__isnull=True) | Q(pk__in=position_ids)
        ).order_by('name')
        active_measuring = Measuring.objects.filter(
            validity=True,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            active_measuring = active_measuring | Measuring.objects.filter(
                pk=self.instance.measuring_id
            )
        self.fields['measuring'].queryset = active_measuring.distinct()
        self.fields['period'].queryset = self.fields['period'].queryset.filter(
            deleted_at__isnull=True,
        )

    def clean(self):
        cleaned_data = super().clean()
        positions = cleaned_data.get('positions')
        measuring = cleaned_data.get('measuring')
        period = cleaned_data.get('period')
        weight = cleaned_data.get('weight')

        if not positions or not measuring or not period or weight is None:
            return cleaned_data

        if self.instance.pk:
            grouped_goals = (
                Goal.objects.filter(group_id=self.instance.group_id)
                if self.instance.group_id
                else Goal.objects.filter(pk=self.instance.pk)
            )
        else:
            grouped_goals = Goal.objects.none()

        for position in positions:
            existing_goals = Goal.objects.filter(
                position=position,
                measuring=measuring,
                period=period,
                deleted_at__isnull=True,
            ).exclude(pk__in=grouped_goals.values('pk'))
            if existing_goals.exists():
                self.add_error(
                    'positions',
                    (
                        f'El cargo "{position.name}" ya tiene una meta para '
                        'este ítem y período.'
                    ),
                )
                continue

            existing_weight = sum(
                Goal.objects.filter(
                    position=position,
                    period=period,
                    deleted_at__isnull=True,
                ).exclude(pk__in=grouped_goals.values('pk')).values_list('weight', flat=True)
            )
            if existing_weight + weight > 100:
                self.add_error(
                    'weight',
                    (
                        f'La ponderación total del cargo "{position.name}" '
                        'superaría el 100% en este período.'
                    ),
                )

        return cleaned_data

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if weight is None or weight < 0 or weight > 100:
            raise forms.ValidationError('El ponderador debe estar entre 0 y 100%.')
        return weight

    def clean_target_value(self):
        target = self.cleaned_data.get('target_value')
        if target is None or target <= 0:
            raise forms.ValidationError('La meta debe ser mayor que 0.')
        return target

    def clean_unity(self):
        unity = (self.cleaned_data.get('unity') or '').strip()
        if not unity:
            raise forms.ValidationError('Debe indicar la unidad de medida.')
        return unity


class PeriodForm(forms.ModelForm):
    class Meta:
        model = Period
        fields = [
            'start_date',
            'end_date',
            'status',
            'minimum_threshold',
            'maximum_computable_days',
            'version_parameter',
            'semaphore',
        ]
        widgets = {
            'start_date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'autocomplete': 'off',
                }
            ),
            'end_date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'autocomplete': 'off',
                }
            ),
            'status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'minimum_threshold': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0, 'step': 1}
            ),
            'maximum_computable_days': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1, 'readonly': True}
            ),
            'version_parameter': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: 2026',
                }
            ),
            'semaphore': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: SGR',
                }
            ),
        }
        labels = {
            'start_date': 'Fecha de inicio',
            'end_date': 'Fecha de término',
            'status': 'Período activo',
            'minimum_threshold': 'Umbral mínimo',
            'maximum_computable_days': 'Máximo de días computables',
            'version_parameter': 'Versión del parámetro',
            'semaphore': 'Parámetro del semáforo',
        }
        help_texts = {
            'start_date': 'Primer día incluido en el período de medición.',
            'end_date': 'Último día incluido. No puede ser anterior a la fecha de inicio.',
            'status': 'El período activo se usa para calcular el avance y el semáforo.',
            'minimum_threshold': 'Valor mínimo usado por la configuración del período.',
            'maximum_computable_days': 'Se calcula automáticamente contando la fecha de inicio y la de término.',
            'version_parameter': 'Etiqueta para identificar la versión de esta configuración.',
            'semaphore': 'Referencia de configuración del semáforo para este período.',
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        minimum_threshold = cleaned_data.get('minimum_threshold')

        if minimum_threshold is not None and minimum_threshold < 0:
            self.add_error(
                'minimum_threshold',
                'El umbral mínimo no puede ser negativo.',
            )
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'La fecha de término no puede ser anterior a la de inicio.')
        elif start_date and end_date:
            cleaned_data['maximum_computable_days'] = (end_date - start_date).days + 1

        return cleaned_data

    def clean_version_parameter(self):
        value = (self.cleaned_data.get('version_parameter') or '').strip()
        if not value:
            raise forms.ValidationError('Debe indicar la versión del parámetro.')
        return value

    def clean_semaphore(self):
        value = (self.cleaned_data.get('semaphore') or '').strip()
        if not value:
            raise forms.ValidationError('Debe indicar el parámetro del semáforo.')
        return value

    def save(self, commit=True):
        period = super().save(commit=False)
        period_days = (period.end_date - period.start_date).days + 1
        period.computable_days = period_days
        period.maximum_computable_days = period_days
        if commit:
            period.save()
            self.save_m2m()
        return period
