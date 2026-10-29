from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
class UsernameOrEmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Usuario o correo electrónico',
        widget=forms.TextInput(attrs={'autofocus': True, 'class': 'form-control'}),
    )

    def clean(self):
        username_or_email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        if username_or_email and password:
            user_model = get_user_model()
            username = username_or_email
            if '@' in username_or_email:
                users = user_model.objects.filter(
                    email__iexact=username_or_email,
                    is_active=True,
                )
                if users.count() != 1:
                    raise self.get_invalid_login_error()
                username = users.get().get_username()
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class PasswordRecoveryRequestForm(forms.Form):
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autocomplete': 'email',
            'required': True,
        }),
    )


class PasswordRecoveryCodeForm(forms.Form):
    code = forms.RegexField(
        regex=r'^\d{6}$',
        label='Código de seis dígitos',
        error_messages={
            'invalid': 'Ingresa el código de seis dígitos recibido por correo.',
        },
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'maxlength': '6',
        }),
    )


class PasswordRecoverySetPasswordForm(SetPasswordForm):
    error_messages = {
        **SetPasswordForm.error_messages,
        'password_mismatch': 'Las contraseñas no coinciden.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = 'Nueva contraseña'
        self.fields['new_password2'].label = 'Confirmar nueva contraseña'
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
