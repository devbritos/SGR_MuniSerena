import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agenda.models import Commitment
from personal.models import Delegation, Functionary, FunctionaryRole, Role
from .models import Attention, AttentionFollowUp
from . import tests as attention_tests


class AttentionCommitmentTests(TestCase):
    def setUp(self):
        attention_tests.CitizenAttentionTests.setUp(self)
        self.attention = Attention.objects.create(
            requester_name='Vecina con solicitud', requester_contact='vecina@example.com',
            attention_type=self.attention_type, sub_attention=self.sub_attention,
            description='Coordinar limpieza del terreno.', delegation=self.delegation,
            functionary=self.functionary, followup_responsible=self.functionary,
        )
        self.url = reverse('atenciones:attention_commitment_create', args=[self.attention.pk])
        self.detail_url = reverse('atenciones:attention_detail', args=[self.attention.pk])

    def payload(self, **overrides):
        data = {
            'creation_token': str(uuid.uuid4()), 'applic_name': self.attention.requester_name,
            'territory': 'Sector norte', 'functionary': self.functionary.pk,
            'commitment_date': (timezone.localdate() + timedelta(days=3)).isoformat(),
            'observation': 'Visitar el terreno y confirmar la limpieza.',
        }
        data.update(overrides)
        return data

    def test_form_prefills_source_and_only_asks_for_relevant_data(self):
        response = self.client.get(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form['applic_name'].value(), self.attention.requester_name)
        self.assertEqual(form['observation'].value(), self.attention.description)
        self.assertEqual(form['functionary'].value(), self.functionary.pk)
        self.assertIsNone(form['commitment_date'].value())
        self.assertNotIn('origin', form.fields)
        self.assertNotIn('state', form.fields)
        self.assertContains(response, 'Crear y vincular compromiso')

    def test_create_links_existing_attention_and_records_history_without_changing_state(self):
        payload = self.payload()
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, self.detail_url)
        commitment = Commitment.objects.get()
        self.assertEqual(commitment.source_attention, self.attention)
        self.assertEqual(commitment.origin, f'Atención ciudadana #{self.attention.pk}')
        self.assertEqual(commitment.support, self.attention.requester_contact)
        entry = AttentionFollowUp.objects.get()
        self.assertEqual(entry.author, self.functionary)
        self.assertIn(f'compromiso #{commitment.pk}', entry.note)
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.status, Attention.Status.PENDING)
        self.assertEqual(self.attention.description, 'Coordinar limpieza del terreno.')
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, f'Compromiso #{commitment.pk}')
        self.assertContains(detail, reverse('agenda:commitment_update', args=[commitment.pk]))

    def test_repeated_submission_creates_only_one_commitment_and_history_entry(self):
        payload = self.payload()
        self.client.post(self.url, payload)
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(Commitment.objects.count(), 1)
        self.assertEqual(AttentionFollowUp.objects.count(), 1)

    def test_source_and_initial_state_cannot_be_changed_by_hidden_extra_fields(self):
        self.client.post(self.url, self.payload(origin='Origen manipulado', source_attention='999999', state=Commitment.State.DONE))
        commitment = Commitment.objects.get()
        self.assertEqual(commitment.source_attention, self.attention)
        self.assertEqual(commitment.state, Commitment.State.JOINED)
        self.assertEqual(commitment.origin, f'Atención ciudadana #{self.attention.pk}')

    def test_token_from_another_attention_cannot_be_reused(self):
        payload = self.payload()
        self.client.post(self.url, payload)
        other = Attention.objects.create(requester_name='Otra solicitud', attention_type=self.attention_type, sub_attention=self.sub_attention, description='Otro caso.', delegation=self.delegation, functionary=self.functionary)
        response = self.client.post(reverse('atenciones:attention_commitment_create', args=[other.pk]), payload)
        self.assertContains(response, 'Este formulario ya fue utilizado')
        self.assertEqual(Commitment.objects.count(), 1)
        self.assertEqual(AttentionFollowUp.objects.count(), 1)

    def test_invalid_data_preserves_text_without_creating_commitment(self):
        for fields, field in [({'territory': ''}, 'territory'), ({'commitment_date': ''}, 'commitment_date'), ({'observation': ''}, 'observation'), ({'commitment_date': (timezone.localdate() - timedelta(days=1)).isoformat()}, 'commitment_date')]:
            with self.subTest(field=field):
                response = self.client.post(self.url, self.payload(**fields))
                self.assertIn(field, response.context['form'].errors)
                self.assertEqual(response.context['form']['applic_name'].value(), self.attention.requester_name)
        self.assertFalse(Commitment.objects.exists())
        self.assertFalse(AttentionFollowUp.objects.exists())

    def test_closed_attention_rejects_creation_including_if_closed_after_opening_form(self):
        self.client.get(self.url)
        self.attention.status = Attention.Status.CLOSED
        self.attention.closed_at = timezone.now()
        self.attention.closure_outcome = Attention.Outcome.RESOLVED
        self.attention.closure_details = 'Resuelto.'
        self.attention.save()
        self.assertRedirects(self.client.get(self.url), self.detail_url)
        response = self.client.post(self.url, self.payload())
        self.assertContains(response, 'La atención se cerró')
        self.assertFalse(Commitment.objects.exists())
        self.assertNotContains(self.client.get(self.detail_url), 'Crear compromiso')

    def test_cannot_read_or_create_from_another_delegation_or_deleted_attention(self):
        other = Delegation.objects.create(name='Otra delegación compromiso', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        self.attention.delegation = other
        self.attention.functionary = colleague
        self.attention.followup_responsible = colleague
        self.attention.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)
        self.attention.delegation = self.delegation
        self.attention.functionary = self.functionary
        self.attention.deleted_at = timezone.now()
        self.attention.save()
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)

    def test_responsible_must_be_active_and_in_source_delegation(self):
        other = Delegation.objects.create(name='Fuera de la atención', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        response = self.client.post(self.url, self.payload(functionary=colleague.pk))
        self.assertIn('functionary', response.context['form'].errors)
        colleague.delegation = self.delegation
        colleague.is_active = False
        colleague.save()
        response = self.client.post(self.url, self.payload(functionary=colleague.pk))
        self.assertIn('functionary', response.context['form'].errors)
        self.assertFalse(Commitment.objects.exists())

    def test_global_admin_uses_attention_delegation_instead_of_own_delegation(self):
        other = Delegation.objects.create(name='Delegación del administrador', field='RURAL')
        admin_user = User.objects.create_user(username='global_attention_admin', password='test-password')
        administrator = Functionary.objects.create(user=admin_user, delegation=other, position=self.position, names='Admin', lastnames='Global')
        role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(functionary=administrator, role=role)
        self.client.force_login(admin_user)
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(Commitment.objects.get().functionary, self.functionary)

    def test_assigned_colleague_can_open_attention_and_original_registrant_can_open_commitment(self):
        user = User.objects.create_user(username='assigned_commitment_user', password='test-password')
        colleague = Functionary.objects.create(user=user, delegation=self.delegation, position=self.position, names='Persona', lastnames='Asignada')
        self.client.post(self.url, self.payload(functionary=colleague.pk))
        commitment = Commitment.objects.get()
        edit_url = reverse('agenda:commitment_update', args=[commitment.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        self.client.force_login(user)
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)
        self.assertContains(self.client.get(edit_url), 'Volver a la atención')

    def test_marking_commitment_done_does_not_close_attention(self):
        self.client.post(self.url, self.payload())
        commitment = Commitment.objects.get()
        response = self.client.post(reverse('agenda:commitment_update', args=[commitment.pk]), {
            'origin': commitment.origin, 'applic_name': commitment.applic_name,
            'territory': commitment.territory, 'commitment_date': commitment.commitment_date.isoformat(),
            'functionary': self.functionary.pk, 'observation': commitment.observation,
            'state': Commitment.State.DONE,
        })
        self.assertEqual(response.status_code, 302)
        commitment.refresh_from_db()
        self.assertEqual(commitment.state, Commitment.State.DONE)
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.status, Attention.Status.PENDING)
        self.assertContains(self.client.get(self.detail_url), 'Cumplido')
