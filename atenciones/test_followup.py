from datetime import timedelta
from io import BytesIO

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from personal.models import Delegation, Functionary
from .models import Attention, AttentionFollowUp
from .tests import CitizenAttentionTests


class AttentionFollowUpTests(TestCase):
    def setUp(self):
        CitizenAttentionTests.setUp(self)
        self.attention = Attention.objects.create(
            requester_name='Vecina con seguimiento', attention_type=self.attention_type,
            sub_attention=self.sub_attention, description='Solicita limpieza.',
            delegation=self.delegation, functionary=self.functionary,
            followup_responsible=self.functionary,
        )
        self.url = reverse('atenciones:attention_detail', args=[self.attention.pk])

    def payload(self, **overrides):
        self.attention.refresh_from_db()
        data = {
            'version': self.attention.updated_at.isoformat(),
            'note': 'Llamada preventiva: se informó la visita técnica.',
            'status': Attention.Status.IN_PROGRESS,
            'followup_responsible': self.functionary.pk,
            'next_action': 'Confirmar la visita con la vecina',
            'next_contact_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
        }
        data.update(overrides)
        return data

    def test_detail_and_history_escape_user_content(self):
        self.attention.description = '<script>alert(1)</script>'
        self.attention.save()
        response = self.client.get(self.url)
        self.assertContains(response, 'Registrar seguimiento')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_followup_keeps_original_registration_and_history_snapshots(self):
        original = self.attention.description
        self.assertRedirects(self.client.post(self.url, self.payload()), self.url)
        entry = AttentionFollowUp.objects.get()
        self.assertEqual(entry.author, self.functionary)
        self.assertEqual(entry.next_action, 'Confirmar la visita con la vecina')
        self.client.post(self.url, self.payload(next_action='Informar nueva fecha', note='Segunda llamada.'))
        self.attention.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(self.attention.description, original)
        self.assertEqual(self.attention.functionary, self.functionary)
        self.assertEqual(entry.next_action, 'Confirmar la visita con la vecina')
        self.assertEqual(self.attention.followups.count(), 2)

    def test_open_followup_requires_next_action_and_future_or_today_date(self):
        for overrides, field in [({'next_action': ''}, 'next_action'), ({'next_contact_date': ''}, 'next_contact_date'), ({'next_contact_date': (timezone.localdate() - timedelta(days=1)).isoformat()}, 'next_contact_date')]:
            with self.subTest(field=field, overrides=overrides):
                response = self.client.post(self.url, self.payload(**overrides))
                self.assertIn(field, response.context['form'].errors)
        self.assertFalse(AttentionFollowUp.objects.exists())

    def test_closure_requires_outcome_and_details(self):
        response = self.client.post(self.url, self.payload(status=Attention.Status.CLOSED))
        self.assertIn('closure_outcome', response.context['form'].errors)
        self.assertIn('closure_details', response.context['form'].errors)
        self.assertFalse(AttentionFollowUp.objects.exists())

    def test_closure_clears_next_action_and_cannot_be_overwritten(self):
        data = self.payload(status=Attention.Status.CLOSED, closure_outcome=Attention.Outcome.REFERRED, closure_details='Se informó la derivación a la unidad correspondiente.')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.attention.refresh_from_db()
        self.assertIsNotNone(self.attention.closed_at)
        self.assertIsNone(self.attention.next_contact_date)
        self.assertEqual(self.attention.next_action, '')
        self.assertFalse(self.attention.is_overdue)
        self.assertContains(self.client.get(self.url), 'Derivación informada')
        self.client.post(self.url, self.payload())
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.status, Attention.Status.CLOSED)
        self.assertEqual(self.attention.followups.count(), 1)

    def test_conflict_preserves_draft_without_writing(self):
        data = self.payload()
        self.attention.next_action = 'Acción registrada por otra persona'
        self.attention.save()
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Otra persona actualizó')
        self.assertContains(response, data['note'])
        self.assertFalse(AttentionFollowUp.objects.exists())
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.next_action, 'Acción registrada por otra persona')

    def test_cannot_read_or_post_attention_from_other_delegation(self):
        other = Delegation.objects.create(name='Otra delegación seguimiento', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        self.attention.delegation = other
        self.attention.functionary = colleague
        self.attention.followup_responsible = colleague
        self.attention.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)
        self.assertFalse(AttentionFollowUp.objects.exists())

    def test_cannot_assign_to_another_delegation_or_inactive_functionary(self):
        other = Delegation.objects.create(name='Delegación sin acceso', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        response = self.client.post(self.url, self.payload(followup_responsible=colleague.pk))
        self.assertIn('followup_responsible', response.context['form'].errors)
        colleague.delegation = self.delegation
        colleague.is_active = False
        colleague.save()
        response = self.client.post(self.url, self.payload(followup_responsible=colleague.pk))
        self.assertIn('followup_responsible', response.context['form'].errors)

    def test_assigned_functionary_can_access_and_register_followup(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user(username='assigned_followup', password='test-password')
        colleague = Functionary.objects.create(user=user, delegation=self.delegation, position=self.position, names='Nueva', lastnames='Responsable')
        self.client.post(self.url, self.payload(followup_responsible=colleague.pk))
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('atenciones:attention_list')), self.attention.requester_name)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertRedirects(self.client.post(self.url, self.payload(followup_responsible=colleague.pk)), self.url)
        self.assertEqual(self.attention.followups.first().author, colleague)

    def test_filters_and_export_use_same_results(self):
        self.attention.next_contact_date = timezone.localdate() - timedelta(days=1)
        self.attention.next_action = 'Llamar a la vecina'
        self.attention.save()
        url = reverse('atenciones:attention_list')
        overdue = self.client.get(url, {'followup': 'overdue'})
        self.assertContains(overdue, self.attention.requester_name)
        self.assertEqual(overdue.context['summary']['overdue'], 1)
        self.assertNotContains(self.client.get(url, {'followup': 'today'}), self.attention.requester_name)
        self.assertNotContains(self.client.get(url, {'status': Attention.Status.CLOSED}), self.attention.requester_name)
        export = self.client.get(url, {'followup': 'overdue', 'export': 'xlsx'})
        sheet = load_workbook(BytesIO(export.content), read_only=True).active
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual(sheet['I2'].value, 'Pendiente')
        self.assertEqual(sheet['K2'].value, 'Llamar a la vecina')

    def test_deleted_attention_has_no_detail_or_followup_access(self):
        self.attention.deleted_at = timezone.now()
        self.attention.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)

    def test_legacy_attention_can_be_classified_on_first_followup(self):
        self.attention.status = Attention.Status.UNCLASSIFIED
        self.attention.save()
        self.assertContains(self.client.get(self.url), 'anterior al seguimiento')
        self.client.post(self.url, self.payload())
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.status, Attention.Status.IN_PROGRESS)


