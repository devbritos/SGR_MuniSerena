from django.test import TestCase

from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from activities.models import Activity
from configuration.models import Measuring
from personal.models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)

from .models import Commitment


class CommitmentActivityLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='funcionario_compromiso',
            password='test-password',
        )
        delegation = Delegation.objects.create(
            name='Delegación compromiso',
            field='URBANO',
        )
        position = Position.objects.create(name='Cargo compromiso')
        self.functionary = Functionary.objects.create(
            user=self.user,
            delegation=delegation,
            position=position,
            names='Funcionario',
            lastnames='Compromiso',
        )
        self.measuring = Measuring.objects.create(
            service='Ítem del compromiso',
            measurable_item='Actividad asociada',
        )
        self.activity = Activity.objects.create(
            date=timezone.localdate(),
            application='Solicitud de origen',
            taken_action='Acción realizada',
            name_contact='Vecino solicitante',
            telephone_contact='12345678',
            functionary=self.functionary,
            measuring=self.measuring,
            enters_pipe=True,
        )
        self.client.force_login(self.user)

    def _commitment_data(self, **overrides):
        data = {
            'origin': 'Solicitud de origen',
            'applic_name': 'Vecino solicitante',
            'territory': 'Sector de prueba',
            'commitment_date': (
                timezone.localdate() + timedelta(days=10)
            ).isoformat(),
            'support': '',
            'state': Commitment.State.JOINED,
            'observation': 'Compromiso asociado a actividad.',
            'functionary': str(self.functionary.pk),
            'activity_id': str(self.activity.pk),
        }
        data.update(overrides)
        return data

    def test_commitment_responsible_is_preselected_and_scoped_to_own_delegation(self):
        create_url = reverse('agenda:commitment_create')
        other_user = User.objects.create_user(username='colega_compromiso')
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=self.functionary.delegation,
            position=self.functionary.position,
            names='Colega',
            lastnames='Delegación',
        )
        outside_delegation = Delegation.objects.create(
            name='Otra delegación compromiso',
            field='RURAL',
        )
        outside_functionary = Functionary.objects.create(
            delegation=outside_delegation,
            position=self.functionary.position,
            names='Fuera',
            lastnames='Delegación',
        )

        response = self.client.get(create_url)

        self.assertEqual(response.status_code, 200)
        responsible_field = response.context['form'].fields['functionary']
        self.assertCountEqual(
            list(responsible_field.queryset),
            [self.functionary, other_functionary],
        )
        self.assertEqual(
            response.context['form']['functionary'].value(),
            self.functionary.pk,
        )
        self.assertNotIn(
            outside_functionary,
            responsible_field.queryset,
        )

    def test_commitment_can_be_assigned_to_another_functionary_in_same_delegation(self):
        other_user = User.objects.create_user(username='responsable_compromiso')
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=self.functionary.delegation,
            position=self.functionary.position,
            names='Responsable',
            lastnames='Delegación',
        )

        response = self.client.post(
            reverse('agenda:commitment_create'),
            self._commitment_data(functionary=str(other_functionary.pk)),
        )

        self.assertRedirects(response, reverse('agenda:commitment_list'))
        self.assertEqual(
            Commitment.objects.get().functionary,
            other_functionary,
        )

    def test_commitment_cannot_be_assigned_to_functionary_in_another_delegation(self):
        outside_delegation = Delegation.objects.create(
            name='Delegación externa compromiso',
            field='RURAL',
        )
        outside_functionary = Functionary.objects.create(
            delegation=outside_delegation,
            position=self.functionary.position,
            names='Fuera',
            lastnames='Delegación',
        )

        response = self.client.post(
            reverse('agenda:commitment_create'),
            self._commitment_data(functionary=str(outside_functionary.pk)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Commitment.objects.exists())
        self.assertIn('functionary', response.context['form'].errors)

    def test_commitment_update_can_reassign_to_functionary_in_same_delegation(self):
        other_user = User.objects.create_user(username='responsable_edicion')
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=self.functionary.delegation,
            position=self.functionary.position,
            names='Responsable',
            lastnames='Edición',
        )
        commitment = Commitment.objects.create(
            origin='Solicitud de origen',
            applic_name='Vecino solicitante',
            territory='Sector de prueba',
            commitment_date=timezone.localdate() + timedelta(days=10),
            functionary=self.functionary,
        )

        response = self.client.post(
            reverse('agenda:commitment_update', args=[commitment.pk]),
            self._commitment_data(
                functionary=str(other_functionary.pk),
                activity_id='',
            ),
        )

        self.assertRedirects(response, reverse('agenda:commitment_list'))
        commitment.refresh_from_db()
        self.assertEqual(commitment.functionary, other_functionary)

    def test_edit_form_shows_existing_date_in_html_date_format_and_allows_change(self):
        commitment_date = timezone.localdate() + timedelta(days=10)
        commitment = Commitment.objects.create(
            origin='Solicitud de origen',
            applic_name='Vecino solicitante',
            territory='Sector de prueba',
            commitment_date=commitment_date,
            functionary=self.functionary,
        )
        edit_url = reverse('agenda:commitment_update', args=[commitment.pk])

        response = self.client.get(edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'value="{commitment_date.isoformat()}"',
        )

        new_date = timezone.localdate() + timedelta(days=20)
        response = self.client.post(
            edit_url,
            self._commitment_data(
                commitment_date=new_date.isoformat(),
                activity_id='',
            ),
        )

        self.assertRedirects(response, reverse('agenda:commitment_list'))
        commitment.refresh_from_db()
        self.assertEqual(commitment.commitment_date, new_date)

    def test_non_admin_cannot_delete_commitment(self):
        commitment = Commitment.objects.create(
            origin='Solicitud de origen',
            applic_name='Vecino solicitante',
            territory='Sector de prueba',
            commitment_date=timezone.localdate() + timedelta(days=10),
            functionary=self.functionary,
        )

        response = self.client.post(
            reverse('agenda:commitment_delete', args=[commitment.pk]),
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Commitment.objects.filter(pk=commitment.pk).exists())

    def test_admin_role_can_delete_commitment_and_sees_delete_action(self):
        admin_user = User.objects.create_user(username='admin_compromiso')
        admin_functionary = Functionary.objects.create(
            user=admin_user,
            delegation=self.functionary.delegation,
            position=self.functionary.position,
            names='Administrador',
            lastnames='Compromisos',
        )
        admin_role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(
            functionary=admin_functionary,
            role=admin_role,
        )
        commitment = Commitment.objects.create(
            origin='Solicitud de origen',
            applic_name='Vecino solicitante',
            territory='Sector de prueba',
            commitment_date=timezone.localdate() + timedelta(days=10),
            functionary=self.functionary,
        )
        self.client.force_login(admin_user)

        list_response = self.client.get(reverse('agenda:commitment_list'))
        self.assertContains(
            list_response,
            reverse('agenda:commitment_delete', args=[commitment.pk]),
        )

        response = self.client.post(
            reverse('agenda:commitment_delete', args=[commitment.pk]),
        )

        self.assertRedirects(response, reverse('agenda:commitment_list'))
        self.assertFalse(Commitment.objects.filter(pk=commitment.pk).exists())

    def test_commitment_created_from_activity_links_it_and_uses_its_measuring(self):
        create_url = reverse('agenda:commitment_create')
        response = self.client.get(
            create_url,
            {'activity_id': self.activity.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['form']['measuring'].value(),
            self.measuring.pk,
        )

        response = self.client.post(
            create_url,
            self._commitment_data(),
        )

        self.assertRedirects(response, reverse('agenda:commitment_list'))
        commitment = Commitment.objects.get()
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.commitment, commitment)
        self.assertEqual(commitment.measuring, self.measuring)

    def test_cannot_link_another_functionarys_activity(self):
        other_user = User.objects.create_user(username='otro_funcionario')
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=self.functionary.delegation,
            position=self.functionary.position,
            names='Otro',
            lastnames='Funcionario',
        )
        other_activity = Activity.objects.create(
            date=timezone.localdate(),
            application='Actividad ajena',
            taken_action='Acción ajena',
            name_contact='Contacto ajeno',
            telephone_contact='12345678',
            functionary=other_functionary,
            measuring=self.measuring,
            enters_pipe=True,
        )

        response = self.client.post(
            reverse('agenda:commitment_create'),
            self._commitment_data(activity_id=str(other_activity.pk)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Commitment.objects.exists())
        self.assertIn('__all__', response.context['form'].errors)
