import re

from django.test import TestCase
from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.urls import reverse


@override_settings(DEBUG=False)
class ErrorPageTests(TestCase):
    def test_not_found_uses_custom_page_and_back_button(self):
        response = self.client.get('/this-page-does-not-exist/')

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, '404.html')
        self.assertContains(response, 'Página no encontrada', status_code=404)
        self.assertContains(response, 'Volver a la página anterior', status_code=404)
        self.assertContains(response, 'sweetalert2', status_code=404)

    def test_forbidden_uses_custom_page_and_back_button(self):
        user = User.objects.create_user(username='unauthorized_user')
        self.client.force_login(user)

        response = self.client.get('/activities/evidencias/1/validar/')

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')
        self.assertContains(response, 'Acceso denegado', status_code=403)
        self.assertContains(response, 'Volver a la página anterior', status_code=403)
        self.assertContains(response, 'sweetalert2', status_code=403)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='sgr@example.com',
)
class PasswordResetEmailTests(TestCase):
    def test_reset_email_link_changes_password(self):
        user = User.objects.create_user(
            username='email_user',
            email='email_user@example.com',
            password='old-test-password',
        )

        response = self.client.post(
            reverse('password_reset'),
            {'email': user.email},
        )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertEqual(mail.outbox[0].from_email, 'sgr@example.com')

        reset_link = re.search(
            r'/accounts/reset/([^/\s]+)/([^/\s]+)/',
            mail.outbox[0].body,
        )
        self.assertIsNotNone(reset_link)
        uidb64, token = reset_link.groups()

        response = self.client.get(
            reverse(
                'password_reset_confirm',
                kwargs={'uidb64': uidb64, 'token': token},
            )
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            response.url,
            {
                'new_password1': 'New-secure-test-password-2026!',
                'new_password2': 'New-secure-test-password-2026!',
            },
        )

        self.assertRedirects(response, reverse('password_reset_complete'))
        response = self.client.get(response.url)
        self.assertTemplateUsed(response, 'registration/password_reset_complete.html')
        self.assertContains(response, 'Contraseña restablecida')
        self.assertContains(response, reverse('login'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('New-secure-test-password-2026!'))
