from datetime import date, timedelta
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.template.backends.django import DjangoTemplates
from django.test import SimpleTestCase, TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from activities.models import Activity, Evidence
from configuration.models import Goal, Measuring, Period
from personal.models import Delegation, Functionary, Position
from .calculations import (
    calcular_cumplimiento_ponderado, calcular_meta_esperada_al_dia,
    calcular_porcentaje_cumplimiento, calcular_porcentaje_esperado,
    calcular_semaforo, estado_semaforo, obtener_indicador_funcionario,
    obtener_semaforo_funcionarios,
)


class SemaphoreFormulaTests(SimpleTestCase):
    def test_help_component_loads_without_automatic_library_discovery(self):
        configuration = deepcopy(settings.TEMPLATES[0])
        configuration.pop('BACKEND')
        configuration['NAME'] = 'semaphore_without_discovery'
        with patch('django.template.backends.django.get_installed_libraries', return_value={}):
            backend = DjangoTemplates(configuration)
            html = backend.from_string('{% load semaphore %}{% semaphore_rules %}').render()
        self.assertIn('Cómo se calcula el semáforo', html)

    def test_calendar_bounds_and_same_day_period(self):
        period = SimpleNamespace(start_date=date(2026, 7, 1), end_date=date(2026, 9, 30))
        for day, expected in (
            (date(2026, 6, 30), Decimal('0')),
            (date(2026, 7, 1), Decimal(100) / 92),
            (date(2026, 8, 15), Decimal('50')),
            (date(2026, 9, 30), Decimal('100')),
            (date(2026, 11, 25), Decimal('100')),
        ):
            with self.subTest(day=day):
                self.assertEqual(calcular_porcentaje_esperado(period, day), expected)
                self.assertEqual(calcular_meta_esperada_al_dia(period, day), expected)
        period.end_date = period.start_date
        self.assertEqual(calcular_porcentaje_esperado(period, period.start_date), 100)

    def test_exact_color_boundaries_are_shared(self):
        for achieved, expected, color, status in (
            ('50', '50', 'verde', 'green'),
            ('49.999', '50', 'ambar', 'yellow'),
            ('30', '50', 'ambar', 'yellow'),
            ('29.999', '50', 'rojo', 'red'),
            ('0', '0', 'verde', 'green'),
            ('100', '100', 'verde', 'green'),
            ('60', '100', 'ambar', 'yellow'),
            ('59.999', '100', 'rojo', 'red'),
        ):
            with self.subTest(achieved=achieved, expected=expected):
                self.assertEqual(calcular_semaforo(achieved, expected), color)
                self.assertEqual(estado_semaforo(achieved, expected)[0], status)

    def test_cap_is_applied_before_weight_and_raw_quantity_is_preserved(self):
        self.assertEqual(calcular_porcentaje_cumplimiento(20, 10), 200)
        self.assertEqual(calcular_cumplimiento_ponderado(200, 20, maximo=150), 30)
        self.assertEqual(calcular_cumplimiento_ponderado(200, 20, maximo=100), 20)
        self.assertEqual(calcular_cumplimiento_ponderado(75, 20, maximo=150), 15)

    def test_zero_or_invalid_target_does_not_divide_by_zero(self):
        for target in (None, 0, -1):
            self.assertEqual(calcular_porcentaje_cumplimiento(10, target), 0)


class SharedSemaphoreEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.period = Period.objects.create(
            start_date=today - timedelta(days=9), end_date=today + timedelta(days=10),
            computable_days=5, status=True, version_parameter='TEST',
            minimum_threshold=0, maximum_computable_days=20, semaphore='TEST',
        )
        cls.delegation = Delegation.objects.create(name='Delegacion calculos', field='URBANO')
        cls.position = Position.objects.create(name='Cargo calculos')
        cls.fn = Functionary.objects.create(
            names='Ana', lastnames='Prueba', delegation=cls.delegation, position=cls.position,
        )
        cls.first = Measuring.objects.create(service='Visitas')
        cls.second = Measuring.objects.create(service='Informes')
        Goal.objects.create(position=cls.position, period=cls.period, measuring=cls.first,
                            target_value=10, weight=60, unity='visitas')
        Goal.objects.create(position=cls.position, period=cls.period, measuring=cls.second,
                            target_value=5, weight=40, unity='informes')

    def activity(self, measuring=None, quantity=1, state='VALIDATED', evidence='APPROVED', day=None):
        activity = Activity.objects.create(
            date=day or timezone.localdate(), functionary=self.fn, measuring=measuring or self.first,
            quantity=quantity, application='Gestion', taken_action='Realizada',
            name_contact='Contacto', telephone_contact='123', state_validity=state,
        )
        Evidence.objects.create(
            name='Respaldo', author='Ana', date_evidence=activity.date, metadata='Prueba',
            file='evidences/test.pdf', activity=activity, functionary=self.fn,
            validity_state=evidence,
        )
        return activity

    def test_summary_and_detail_have_same_weighted_score_and_expected_progress(self):
        self.activity(quantity=12)
        self.activity(measuring=self.second, quantity=2)
        detail = obtener_indicador_funcionario(self.fn, self.period)
        summary, unmatched = obtener_semaforo_funcionarios([self.fn], self.period, 50)
        self.assertEqual(detail['total_ponderado'], Decimal('76'))
        self.assertEqual(summary[0]['achieved_percentage'], detail['total_ponderado'])
        self.assertEqual(detail['items'][0]['porcentaje_cumplimiento'], 120)
        self.assertEqual(detail['items'][0]['cumplimiento_aplicado'], 100)
        self.assertEqual(detail['items'][0]['avance'], 12)
        self.assertEqual(detail['items'][0]['meta_esperada_al_dia'], 50)
        self.assertEqual(summary[0]['status'], detail['status'])
        self.assertEqual(unmatched, 0)

    def test_latest_evidence_and_activity_validation_are_both_required(self):
        activity = self.activity(quantity=4)
        self.activity(quantity=50, state='PENDING')
        self.activity(quantity=50, evidence='PENDING')
        self.activity(quantity=50, day=self.period.start_date - timedelta(days=1))
        self.assertEqual(obtener_indicador_funcionario(self.fn, self.period)['items'][0]['avance'], 4)
        Evidence.objects.create(
            name='Correccion', author='Ana', date_evidence=activity.date, metadata='Revision',
            file='evidences/correction.pdf', activity=activity, functionary=self.fn,
            validity_state='REJECTED',
        )
        self.assertEqual(obtener_indicador_funcionario(self.fn, self.period)['items'][0]['avance'], 0)

    def test_unmatched_warning_counts_records_without_adding_them_to_score(self):
        extra = Measuring.objects.create(service='Sin meta')
        self.activity(measuring=extra, quantity=5)
        self.activity(measuring=extra, quantity=7)
        summary, unmatched = obtener_semaforo_funcionarios([self.fn], self.period, 50)
        self.assertEqual(unmatched, 2)
        self.assertEqual(summary[0]['achieved_percentage'], 0)

    def test_no_goal_is_neutral_even_before_the_period(self):
        Goal.objects.all().update(validity=False)
        summary, _ = obtener_semaforo_funcionarios([self.fn], self.period, 0)
        self.assertEqual(summary[0]['status'], 'no_goal')
        self.assertIsNone(summary[0]['achieved_percentage'])

    def test_color_is_decided_before_rounding(self):
        Goal.objects.filter(measuring=self.first).update(target_value=10000, weight=100)
        Goal.objects.filter(measuring=self.second).update(validity=False)
        self.activity(quantity=4999)
        summary, _ = obtener_semaforo_funcionarios([self.fn], self.period, 50)
        self.assertEqual(summary[0]['achieved_percentage'], 50)
        self.assertEqual(summary[0]['status'], 'yellow')

    def test_batch_calculation_does_not_query_for_each_functionary_or_goal(self):
        functionaries = [self.fn]
        for number in range(4):
            functionaries.append(Functionary.objects.create(
                names='Persona', lastnames=f'Prueba {number}',
                position=self.position, delegation=self.delegation,
            ))
        with self.assertNumQueries(3):
            summary, _ = obtener_semaforo_funcionarios(functionaries, self.period, 50)
        self.assertEqual(len(summary), 5)

    def test_personal_panel_summary_and_delegation_use_the_same_calculation(self):
        user = User.objects.create_user(username='a.prueba', password='Test-Password-143!')
        self.fn.user = user
        self.fn.save()
        self.activity(quantity=8)
        self.client.force_login(user)
        panel = self.client.get(reverse('user_dashboard'))
        summary = self.client.get(reverse('activities:traffic_light'))
        self.assertEqual(panel.status_code, 200)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(panel.context['indicador']['total_ponderado'], 48)
        self.assertEqual(panel.context['indicador']['status'], 'yellow')
        self.assertEqual(summary.context['traffic_light_data'][0]['achieved_percentage'], 48)
        self.assertEqual(summary.context['traffic_light_data'][0]['status'], 'yellow')
        self.assertContains(panel, 'Cómo se calcula el semáforo')
        staff = User.objects.create_user(username='admin.calculos', is_staff=True)
        self.client.force_login(staff)
        delegation = self.client.get(reverse('delegation_dashboard'))
        self.assertEqual(delegation.status_code, 200)
        result = delegation.context['delegation_summaries'][0]
        self.assertEqual(result['average_percentage'], 48)
        self.assertEqual(result['status'], 'yellow')
