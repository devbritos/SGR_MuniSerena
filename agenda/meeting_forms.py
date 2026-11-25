import uuid
from django import forms
from django.db.models import Q
from personal.models import Delegation, Functionary
from .models import Meeting, MeetingAgreement
from .forms import CommitmentForm


class MeetingForm(forms.ModelForm):
    creation_token = forms.UUIDField(widget=forms.HiddenInput)
    class Meta:
        model = Meeting
        fields = ['delegation', 'title', 'starts_at', 'location', 'participants', 'external_participants', 'status', 'notes']
        widgets = {'starts_at': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
                   'participants': forms.CheckboxSelectMultiple()}
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        fn = user.functionary
        self.initial.setdefault('creation_token', uuid.uuid4())
        self.initial.setdefault('delegation', fn.delegation_id)
        self.fields['delegation'].queryset = Delegation.objects.filter(state='ACTIVO', deleted_at__isnull=True)
        if self.instance.pk:
            self.fields['delegation'].queryset = Delegation.objects.filter(pk=self.instance.delegation_id)
            self.fields['delegation'].disabled = True
        elif not (user.is_staff or user.is_superuser or fn.has_global_scope):
            self.fields['delegation'].queryset = self.fields['delegation'].queryset.filter(pk=fn.delegation_id)
            self.fields['delegation'].disabled = True
        self.fixed_delegation = self.fields['delegation'].queryset.first() if self.fields['delegation'].disabled else None
        delegation_id = self.instance.delegation_id if self.instance.pk else self.initial.get('delegation')
        if self.is_bound and not self.fields['delegation'].disabled:
            delegation_id = self.data.get('delegation')
        self.fields['participants'].queryset = Functionary.objects.none()
        if delegation_id and str(delegation_id).isdigit():
            allowed = Q(is_active=True, deleted_at__isnull=True)
            if self.instance.pk:
                allowed |= Q(pk__in=self.instance.participants.values('pk'))
            self.fields['participants'].queryset = Functionary.objects.filter(allowed, delegation_id=delegation_id).order_by('names', 'lastnames')
        self.fields['starts_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S']
        for name, field in self.fields.items():
            if name != 'participants':
                field.widget.attrs['class'] = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            if isinstance(field.widget, forms.Textarea): field.widget.attrs['rows'] = 3

    @property
    def participant_catalog(self):
        qs = Functionary.objects.filter(is_active=True, deleted_at__isnull=True, delegation__in=self.fields['delegation'].queryset)
        result = {}
        for person in qs.order_by('names', 'lastnames').values('id', 'names', 'lastnames', 'delegation_id'):
            result.setdefault(str(person['delegation_id']), []).append({'id': person['id'], 'name': person['names'] + ' ' + person['lastnames']})
        return result


class AgreementForm(forms.ModelForm):
    class Meta:
        model = MeetingAgreement
        fields = ['description', 'responsible', 'due_date']
        widgets = {'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                   'responsible': forms.Select(attrs={'class': 'form-select'}),
                   'due_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'})}
    def __init__(self, *args, meeting, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = Q(is_active=True, deleted_at__isnull=True)
        if self.instance.pk: allowed |= Q(pk=self.instance.responsible_id)
        self.fields['responsible'].queryset = Functionary.objects.filter(allowed, delegation=meeting.delegation).order_by('names', 'lastnames')


class AgreementCommitmentForm(CommitmentForm):
    activity_id = None
    class Meta(CommitmentForm.Meta):
        fields = ['applic_name', 'territory', 'functionary', 'commitment_date', 'observation']
