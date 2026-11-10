import logging
import secrets
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db.models import F
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import (
    PasswordRecoveryCodeForm,
    PasswordRecoveryRequestForm,
    PasswordRecoverySetPasswordForm,
)
from .models import PasswordRecoveryCode

logger = logging.getLogger(__name__)
MAX_CODE_ATTEMPTS = 5
RECOVERY_USER_SESSION_KEY = 'password_recovery_user_id'
RECOVERY_CODE_SESSION_KEY = 'password_recovery_code_id'


def password_recovery_request(request):
    form = PasswordRecoveryRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        users = get_user_model().objects.filter(
            email__iexact=email,
            is_active=True,
        )
        user = users.first() if users.count() == 1 else None
        request.session.pop(RECOVERY_USER_SESSION_KEY, None)
        request.session.pop(RECOVERY_CODE_SESSION_KEY, None)
        if user is not None:
            now = timezone.now()
            code = f'{secrets.randbelow(1_000_000):06d}'
            recovery_code = PasswordRecoveryCode.objects.create(
                user=user,
                code_hash=make_password(code),
                expires_at=now + timedelta(
                    seconds=settings.PASSWORD_RESET_CODE_TIMEOUT
                ),
            )
            PasswordRecoveryCode.objects.filter(
                user=user,
                used_at__isnull=True,
            ).exclude(pk=recovery_code.pk).update(used_at=now)
            try:
                sent = send_mail(
                    'Código de recuperación de contraseña - SGR',
                    (
                        f'Hola {user.get_full_name() or user.get_username()},\n\n'
                        f'Tu código de recuperación es: {code}\n'
                        f'El código vence en '
                        f'{settings.PASSWORD_RESET_CODE_TIMEOUT // 60} minutos '
                        'y solo puede utilizarse una vez.\n\n'
                        'Si no solicitaste este cambio, ignora este mensaje.'
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            except (OSError, SMTPException):
                recovery_code.delete()
                logger.exception(
                    'No se pudo enviar el código de recuperación de contraseña.'
                )
                messages.error(
                    request,
                    'No fue posible enviar el correo de recuperación. '
                    'Inténtalo nuevamente más tarde.',
                )
                return render(
                    request,
                    'registration/password_recovery_request.html',
                    {'form': form},
                    status=503,
                )
            if sent != 1:
                recovery_code.delete()
                logger.error('El backend de correo no confirmó el envío del código.')
                messages.error(
                    request,
                    'No fue posible enviar el correo de recuperación. '
                    'Inténtalo nuevamente más tarde.',
                )
                return render(
                    request,
                    'registration/password_recovery_request.html',
                    {'form': form},
                    status=503,
                )
            request.session[RECOVERY_USER_SESSION_KEY] = user.pk
        return redirect('password_recovery_sent')
    return render(
        request,
        'registration/password_recovery_request.html',
        {'form': form},
    )


def password_recovery_sent(request):
    return render(request, 'registration/password_recovery_sent.html')


def password_recovery_verify(request):
    user_id = request.session.get(RECOVERY_USER_SESSION_KEY)
    user = get_user_model().objects.filter(
        pk=user_id,
        is_active=True,
    ).first()
    if user is None:
        messages.error(
            request,
            'La solicitud venció o no está disponible. Solicita un nuevo código.',
        )
        return redirect('password_recovery_request')

    form = PasswordRecoveryCodeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        recovery_code = PasswordRecoveryCode.objects.filter(
            user=user,
            used_at__isnull=True,
        ).first()
        if (
            recovery_code is None
            or recovery_code.expires_at <= timezone.now()
            or recovery_code.attempts >= MAX_CODE_ATTEMPTS
        ):
            if recovery_code is not None:
                recovery_code.used_at = timezone.now()
                recovery_code.save(update_fields=['used_at'])
            request.session.pop(RECOVERY_USER_SESSION_KEY, None)
            messages.error(
                request,
                'El código venció o superó el límite de intentos. Solicita uno nuevo.',
            )
            return redirect('password_recovery_request')

        PasswordRecoveryCode.objects.filter(pk=recovery_code.pk).update(
            attempts=F('attempts') + 1
        )
        recovery_code.refresh_from_db(fields=['attempts'])
        if not check_password(form.cleaned_data['code'], recovery_code.code_hash):
            if recovery_code.attempts >= MAX_CODE_ATTEMPTS:
                recovery_code.used_at = timezone.now()
                recovery_code.save(update_fields=['used_at'])
                request.session.pop(RECOVERY_USER_SESSION_KEY, None)
                messages.error(
                    request,
                    'Se alcanzó el máximo de intentos. Solicita un nuevo código.',
                )
                return redirect('password_recovery_request')
            form.add_error('code', 'El código ingresado no es correcto.')
        else:
            request.session[RECOVERY_CODE_SESSION_KEY] = recovery_code.pk
            return redirect('password_recovery_set_password')

    return render(
        request,
        'registration/password_recovery_verify.html',
        {'form': form},
    )


def password_recovery_set_password(request):
    user_id = request.session.get(RECOVERY_USER_SESSION_KEY)
    code_id = request.session.get(RECOVERY_CODE_SESSION_KEY)
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    recovery_code = PasswordRecoveryCode.objects.filter(
        pk=code_id,
        user=user,
        used_at__isnull=True,
    ).first() if user is not None else None
    if (
        user is None
        or recovery_code is None
        or recovery_code.expires_at <= timezone.now()
        or recovery_code.attempts > MAX_CODE_ATTEMPTS
    ):
        request.session.pop(RECOVERY_USER_SESSION_KEY, None)
        request.session.pop(RECOVERY_CODE_SESSION_KEY, None)
        messages.error(
            request,
            'La verificación venció. Solicita un nuevo código de recuperación.',
        )
        return redirect('password_recovery_request')

    form = PasswordRecoverySetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        recovery_code.used_at = timezone.now()
        recovery_code.save(update_fields=['used_at'])
        if request.user.is_authenticated and request.user.pk == user.pk:
            update_session_auth_hash(request, user)
        request.session.pop(RECOVERY_USER_SESSION_KEY, None)
        request.session.pop(RECOVERY_CODE_SESSION_KEY, None)
        messages.success(request, 'Tu contraseña se actualizó correctamente.')
        return redirect('password_reset_complete')
    return render(
        request,
        'registration/password_recovery_set_password.html',
        {'form': form},
    )
