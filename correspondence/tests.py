from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from personal.models import Delegation, Functionary, Position, Role, FunctionaryRole

from .models import OfficeLetter


class OfficeLetterWorkflowTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            code='CARTA-01',
            name='Delegación cartas',
            field='URBANO',
        )
        self.position = Position.objects.create(name='Gestor de seguimiento')
        self.user = User.objects.create_user(
            username='encargado_cartas',
            password='test-password',
        )
        self.functionary = Functionary.objects.create(
            user=self.user,
            delegation=self.delegation,
            position=self.position,
            names='Gestor',
            lastnames='Cartas',
        )
        self.client.force_login(self.user)

    def _letter_data(self, **overrides):
        data = {
            'delegation': str(self.delegation.pk),
            'received_at': date.today().isoformat(),
            'registry_number': '2026-001',
            'recipient': 'Alcaldesa',
            'sender': 'Organización vecinal',
            'contact_phone': '512123456',
            'subject': 'Solicitud de apoyo comunitario',
            'activity_date': '16 al 19/07',
            'responsible': str(self.functionary.pk),
            'state': OfficeLetter.State.IN_PROGRESS,
            'pronouncement': 'En revisión',
            'referred_to': 'Dirección municipal',
            'observation': 'Se solicitó respuesta al área.',
        }
        data.update(overrides)
        return data

    def test_functionary_registers_letter_with_follow_up_details(self):
        response = self.client.post(
            reverse('correspondence:letter_create'),
            self._letter_data(),
        )

        self.assertRedirects(response, reverse('correspondence:letter_list'))
        letter = OfficeLetter.objects.get()
        self.assertEqual(letter.delegation, self.delegation)
        self.assertEqual(letter.responsible, self.functionary)
        self.assertEqual(letter.registered_by, self.functionary)
        self.assertEqual(letter.activity_date, '16 al 19/07')
        self.assertEqual(letter.state, OfficeLetter.State.IN_PROGRESS)

    def test_letter_listing_filters_and_exports_all_matching_rows(self):
        first = OfficeLetter.objects.create(
            delegation=self.delegation,
            received_at=date.today(),
            registry_number='REG-100',
            recipient='Alcaldesa',
            sender='Junta de vecinos',
            subject='Solicitud de iluminación',
            responsible=self.functionary,
            registered_by=self.functionary,
        )
        other = OfficeLetter.objects.create(
            delegation=self.delegation,
            received_at=date.today() - timedelta(days=2),
            registry_number='REG-200',
            recipient='Alcaldesa',
            sender='Organización cultural',
            subject='Actividad cultural',
            responsible=self.functionary,
            registered_by=self.functionary,
            state=OfficeLetter.State.FINALIZED,
        )

        response = self.client.get(
            reverse('correspondence:letter_list'),
            {'search': 'iluminación', 'state': OfficeLetter.State.IN_PROGRESS},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['letters']), [first])
        self.assertNotContains(response, other.registry_number)

        export = self.client.get(
            reverse('correspondence:letter_list'),
            {'search': 'iluminación', 'export': 'xlsx'},
        )
        workbook = load_workbook(BytesIO(export.content), read_only=True)
        rows = list(workbook.active.values)
        workbook.close()
        self.assertEqual(export.status_code, 200)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], first.registry_number)

    def test_user_cannot_assign_letter_to_another_delegation(self):
        outside_delegation = Delegation.objects.create(
            code='CARTA-02',
            name='Otra delegación cartas',
            field='RURAL',
        )
        outside_functionary = Functionary.objects.create(
            delegation=outside_delegation,
            position=self.position,
            names='Otro',
            lastnames='Encargado',
        )

        response = self.client.post(
            reverse('correspondence:letter_create'),
            self._letter_data(responsible=str(outside_functionary.pk)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(OfficeLetter.objects.exists())
        self.assertIn('responsible', response.context['form'].errors)

    def test_global_admin_can_register_a_letter_for_another_delegation(self):
        admin_role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(
            functionary=self.functionary,
            role=admin_role,
        )
        outside_delegation = Delegation.objects.create(
            code='CARTA-04',
            name='Delegación administrada',
            field='RURAL',
        )
        outside_functionary = Functionary.objects.create(
            delegation=outside_delegation,
            position=self.position,
            names='Responsable',
            lastnames='Externo',
        )

        response = self.client.post(
            reverse('correspondence:letter_create'),
            self._letter_data(
                delegation=str(outside_delegation.pk),
                responsible=str(outside_functionary.pk),
            ),
        )

        self.assertRedirects(response, reverse('correspondence:letter_list'))
        letter = OfficeLetter.objects.get()
        self.assertEqual(letter.delegation, outside_delegation)
        self.assertEqual(letter.registered_by, self.functionary)

    def test_regular_functionary_only_sees_assigned_letters(self):
        other_user = User.objects.create_user(username='otro_encargado')
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=self.delegation,
            position=self.position,
            names='Otro',
            lastnames='Encargado',
        )
        own_letter = OfficeLetter.objects.create(
            delegation=self.delegation,
            received_at=date.today(),
            recipient='Alcaldesa',
            sender='Remitente propio',
            subject='Carta propia',
            responsible=self.functionary,
        )
        OfficeLetter.objects.create(
            delegation=self.delegation,
            received_at=date.today(),
            recipient='Alcaldesa',
            sender='Remitente ajeno',
            subject='Carta ajena',
            responsible=other_functionary,
        )

        response = self.client.get(reverse('correspondence:letter_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['letters']), [own_letter])
        self.assertContains(response, 'Remitente propio')
        self.assertNotContains(response, 'Remitente ajeno')

    def test_model_rejects_responsible_from_different_delegation(self):
        other_delegation = Delegation.objects.create(
            code='CARTA-03',
            name='Delegación incompatible',
            field='RURAL',
        )
        other_functionary = Functionary.objects.create(
            delegation=other_delegation,
            position=self.position,
            names='Incompatible',
            lastnames='Responsable',
        )
        letter = OfficeLetter(
            delegation=self.delegation,
            received_at=date.today(),
            recipient='Alcaldesa',
            sender='Remitente',
            subject='Carta incompatible',
            responsible=other_functionary,
        )

        with self.assertRaises(ValidationError) as error:
            letter.full_clean()
        self.assertIn('responsible', error.exception.message_dict)

    def test_search_filter_errors_are_shown_without_breaking_the_list(self):
        response = self.client.get(
            reverse('correspondence:letter_list'),
            {'received_from': 'fecha-inválida'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['filter_form'].errors)
        self.assertContains(response, 'Corrige los filtros')

    def test_invalid_export_filters_show_validation_instead_of_exporting_all(self):
        response = self.client.get(
            reverse('correspondence:letter_list'),
            {'received_from': 'fecha-inválida', 'export': 'xlsx'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertContains(response, 'Corrige los filtros')

    def test_only_admin_can_archive_and_archiving_preserves_the_record(self):
        letter = OfficeLetter.objects.create(
            delegation=self.delegation,
            received_at=date.today(),
            recipient='Alcaldesa',
            sender='Carta histórica',
            subject='Asunto histórico',
            responsible=self.functionary,
        )
        delete_url = reverse('correspondence:letter_delete', args=[letter.pk])

        denied = self.client.post(delete_url)
        self.assertEqual(denied.status_code, 403)
        self.assertIsNone(OfficeLetter.objects.get(pk=letter.pk).deleted_at)

        admin_role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(
            functionary=self.functionary,
            role=admin_role,
        )
        response = self.client.post(delete_url)

        self.assertRedirects(response, reverse('correspondence:letter_list'))
        letter.refresh_from_db()
        self.assertIsNotNone(letter.deleted_at)
        self.assertTrue(OfficeLetter.objects.filter(pk=letter.pk).exists())
        self.assertNotContains(
            self.client.get(reverse('correspondence:letter_list')),
            'Carta histórica',
        )
