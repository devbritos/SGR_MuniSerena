from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from activities.models import Activity, Evidence
from agenda.models import Commitment
from analytics.calculations import obtener_indicador_funcionario
from configuration.forms import GoalForm, MeasuringForm
from configuration.models import Goal, Measuring, Period
from personal.models import Delegation, Functionary, Position


class CommitmentIndicatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.period = Period.objects.create(start_date=today - timedelta(days=10), end_date=today + timedelta(days=10),
            computable_days=21, maximum_computable_days=21, minimum_threshold=0, version_parameter='TEST', semaphore='TEST')
        cls.delegation = Delegation.objects.create(name='Delegacion compromisos', field='URBANO')
        cls.position = Position.objects.create(name='Gestor compromisos')
        cls.fn = Functionary.objects.create(names='Ana', lastnames='Prueba', position=cls.position, delegation=cls.delegation)
        cls.other = Functionary.objects.create(names='Otra', lastnames='Persona', position=cls.position, delegation=cls.delegation)
        cls.done = Measuring.objects.create(code='DONE', service='Compromisos cumplidos', calculation_method=Measuring.Calculation.COMMITMENTS_DONE)
        cls.pending = Measuring.objects.create(code='PENDING', service='Compromisos pendientes', calculation_method=Measuring.Calculation.COMMITMENTS_PENDING)
        Goal.objects.create(position=cls.position, period=cls.period, measuring=cls.done, target_value=80, weight=70, unity='%')
        Goal.objects.create(position=cls.position, period=cls.period, measuring=cls.pending, target_value=10, weight=30, unity='%')

    def commitment(self, state, fn=None, created_at=None, deadline=None):
        obj = Commitment.objects.create(functionary=fn or self.fn, state=state, origin='Prueba', applic_name='Solicitud', territory='Sector', commitment_date=deadline or timezone.localdate())
        if created_at is not None:
            Commitment.objects.filter(pk=obj.pk).update(created_at=created_at)
        return obj

    def test_counts_and_weighted_contribution_come_from_agenda_without_activities(self):
        for _ in range(8): self.commitment(Commitment.State.DONE)
        self.commitment(Commitment.State.PENDING)
        self.commitment(Commitment.State.IN_PROGRESS)
        metric = obtener_indicador_funcionario(self.fn, self.period)
        self.assertEqual(metric['commitments']['total'], 10)
        self.assertEqual(metric['commitments']['done_percentage'], 80)
        self.assertEqual(metric['commitments']['pending_percentage'], 10)
        self.assertEqual(metric['total_ponderado'], 100)
        self.assertEqual(metric['items'][0]['avance'], 80)
        self.assertEqual(metric['items'][0]['cumplimiento_ponderado'], 70)
        self.assertEqual(metric['items'][1]['cumplimiento_ponderado'], 30)
        self.assertFalse(Activity.objects.exists())

    def test_state_changes_refresh_percentages_without_a_duplicate_record(self):
        obj = self.commitment(Commitment.State.PENDING)
        before = obtener_indicador_funcionario(self.fn, self.period)
        self.assertEqual(before['commitments']['done_percentage'], 0)
        obj.state = Commitment.State.DONE
        obj.save()
        after = obtener_indicador_funcionario(self.fn, self.period)
        self.assertEqual(after['commitments']['done_percentage'], 100)
        self.assertEqual(after['commitments']['pending_percentage'], 0)
        self.assertEqual(Commitment.objects.count(), 1)

    def test_pending_scale_inverts_the_percentage_and_respects_excel_boundaries(self):
        objs = [self.commitment(Commitment.State.PENDING if n < 1 else Commitment.State.DONE) for n in range(10)]
        self.assertEqual(obtener_indicador_funcionario(self.fn, self.period)['items'][1]['porcentaje_cumplimiento'], 100)
        Commitment.objects.filter(pk__in=[o.pk for o in objs[:5]]).update(state=Commitment.State.PENDING)
        self.assertEqual(obtener_indicador_funcionario(self.fn, self.period)['items'][1]['porcentaje_cumplimiento'], 50)
        Commitment.objects.filter(pk=objs[5].pk).update(state=Commitment.State.PENDING)
        self.assertEqual(obtener_indicador_funcionario(self.fn, self.period)['items'][1]['porcentaje_cumplimiento'], 0)

    def test_no_commitments_is_no_data_not_perfect_pending_compliance(self):
        metric = obtener_indicador_funcionario(self.fn, self.period)
        self.assertIsNone(metric['commitments']['pending_percentage'])
        self.assertEqual(metric['items'][1]['semaforo'], 'sin_datos')
        self.assertEqual(metric['items'][1]['cumplimiento_ponderado'], 0)

    def test_cohort_uses_registration_date_and_does_not_include_other_workers_or_archived_rows(self):
        start = timezone.make_aware(datetime.combine(self.period.start_date, time.min))
        end = timezone.make_aware(datetime.combine(self.period.end_date + timedelta(days=1), time.min))
        self.commitment(Commitment.State.DONE, created_at=start, deadline=self.period.end_date + timedelta(days=90))
        self.commitment(Commitment.State.DONE, created_at=end - timedelta(microseconds=1))
        self.commitment(Commitment.State.PENDING, created_at=start - timedelta(microseconds=1))
        self.commitment(Commitment.State.PENDING, created_at=end)
        self.commitment(Commitment.State.PENDING, fn=self.other)
        archived = self.commitment(Commitment.State.PENDING)
        archived.deleted_at = timezone.now(); archived.save()
        metric = obtener_indicador_funcionario(self.fn, self.period)
        self.assertEqual(metric['commitments']['total'], 2)
        self.assertEqual(metric['commitments']['done_percentage'], 100)

    def test_an_activity_cannot_double_count_an_automatic_commitment_indicator(self):
        self.commitment(Commitment.State.DONE)
        activity = Activity.objects.create(date=timezone.localdate(), functionary=self.fn, measuring=self.done,
            application='Carga anterior', taken_action='Prueba', name_contact='Contacto', telephone_contact='123',
            quantity=500, state_validity='VALIDATED')
        Evidence.objects.create(name='Respaldo', author='Ana', date_evidence=activity.date, metadata='Prueba',
            file='test.pdf', activity=activity, functionary=self.fn, validity_state='APPROVED')
        metric = obtener_indicador_funcionario(self.fn, self.period)
        self.assertEqual(metric['items'][0]['avance'], 100)
        self.assertEqual(metric['items'][0]['cumplimiento_ponderado'], 70)

    def test_catalog_method_defaults_to_activities_for_legacy_forms(self):
        form = MeasuringForm(data={'code': 'OLD', 'service': 'Visitas', 'validity': 'on'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().calculation_method, Measuring.Calculation.ACTIVITIES)

    def test_percentage_goals_accept_human_readable_percentages_and_set_the_unit(self):
        position = Position.objects.create(name='Nuevo cargo porcentajes')
        payload = {'positions': [position.pk], 'measuring': self.done.pk, 'period': self.period.pk,
                   'weight': 20, 'target_value': 80, 'unity': '', 'validity': 'on'}
        form = GoalForm(data=payload)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['unity'], '%')
        payload['target_value'] = 101
        self.assertIn('target_value', GoalForm(data=payload).errors)
        payload.update(measuring=self.pending.pk, target_value=50)
        self.assertIn('target_value', GoalForm(data=payload).errors)

    def test_automatic_metrics_cannot_be_selected_when_registering_an_activity(self):
        from activities.forms import ActivityForm
        form = ActivityForm()
        self.assertNotIn(self.done, form.fields['measuring'].queryset)
        self.assertNotIn(self.pending, form.fields['measuring'].queryset)
