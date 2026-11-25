import unicodedata
import uuid

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import NeighborhoodMember, OrganizationLeader


def suggested_username(names, lastnames):
    value = f'{names[:1]}.{lastnames.split()[0] if lastnames.split() else ""}'.lower()
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).replace(' ', '')


class MemberProfileForm(forms.ModelForm):
    class Meta:
        model = NeighborhoodMember
        fields = ['names', 'lastnames', 'email', 'phone']
        widgets = {field: forms.TextInput(attrs={'class': 'form-control'}) for field in fields}
        widgets['email'] = forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'})

    def clean_names(self):
        return self.cleaned_data['names'].strip()

    def clean_lastnames(self):
        return self.cleaned_data['lastnames'].strip()


class MemberForm(MemberProfileForm):
    submission_token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    create_access = forms.BooleanField(required=False, label='Crear una cuenta para este vecino', help_text='Solo necesita acceso si consultará la junta o enviará cartas como dirigente.')
    username = forms.CharField(required=False, max_length=150, label='Nombre de usuario', help_text='Si lo dejas vacío, se propone inicial.apellido. Se comprobará que esté disponible.')
    password = forms.CharField(required=False, label='Contraseña inicial', widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    class Meta(MemberProfileForm.Meta):
        fields = MemberProfileForm.Meta.fields + ['is_active']

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        if self.instance.pk:
            self.fields.pop('submission_token')
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-control')
        if self.instance.user_id:
            for key in ('create_access', 'username', 'password'):
                self.fields.pop(key)

    def clean(self):
        data = super().clean()
        if self.instance.pk == self.actor.pk and data.get('is_active') is False:
            self.add_error('is_active', 'Conserva activa tu cuenta de administración de la junta.')
        if data.get('create_access'):
            username = data.get('username') or suggested_username(data.get('names', ''), data.get('lastnames', ''))
            if not username or User.objects.filter(username__iexact=username).exists():
                self.add_error('username', 'Este usuario ya existe. Elige otro nombre; no se vincularán cuentas ajenas.')
            else:
                try:
                    User._meta.get_field('username').run_validators(username)
                except ValidationError as error:
                    self.add_error('username', error)
                data['username'] = username
            if not data.get('password'):
                self.add_error('password', 'Define una contraseña inicial para crear el acceso.')
            else:
                try:
                    validate_password(data['password'], User(username=username, first_name=data.get('names', ''), last_name=data.get('lastnames', '')))
                except ValidationError as error:
                    self.add_error('password', error)
        return data


class BoardForm(forms.Form):
    president = forms.ModelChoiceField(queryset=NeighborhoodMember.objects.none(), required=False, label='Presidente')
    secretary = forms.ModelChoiceField(queryset=NeighborhoodMember.objects.none(), required=False, label='Secretario')
    treasurer = forms.ModelChoiceField(queryset=NeighborhoodMember.objects.none(), required=False, label='Tesorero')
    POSITIONS = {'president': OrganizationLeader.BoardPosition.PRESIDENT,
                 'secretary': OrganizationLeader.BoardPosition.SECRETARY,
                 'treasurer': OrganizationLeader.BoardPosition.TREASURER}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        members = organization.neighbors.filter(is_active=True, deleted_at__isnull=True).order_by('lastnames', 'names')
        existing = {leader.board_position: leader.member_id for leader in organization.leaders.filter(board_position__isnull=False, deleted_at__isnull=True)}
        for field, position in self.POSITIONS.items():
            self.fields[field].queryset = members
            self.fields[field].label_from_instance = lambda member: member.full_name
            self.fields[field].widget.attrs['class'] = 'form-select'
            self.fields[field].empty_label = 'Sin asignar'
            self.initial[field] = existing.get(position)

    def clean(self):
        data = super().clean()
        assigned = [member.pk for member in data.values() if member]
        if len(assigned) != len(set(assigned)):
            raise ValidationError('Cada cargo debe asignarse a un vecino distinto.')
        return data


class CommunityLetterForm(forms.Form):
    submission_token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    subject = forms.CharField(label='¿Qué solicita o informa la junta?', max_length=10000, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Describe la solicitud con la información necesaria para que la delegación pueda responder.'}))
    contact_phone = forms.CharField(label='Teléfono de contacto (opcional)', required=False, max_length=30, widget=forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'tel'}))
    activity_date = forms.CharField(label='Fecha de la actividad (opcional)', required=False, max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Solo si tu solicitud se relaciona con una actividad.'}))