class AttentionFollowUpMigrationTests(TransactionTestCase):
    def test_existing_attentions_remain_unclassified_and_new_ones_start_pending(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([('atenciones', '0001_initial')])
            executor = MigrationExecutor(connection)
            apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
            delegation = apps.get_model('personal', 'Delegation').objects.create(name='Migración', field='URBANO')
            position = apps.get_model('personal', 'Position').objects.create(name='Cargo')
            functionary = apps.get_model('personal', 'Functionary').objects.create(delegation=delegation, position=position, names='Nombre', lastnames='Apellido')
            attention_type = apps.get_model('atenciones', 'AttentionType').objects.create(code='MIG', name='Migración')
            sub = apps.get_model('atenciones', 'SubAttention').objects.create(code='MIG-S', name='Sub', attention_type=attention_type)
            old = apps.get_model('atenciones', 'Attention').objects.create(requester_name='Registro anterior', description='Conservar este texto', delegation=delegation, functionary=functionary, attention_type=attention_type, sub_attention=sub)
            old_commitment = apps.get_model('agenda', 'Commitment').objects.create(
                origin='Solicitud anterior', applic_name='Vecina', territory='Sector',
                commitment_date=timezone.localdate(), functionary_id=functionary.pk,
            )
            old_letter = apps.get_model('correspondence', 'OfficeLetter').objects.create(
                delegation_id=delegation.pk, responsible_id=functionary.pk,
                received_at=timezone.localdate(), sender='Remitente anterior',
                recipient='Delegación', subject='Conservar carta',
            )
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            migrated = Attention.objects.get(pk=old.pk)
            self.assertEqual(migrated.status, Attention.Status.UNCLASSIFIED)
            self.assertEqual(migrated.description, 'Conservar este texto')
            self.assertIsNone(migrated.followup_responsible_id)
            self.assertEqual(migrated.functionary_id, functionary.pk)
            from agenda.models import Commitment
            migrated_commitment = Commitment.objects.get(pk=old_commitment.pk)
            self.assertIsNone(migrated_commitment.source_attention_id)
            self.assertIsNone(migrated_commitment.submission_token)
            self.assertEqual(migrated_commitment.origin, 'Solicitud anterior')
            from correspondence.models import OfficeLetter
            migrated_letter = OfficeLetter.objects.get(pk=old_letter.pk)
            self.assertIsNone(migrated_letter.attention_id)
            self.assertEqual(migrated_letter.subject, 'Conservar carta')
            new = Attention.objects.create(requester_name='Registro nuevo', description='Nuevo', delegation_id=delegation.pk, functionary_id=functionary.pk, attention_type_id=attention_type.pk, sub_attention_id=sub.pk)
            self.assertEqual(new.status, Attention.Status.PENDING)
        finally:
            MigrationExecutor(connection).migrate(latest)
