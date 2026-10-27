from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from personal.models import Delegation, Functionary, FunctionaryRole, Position, Role

from .models import Goal, Measuring, Period

# Create your tests here.


class MeasuringCatalogViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_items',
            email='items@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)

    def test_measuring_list_searches_and_exports(self):
        Measuring.objects.create(
            code='IT-01',
            service='Atención vecinal',
            measurable_item='Descripción de prueba',
        )
        response = self.client.get(
            reverse('configuration:measuring_list'),
            {'q': 'VECINAL'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Atención vecinal')
        self.assertContains(response, 'Ítems de medición')

        export = self.client.get(
            reverse('configuration:measuring_list'),
            {'export': 'xlsx', 'q': 'vecinal'},
        )
        self.assertEqual(export.status_code, 200)
        self.assertEqual(
            export['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_measuring_create_reports_success_only_after_save(self):
        response = self.client.post(
            reverse('configuration:measuring_create'),
            {
                'code': 'IT-02',
                'service': 'Nuevo ítem',
                'measurable_item': 'Descripción',
                'validity': 'on',
            },
        )
        self.assertRedirects(response, reverse('configuration:measuring_list'))
        self.assertTrue(Measuring.objects.filter(code='IT-02').exists())

    def test_measuring_form_uses_clear_spanish_labels_and_guidance(self):
        response = self.client.get(reverse('configuration:measuring_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Código del ítem')
        self.assertContains(response, 'Nombre del ítem de medición')
        self.assertContains(response, 'Identificador único')
        self.assertContains(response, 'Crear ítem de medición')


class GoalFormTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_goals',
            email='goals@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)
        self.position_one = Position.objects.create(name='Cargo uno')
        self.position_two = Position.objects.create(name='Cargo dos')
        self.measuring = Measuring.objects.create(
            code='META-01',
            service='Atención vecinal',
            measurable_item='Atenciones realizadas',
        )
        self.period = Period.objects.create(
            start_date='2026-01-01',
            end_date='2026-12-31',
            computable_days=365,
            status=True,
            version_parameter='2026',
            minimum_threshold=0,
            maximum_computable_days=365,
            semaphore='SGR',
        )

    def test_goal_list_distinguishes_target_value_from_weight(self):
        Goal.objects.create(
            position=self.position_one,
            measuring=self.measuring,
            period=self.period,
            weight=50,
            validity=True,
            target_value=120,
            unity='atenciones',
        )
        response = self.client.get(reverse('configuration:goal_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Metas y ponderaciones por cargo')
        self.assertContains(response, 'Ítem de medición')
        self.assertContains(response, 'Valor objetivo')
        self.assertContains(response, 'Ponderación')

    def test_goal_form_renders_spanish_labels_and_updated_layout(self):
        response = self.client.get(reverse('configuration:goal_create'))

        self.assertEqual(response.status_code, 200)
        for label in (
            'Cargos responsables',
            'Ítem de medición',
            'Período de medición',
            'Ponderación (%)',
            'Meta activa',
            'Valor de la meta',
            'Unidad de medida',
        ):
            self.assertContains(response, label)
        self.assertContains(response, 'Crear meta')
        self.assertContains(response, 'Cargo uno')
        self.assertContains(response, 'Cargo dos')
        self.assertContains(response, 'La suma por cargo y período')
        self.assertNotContains(response, '>Position<')
        self.assertNotContains(response, '>Target value<')

    def test_goal_create_saves_one_goal_per_selected_position(self):
        response = self.client.post(
            reverse('configuration:goal_create'),
            {
                'positions': [self.position_one.pk, self.position_two.pk],
                'measuring': self.measuring.pk,
                'period': self.period.pk,
                'weight': '30',
                'validity': 'on',
                'target_value': '120',
                'unity': 'atenciones',
            },
        )

        self.assertRedirects(response, reverse('configuration:goal_list'))
        self.assertEqual(
            Goal.objects.filter(
                measuring=self.measuring,
                period=self.period,
            ).count(),
            2,
        )
        self.assertSetEqual(
            set(
                Goal.objects.filter(
                    measuring=self.measuring,
                    period=self.period,
                ).values_list('position_id', flat=True)
            ),
            {self.position_one.pk, self.position_two.pk},
        )

    def test_goal_form_requires_at_least_one_position(self):
        response = self.client.post(
            reverse('configuration:goal_create'),
            {
                'positions': [],
                'measuring': self.measuring.pk,
                'period': self.period.pk,
                'weight': '30',
                'target_value': '120',
                'unity': 'atenciones',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selecciona al menos un cargo responsable.')
        self.assertFalse(Goal.objects.exists())


class PeriodCreateEntryPointTests(TestCase):
    def test_admin_role_can_find_period_creation_from_configuration(self):
        user = User.objects.create_user(
            username='admin_periods',
            password='test-password',
        )
        role = Role.objects.create(role_name=Role.ADMIN)
        functionary = Functionary.objects.create(
            user=user,
            delegation=Delegation.objects.create(
                name='Delegación períodos',
                field='URBANO',
            ),
            position=Position.objects.create(name='Cargo períodos'),
            names='Admin',
            lastnames='Períodos',
        )
        FunctionaryRole.objects.create(functionary=functionary, role=role)
        self.client.force_login(user)

        goals_response = self.client.get(reverse('configuration:goal_list'))
        period_response = self.client.get(
            reverse('configuration:period_create')
        )

        self.assertEqual(goals_response.status_code, 200)
        self.assertContains(goals_response, 'Crear período')
        self.assertContains(goals_response, 'Nuevo período')
        self.assertEqual(period_response.status_code, 200)
        self.assertContains(period_response, 'Fecha de inicio')
        self.assertContains(period_response, 'Fecha de término')
        self.assertContains(period_response, 'Máximo de días computables')
        self.assertContains(period_response, 'Período activo')
