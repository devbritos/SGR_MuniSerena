import re
import tempfile
from io import BytesIO
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from personal.models import Delegation, Functionary, Position

from .models import (
    CommunityEvent,
    DelegationPerson,
    EventRegistration,
)
from .validators import normalize_chilean_rut


class EventRegistrationWorkflowTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            code='EVENT-01',
            name='Delegación eventos',
            field='URBANO',
        )
        self.event = CommunityEvent.objects.create(
            delegation=self.delegation,
            title='Navidad en la delegación',
            description='Actividad familiar.',
            what_to_expect='Juegos, música y entrega de regalos.',
            starts_at=timezone.now() + timedelta(days=14),
            registration_deadline=timezone.now() + timedelta(days=7),
            location='Plaza del sector',
            status=CommunityEvent.Status.PUBLISHED,
        )

    def _registration_data(self, **overrides):
        data = {
            'full_name': 'María Pérez',
            'rut': '12.345.678-5',
            'email': 'MARIA@example.com',
            'phone': '+56 9 1234 5678',
            'adult_attends': 'on',
            'consent': 'on',
            'children-TOTAL_FORMS': '0',
            'children-INITIAL_FORMS': '0',
            'children-MIN_NUM_FORMS': '0',
            'children-MAX_NUM_FORMS': '10',
        }
        data.update(overrides)
        return data

    def _register(self, data=None):
        return self.client.post(
            reverse('events:public_register', args=[self.event.pk]),
            data or self._registration_data(),
        )

    def _verify_email(self, message):
        match = re.search(
            r'http://testserver(/eventos/verificar-correo/[^/\s]+/)',
            message.body,
        )
        self.assertIsNotNone(match)
        verify_url = match.group(1)
        self.assertEqual(self.client.get(verify_url).status_code, 200)
        return self.client.post(verify_url)

    def test_public_registration_verifies_email_and_links_registered_guardian(self):
        guardian = DelegationPerson.objects.create(
            delegation=self.delegation,
            full_name='María Pérez',
            rut='12345678-5',
            email='maria@example.com',
            phone='+56912345678',
        )
        response = self._register(self._registration_data(
            **{
                'children-TOTAL_FORMS': '2',
                'children-INITIAL_FORMS': '0',
                'children-0-full_name': 'Sofía Pérez',
                'children-1-full_name': 'Tomás Pérez',
            }
        ))

        self.assertEqual(response.status_code, 200)
        registration = EventRegistration.objects.get()
        self.assertEqual(registration.status, EventRegistration.Status.PENDING_EMAIL)
        self.assertEqual(registration.rut, '12345678-5')
        self.assertEqual(registration.email, 'maria@example.com')
        self.assertEqual(registration.children.count(), 2)
        self.assertEqual(len(mail.outbox), 1)

        response = self._verify_email(mail.outbox[0])

        self.assertEqual(response.status_code, 200)
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(registration.guardian_person, guardian)
        self.assertEqual(registration.attendee_count, 3)

    def test_minor_registration_without_roster_match_waits_for_staff_review(self):
        response = self._register(self._registration_data(
            **{
                'children-TOTAL_FORMS': '1',
                'children-INITIAL_FORMS': '0',
                'children-0-full_name': 'Sofía Pérez',
            }
        ))
        self.assertEqual(response.status_code, 200)

        self._verify_email(mail.outbox[0])

        registration = EventRegistration.objects.get()
        self.assertEqual(
            registration.status,
            EventRegistration.Status.PENDING_REVIEW,
        )
        self.assertIsNone(registration.guardian_person)

    def test_adult_registration_confirms_without_padrón_match(self):
        self._register()
        self._verify_email(mail.outbox[0])

        registration = EventRegistration.objects.get()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)
        self.assertIsNone(registration.guardian_person)

    def test_invalid_rut_does_not_create_registration_or_send_email(self):
        response = self._register(self._registration_data(rut='12.345.678-9'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EventRegistration.objects.exists())
        self.assertEqual(mail.outbox, [])
        self.assertContains(response, 'dígito verificador')

    def test_invalid_phone_does_not_create_registration(self):
        response = self._register(self._registration_data(phone='++++++++'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EventRegistration.objects.exists())
        self.assertEqual(mail.outbox, [])
        self.assertContains(response, 'teléfono con formato válido')

    def test_expired_email_link_can_be_resent_without_duplicate_registration(self):
        self._register()
        registration = EventRegistration.objects.get()
        original_token_hash = registration.email_verification_token_hash
        registration.email_verification_sent_at = (
            timezone.now() - timedelta(hours=25)
        )
        registration.save(update_fields=[
            'email_verification_sent_at',
            'updated_at',
        ])

        self._register()

        self.assertEqual(EventRegistration.objects.count(), 1)
        registration.refresh_from_db()
        self.assertNotEqual(
            registration.email_verification_token_hash,
            original_token_hash,
        )
        self.assertEqual(len(mail.outbox), 2)
        self._verify_email(mail.outbox[-1])
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)

    def test_adult_cannot_submit_without_anyone_attending(self):
        data = self._registration_data(adult_attends='')

        response = self._register(data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EventRegistration.objects.exists())
        self.assertContains(response, 'al menos un menor')

    def test_pending_email_registration_reserves_event_capacity(self):
        self.event.capacity = 1
        self.event.save(update_fields=['capacity', 'updated_at'])
        first = self._register()
        second = self._register(self._registration_data(
            rut='9.876.543-3',
            email='otra@example.com',
        ))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(EventRegistration.objects.count(), 1)
        self.assertContains(second, 'No hay suficientes cupos')

    def test_public_event_list_only_shows_published_future_events(self):
        CommunityEvent.objects.create(
            delegation=self.delegation,
            title='Evento en borrador',
            description='No público',
            starts_at=timezone.now() + timedelta(days=20),
            location='Lugar',
            status=CommunityEvent.Status.DRAFT,
        )
        informational_event = CommunityEvent.objects.create(
            delegation=self.delegation,
            title='Corte de tránsito',
            description='Información para la comunidad.',
            starts_at=timezone.now() + timedelta(days=2),
            registration_deadline=timezone.now() - timedelta(days=1),
            location='Avenida principal',
            event_type=CommunityEvent.EventType.INFORMATION,
            status=CommunityEvent.Status.PUBLISHED,
        )

        response = self.client.get(reverse('events:public_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)
        self.assertContains(response, 'Ver detalles')
        self.assertContains(response, 'Juegos, música y entrega de regalos.')
        self.assertNotContains(response, 'id="sidebarMenuToggle"')
        self.assertNotContains(response, 'id="sidebarMenu"')
        self.assertContains(response, informational_event.title)
        self.assertContains(response, 'Solo informativo')
        self.assertNotContains(
            response,
            reverse('events:public_register', args=[informational_event.pk]),
        )
        self.assertContains(response, 'eventDetailsModal')
        self.assertNotContains(response, 'Evento en borrador')

    def test_informational_event_cannot_be_registered_directly(self):
        event = CommunityEvent.objects.create(
            delegation=self.delegation,
            title='Aviso comunitario',
            description='Solo información.',
            starts_at=timezone.now() + timedelta(days=2),
            location='Sede',
            event_type=CommunityEvent.EventType.INFORMATION,
            status=CommunityEvent.Status.PUBLISHED,
        )

        response = self.client.get(
            reverse('events:public_register', args=[event.pk]),
        )

        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse('events:public_register', args=[event.pk]),
            {},
        )
        self.assertEqual(response.status_code, 404)

    def test_public_events_are_not_linked_from_the_login_page(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Ver eventos e inscribirme')

    def test_public_registration_page_hides_application_menu(self):
        response = self.client.get(
            reverse('events:public_register', args=[self.event.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="sidebarMenuToggle"')
        self.assertNotContains(response, 'id="sidebarMenu"')


class ChileanRutValidationTests(TestCase):
    def test_normalizes_valid_rut(self):
        self.assertEqual(normalize_chilean_rut('12.345.678-5'), '12345678-5')
        self.assertEqual(normalize_chilean_rut('100008-k'), '100008-K')

    def test_rejects_invalid_check_digit(self):
        with self.assertRaisesMessage(ValidationError, 'dígito verificador'):
            normalize_chilean_rut('12.345.678-9')


class EventImageValidationTests(TestCase):
    def test_event_image_validator_rejects_non_image_upload(self):
        upload = SimpleUploadedFile(
            'evento.jpg',
            b'not an image',
            content_type='image/jpeg',
        )

        with self.assertRaisesMessage(ValidationError, 'Selecciona una imagen'):
            CommunityEvent._meta.get_field('image').run_validators(upload)


class EventManagementTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            code='EVENT-02',
            name='Delegación gestora',
            field='RURAL',
        )
        user = User.objects.create_user(username='gestor_eventos')
        Functionary.objects.create(
            user=user,
            delegation=self.delegation,
            position=Position.objects.create(name='Gestor de eventos'),
            names='Gestor',
            lastnames='Eventos',
        )
        self.client.force_login(user)

    def test_event_management_keeps_application_menu(self):
        response = self.client.get(reverse('events:management_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebarMenuToggle"')
        self.assertContains(response, 'id="sidebarMenu"')

    def test_functionary_can_create_a_delegation_event(self):
        start = timezone.localtime(timezone.now() + timedelta(days=30))
        end = start + timedelta(hours=3)
        deadline = start - timedelta(days=2)

        response = self.client.post(
            reverse('events:event_create'),
            {
                'delegation': str(self.delegation.pk),
                'title': 'Fiesta de Navidad',
                'event_type': CommunityEvent.EventType.REGISTRATION,
                'description': 'Celebración familiar.',
                'starts_at': start.strftime('%Y-%m-%dT%H:%M'),
                'ends_at': end.strftime('%Y-%m-%dT%H:%M'),
                'location': 'Sede vecinal',
                'capacity': '80',
                'registration_deadline': deadline.strftime('%Y-%m-%dT%H:%M'),
                'status': CommunityEvent.Status.PUBLISHED,
            },
        )

        self.assertRedirects(response, reverse('events:management_list'))
        event = CommunityEvent.objects.get()
        self.assertEqual(event.title, 'Fiesta de Navidad')
        self.assertEqual(event.delegation, self.delegation)
        self.assertEqual(event.status, CommunityEvent.Status.PUBLISHED)

    def test_functionary_can_create_an_information_only_event(self):
        start = timezone.localtime(timezone.now() + timedelta(days=30))

        response = self.client.post(
            reverse('events:event_create'),
            {
                'delegation': str(self.delegation.pk),
                'title': 'Aviso de mantención',
                'event_type': CommunityEvent.EventType.INFORMATION,
                'description': 'Se realizarán trabajos en la plaza.',
                'starts_at': start.strftime('%Y-%m-%dT%H:%M'),
                'location': 'Plaza de la delegación',
                'status': CommunityEvent.Status.PUBLISHED,
            },
        )

        self.assertRedirects(response, reverse('events:management_list'))
        event = CommunityEvent.objects.get()
        self.assertEqual(
            event.event_type,
            CommunityEvent.EventType.INFORMATION,
        )
        public_response = self.client.get(reverse('events:public_list'))
        self.assertContains(public_response, event.title)
        self.assertNotContains(
            public_response,
            reverse('events:public_register', args=[event.pk]),
        )

    def test_functionary_can_create_event_with_cover_image_and_program(self):
        start = timezone.localtime(timezone.now() + timedelta(days=30))
        image_bytes = BytesIO()
        Image.new('RGB', (640, 480), color='red').save(image_bytes, format='JPEG')
        image = SimpleUploadedFile(
            'navidad.jpg',
            image_bytes.getvalue(),
            content_type='image/jpeg',
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('events:event_create'),
                    {
                        'delegation': str(self.delegation.pk),
                        'title': 'Fiesta de Navidad',
                        'event_type': CommunityEvent.EventType.REGISTRATION,
                        'description': 'Celebración familiar.',
                        'what_to_expect': 'Juegos, música y regalos.',
                        'starts_at': start.strftime('%Y-%m-%dT%H:%M'),
                        'location': 'Sede vecinal',
                        'image': image,
                        'capacity': '80',
                        'status': CommunityEvent.Status.PUBLISHED,
                    },
                )

                self.assertRedirects(
                    response,
                    reverse('events:management_list'),
                )
                event = CommunityEvent.objects.get()
                self.assertEqual(
                    event.what_to_expect,
                    'Juegos, música y regalos.',
                )
                self.assertTrue(event.image.name.startswith('event_images/'))
                self.assertTrue(event.image.storage.exists(event.image.name))
                public_response = self.client.get(reverse('events:public_list'))
                self.assertContains(public_response, event.image.url)

    def test_functionary_cannot_manage_another_delegations_event(self):
        other_delegation = Delegation.objects.create(
            code='EVENT-03',
            name='Otra delegación',
            field='URBANO',
        )
        event = CommunityEvent.objects.create(
            delegation=other_delegation,
            title='Evento privado',
            description='No autorizado',
            starts_at=timezone.now() + timedelta(days=30),
            location='Lugar',
        )

        response = self.client.get(
            reverse('events:event_update', args=[event.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_pending_guardian_review_requires_a_padrón_record(self):
        event = CommunityEvent.objects.create(
            delegation=self.delegation,
            title='Evento para menores',
            description='Inscripción',
            starts_at=timezone.now() + timedelta(days=30),
            location='Lugar',
        )
        registration = EventRegistration.objects.create(
            event=event,
            full_name='María Pérez',
            rut='12345678-5',
            email='maria@example.com',
            phone='+56 9 1234 5678',
            adult_attends=False,
            status=EventRegistration.Status.PENDING_REVIEW,
            email_verification_sent_at=timezone.now(),
            email_verified_at=timezone.now(),
            consented_at=timezone.now(),
        )
        registration.children.create(full_name='Sofía Pérez')

        response = self.client.post(
            reverse('events:registration_review', args=[registration.pk]),
            {'decision': 'confirm'},
        )

        self.assertEqual(
            response.url,
            f"{reverse('events:person_create')}?registration={registration.pk}",
        )
        registration.refresh_from_db()
        self.assertEqual(
            registration.status,
            EventRegistration.Status.PENDING_REVIEW,
        )

        person_url = response.url
        response = self.client.get(person_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['rut'], '12345678-5')

        response = self.client.post(
            person_url,
            {
                'full_name': 'María Pérez',
                'rut': '12.345.678-5',
                'email': 'maria@example.com',
                'phone': '+56 9 1234 5678',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('events:registration_list'))
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(registration.guardian_person.full_name, 'María Pérez')
