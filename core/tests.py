import re

from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from .models import PasswordRecoveryCode


class PaginationTemplateTests(SimpleTestCase):
    def test_paginator_shows_page_one_even_when_results_fit_on_one_page(self):
        request = RequestFactory().get('/listado/')
        page = Paginator(['único resultado'], 10).get_page(1)

        rendered = render_to_string(
            '_pagination.html',
            {
                'request': request,
                'page_obj': page,
                'is_paginated': page.has_other_pages(),
                'query_params': '',
            },
        )

        self.assertIn('Mostrando <strong>1–1</strong>', rendered)
        self.assertIn('de <strong>1</strong> resultados', rendered)
        self.assertIn('aria-current="page"', rendered)
        self.assertIn('<span class="page-link">1', rendered)
        self.assertIn('aria-disabled="true"', rendered)

    def test_paginator_is_hidden_when_list_is_empty(self):
        request = RequestFactory().get('/listado/')
        page = Paginator([], 10).get_page(1)

        rendered = render_to_string(
            '_pagination.html',
            {
                'request': request,
                'page_obj': page,
                'is_paginated': page.has_other_pages(),
                'query_params': '',
            },
        )

        self.assertNotIn('<nav', rendered)

    def test_paginator_shows_page_window_and_preserves_filters(self):
        request = RequestFactory().get(
            '/listado/',
            {'q': 'solicitud', 'state': 'activo', 'page': '3'},
        )
        query_params = request.GET.copy()
        query_params.pop('page', None)
        page = Paginator(range(51), 10).get_page(request.GET.get('page'))

        rendered = render_to_string(
            '_pagination.html',
            {
                'request': request,
                'page_obj': page,
                'is_paginated': page.has_other_pages(),
                'query_params': query_params.urlencode(),
            },
        )

        self.assertIn('Mostrando <strong>21–30</strong>', rendered)
        self.assertIn('de <strong>51</strong> resultados', rendered)
        self.assertIn('aria-current="page"', rendered)
        self.assertIn('page=1', rendered)
        self.assertIn('page=2', rendered)
        self.assertIn('page=4', rendered)
        self.assertIn('page=6', rendered)
        self.assertIn('q=solicitud&amp;state=activo&amp;page=', rendered)

    def test_paginator_disables_previous_and_next_at_boundaries(self):
        request = RequestFactory().get('/listado/')
        for page_number, disabled_label in ((1, 'Anterior'), (2, 'Siguiente')):
            with self.subTest(page_number=page_number):
                page = Paginator(range(20), 10).get_page(page_number)
                rendered = render_to_string(
                    '_pagination.html',
                    {
                        'request': request,
                        'page_obj': page,
                        'is_paginated': page.has_other_pages(),
                        'query_params': '',
                    },
                )
                self.assertIn(f'>{disabled_label}</span>', rendered)


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
        user.refresh_from_db()
        self.assertTrue(user.check_password('New-secure-test-password-2026!'))


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='sgr@example.com',
)
class AuthenticationAndCodeRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='correo_user',
            email='correo_user@example.com',
            password='Old-test-password-2026!',
        )

    def test_login_accepts_username_and_email(self):
        for identifier in (self.user.username, self.user.email):
            with self.subTest(identifier=identifier):
                response = self.client.post(
                    reverse('login'),
                    {
                        'username': identifier,
                        'password': 'Old-test-password-2026!',
                    },
                )
                self.assertEqual(response.status_code, 302)
                self.client.logout()

    def test_code_recovery_verifies_code_and_changes_password(self):
        response = self.client.post(
            reverse('password_recovery_request'),
            {'email': self.user.email},
        )
        self.assertRedirects(response, reverse('password_recovery_sent'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        code = re.search(r'código de recuperación es: (\d{6})', mail.outbox[0].body)
        self.assertIsNotNone(code)

        response = self.client.post(
            reverse('password_recovery_verify'),
            {'code': code.group(1)},
        )
        self.assertRedirects(response, reverse('password_recovery_set_password'))
        response = self.client.post(
            reverse('password_recovery_set_password'),
            {
                'new_password1': 'Nuevo-pass-908!',
                'new_password2': 'Nuevo-pass-908!',
            },
        )
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Nuevo-pass-908!'))
        recovery_code = PasswordRecoveryCode.objects.get(user=self.user)
        self.assertIsNotNone(recovery_code.used_at)

    def test_expired_code_cannot_be_used(self):
        self.client.post(
            reverse('password_recovery_request'),
            {'email': self.user.email},
        )
        recovery_code = PasswordRecoveryCode.objects.get(user=self.user)
        recovery_code.expires_at = timezone.now() - timedelta(seconds=1)
        recovery_code.save(update_fields=['expires_at'])

        response = self.client.post(
            reverse('password_recovery_verify'),
            {'code': '123456'},
        )
        self.assertRedirects(response, reverse('password_recovery_request'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-test-password-2026!'))

    @patch('core.auth_views.send_mail', return_value=0)
    def test_mail_failure_does_not_show_a_success_response(self, send_mail_mock):
        response = self.client.post(
            reverse('password_recovery_request'),
            {'email': self.user.email},
        )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(
            PasswordRecoveryCode.objects.filter(user=self.user).exists()
        )
        self.assertContains(response, 'No fue posible enviar', status_code=503)
