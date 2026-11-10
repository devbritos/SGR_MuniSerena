from datetime import timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from activities.models import Activity, Evidence
from agenda.models import Commitment
from configuration.models import Goal, Measuring, Period
from personal.models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)


class DashboardTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.staff = User.objects.create_user(
            username='dashboard_admin',
            password='test-password',
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username='dashboard_functionary',
            password='test-password',
        )
        self.delegation = Delegation.objects.create(
            name='Delegación panel',
            code='DP-01',
            field='URBANO',
        )
        self.position = Position.objects.create(name='Cargo panel')
        self.functionary = Functionary.objects.create(
            user=self.user,
            delegation=self.delegation,
            position=self.position,
            names='Panel',
            lastnames='Prueba',
        )
        self.measuring = Measuring.objects.create(
            service='Atención territorial',
            measurable_item='Atenciones',
        )
        self.period = Period.objects.create(
            start_date=today.replace(day=1),
            end_date=today + timedelta(days=10),
            computable_days=30,
            status=True,
            version_parameter='1',
            minimum_threshold=0,
            maximum_computable_days=30,
            semaphore='SGR',
        )
        Goal.objects.create(
            target_value=5,
            weight=100,
            unity='atenciones',
            validity=True,
            position=self.position,
            period=self.period,
            measuring=self.measuring,
        )
        self.validated_activity = Activity.objects.create(
            date=today,
            application='Actividad validada',
            taken_action='Gestión realizada',
            name_contact='Contacto',
            telephone_contact='12345678',
            quantity=3,
            state_validity='VALIDATED',
            functionary=self.functionary,
            measuring=self.measuring,
        )
        Evidence.objects.create(
            name='Respaldo de actividad validada',
            author='Funcionario panel',
            date_evidence=today,
            metadata='Evidencia aprobada de prueba.',
            file='evidences/dashboard-test.pdf',
            validity_state=Evidence.Validity.APPROVED,
            date_validity=today,
            activity=self.validated_activity,
            functionary=self.functionary,
        )
        self.pending_activity = Activity.objects.create(
            date=today,
            application='Actividad por validar',
            taken_action='Gestión en revisión',
            name_contact='Contacto',
            telephone_contact='12345678',
            quantity=2,
            state_validity='PENDING',
            functionary=self.functionary,
            measuring=self.measuring,
        )
        Commitment.objects.create(
            origin='Solicitud vencida',
            applic_name='Solicitante',
            territory='Sector',
            commitment_date=today - timedelta(days=1),
            state=Commitment.State.JOINED,
            functionary=self.functionary,
        )

    def test_user_dashboard_shows_current_activity_and_validated_quantity(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('user_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['actividades_mes'], 2)
        self.assertEqual(response.context['actividades_por_validar'], 1)
        self.assertEqual(
            response.context['indicador']['items'][0]['avance'],
            3,
        )
        self.assertContains(response, 'id="sidebarPinToggle"')
        self.assertContains(response, 'Actividad por validar')
        self.assertContains(response, 'Atención territorial')
        self.assertContains(response, 'images/serena.png')

    def test_site_root_redirects_functionary_to_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get('/', follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0],
            reverse('user_dashboard'),
        )

    def test_admin_dashboard_shows_live_system_totals(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_funcionarios'], 1)
        self.assertEqual(response.context['total_delegaciones'], 1)
        self.assertEqual(response.context['compromisos_pendientes'], 1)
        self.assertEqual(response.context['compromisos_vencidos'], 1)
        self.assertEqual(response.context['actividades_mes'], 2)
        self.assertEqual(response.context['actividades_por_validar'], 1)
        self.assertContains(response, 'Actividad validada')
        self.assertContains(response, 'Solicitud vencida')
        self.assertContains(response, 'images/serena.png')

    def test_functionary_with_admin_role_can_open_admin_dashboard(self):
        admin_user = User.objects.create_user(
            username='dashboard_role_admin',
            password='test-password',
        )
        admin_functionary = Functionary.objects.create(
            user=admin_user,
            delegation=self.delegation,
            position=self.position,
            names='Admin',
            lastnames='Panel',
        )
        admin_role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(
            functionary=admin_functionary,
            role=admin_role,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse('dashboard_redirect'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0],
            reverse('admin_dashboard'),
        )
        self.assertContains(response, 'Panel de control')

    def test_functionary_menu_shows_operational_sections_without_admin_links(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('user_dashboard'))

        self.assertEqual(response.status_code, 200)
        for route_name in (
            'activities:activity_list',
            'activities:evidence_list',
            'agenda:commitment_list',
            'atenciones:attention_list',
        ):
            self.assertContains(response, reverse(route_name))
        self.assertNotContains(response, reverse('personal:functionary_list'))

    def test_staff_menu_does_not_show_admin_routes_the_staff_role_cannot_open(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('activities:traffic_light'))
        html = response.content.decode()
        functionary_list_url = reverse('personal:functionary_list')
        goals_url = reverse('configuration:goal_list')
        self.assertNotIn(
            f'href="{functionary_list_url}" class="sidebar-link',
            html,
        )
        self.assertNotIn(
            f'href="{goals_url}" class="sidebar-link',
            html,
        )

    def test_inactive_admin_functionary_cannot_open_admin_dashboard_or_menu(self):
        inactive_admin = User.objects.create_user(
            username='inactive_dashboard_admin',
            password='test-password',
        )
        functionary = Functionary.objects.create(
            user=inactive_admin,
            delegation=self.delegation,
            position=self.position,
            names='Admin',
            lastnames='Inactivo',
            is_active=False,
        )
        admin_role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(functionary=functionary, role=admin_role)
        self.client.force_login(inactive_admin)

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse('personal:profile_update'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('configuration:goal_list'))
        self.assertNotContains(response, reverse('personal:functionary_list'))
