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
        self.assertContains(response, 'images/laserena.png')
        self.assertContains(response, 'dashboard-shortcut')
        self.assertContains(response, 'dashboard-priority')
        self.assertContains(response, 'dashboard-goal-card')
        self.assertContains(response, 'Menú de Panel Prueba')
        self.assertContains(
            response,
            '<span class="d-none d-sm-inline user-display-name">Panel Prueba</span>',
        )

    def test_user_goal_cards_only_show_the_assigned_position(self):
        other_position = Position.objects.create(name='Cargo no asignado')
        other_measuring = Measuring.objects.create(
            service='Atención exclusiva de otro cargo',
            measurable_item='Atenciones',
        )
        Goal.objects.create(
            target_value=4,
            weight=100,
            unity='atenciones',
            validity=True,
            position=other_position,
            period=self.period,
            measuring=other_measuring,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('user_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['measuring'] for item in response.context['indicador']['items']],
            [self.measuring],
        )
        self.assertContains(response, self.measuring.service)
        self.assertNotContains(response, other_measuring.service)

    def test_site_root_redirects_functionary_to_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get('/', follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0],
            reverse('user_dashboard'),
        )

    def test_staff_login_redirects_to_management_dashboard(self):
        response = self.client.post(
            reverse('login'),
            {'username': self.staff.username, 'password': 'test-password'},
        )

        self.assertRedirects(
            response,
            reverse('admin_dashboard'),
            fetch_redirect_response=False,
        )

    def test_functionary_login_redirects_to_personal_dashboard(self):
        response = self.client.post(
            reverse('login'),
            {'username': self.user.username, 'password': 'test-password'},
        )

        self.assertRedirects(
            response,
            reverse('user_dashboard'),
            fetch_redirect_response=False,
        )

    def test_login_keeps_an_explicit_safe_next_destination(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': self.staff.username,
                'password': 'test-password',
                'next': reverse('dashboard_redirect'),
            },
        )

        self.assertRedirects(
            response,
            reverse('dashboard_redirect'),
            fetch_redirect_response=False,
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
        self.assertContains(response, 'Hola, dashboard_admin')
        self.assertContains(response, 'Accesos rápidos')
        self.assertContains(response, 'Pendientes que requieren atención')
        self.assertContains(response, 'images/laserena.png')
        self.assertContains(response, 'Semáforo')
        self.assertContains(response, reverse('agenda:commitment_list'))
        self.assertNotContains(response, reverse('personal:functionary_list'))

    def test_admin_dashboard_links_to_delegation_summary(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Semáforo por delegación')
        self.assertContains(response, reverse('dashboard_redirect'))
        self.assertContains(
            response,
            f'class="navbar-brand d-flex align-items-center me-auto" href="{reverse("admin_dashboard")}"',
        )

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

        response = self.client.get(reverse('dashboard_redirect'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Semáforo por delegación')
        self.assertContains(response, reverse('personal:functionary_list'))
        self.assertContains(response, reverse('personal:delegation_list'))

    def test_delegation_dashboard_averages_and_links_to_scoped_detail(self):
        second_functionary = Functionary.objects.create(
            delegation=self.delegation,
            position=self.position,
            names='Segundo',
            lastnames='Funcionario',
        )
        other_delegation = Delegation.objects.create(
            name='Delegación sin metas',
            code='DP-02',
            field='RURAL',
        )
        other_position = Position.objects.create(name='Cargo sin metas')
        other_functionary = Functionary.objects.create(
            delegation=other_delegation,
            position=other_position,
            names='Otro',
            lastnames='Funcionario',
        )
        self.client.force_login(self.staff)

        dashboard_response = self.client.get(reverse('dashboard_redirect'))

        self.assertEqual(dashboard_response.status_code, 200)
        summaries = {
            item['delegation'].pk: item
            for item in dashboard_response.context['delegation_summaries']
        }
        self.assertEqual(len(summaries), 2)
        self.assertEqual(
            summaries[self.delegation.pk]['average_percentage'],
            30.0,
        )
        self.assertEqual(
            summaries[self.delegation.pk]['measured_functionary_count'],
            2,
        )
        self.assertEqual(summaries[self.delegation.pk]['status'], 'red')
        self.assertIsNone(
            summaries[other_delegation.pk]['average_percentage'],
        )
        self.assertEqual(summaries[other_delegation.pk]['status'], 'no_goal')
        self.assertContains(dashboard_response, 'delegation-card--red')
        self.assertContains(dashboard_response, 'delegation-card--no_goal')
        self.assertContains(dashboard_response, 'delegation-progress-marker')
        self.assertContains(
            dashboard_response,
            reverse(
                'dashboard_delegation_detail',
                args=[self.delegation.pk],
            ),
        )

        detail_response = self.client.get(
            reverse(
                'dashboard_delegation_detail',
                args=[self.delegation.pk],
            ),
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context['delegation'], self.delegation)
        self.assertEqual(
            {
                item['functionary'].pk
                for item in detail_response.context['traffic_light_data']
            },
            {self.functionary.pk, second_functionary.pk},
        )
        self.assertNotContains(detail_response, other_functionary.full_name)
        self.assertContains(detail_response, 'Volver a delegaciones')

    def test_delegation_dashboard_can_select_a_historical_period(self):
        today = timezone.localdate()
        historical_period = Period.objects.create(
            start_date=today - timedelta(days=35),
            end_date=today - timedelta(days=25),
            computable_days=11,
            status=False,
            version_parameter='0',
            minimum_threshold=0,
            maximum_computable_days=11,
            semaphore='SGR',
        )
        Goal.objects.create(
            target_value=10,
            weight=100,
            unity='atenciones',
            validity=True,
            position=self.position,
            period=historical_period,
            measuring=self.measuring,
        )
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse('dashboard_redirect'),
            {'period': historical_period.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['period'], historical_period)
        self.assertContains(
            response,
            f'value="{historical_period.pk}" selected',
        )
        self.assertContains(
            response,
            f'{reverse("dashboard_delegation_detail", args=[self.delegation.pk])}?period={historical_period.pk}',
        )

        detail_response = self.client.get(
            reverse(
                'dashboard_delegation_detail',
                args=[self.delegation.pk],
            ),
            {'period': historical_period.pk},
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context['period'], historical_period)

    def test_delegation_dashboard_orders_filters_and_paginates(self):
        larger_delegation = Delegation.objects.create(
            name='Delegación con más funcionarios',
            code='DP-03',
            field='RURAL',
        )
        empty_delegation = Delegation.objects.create(
            name='Delegación vacía',
            code='DP-04',
            field='RURAL',
        )
        for name in ('Ana', 'Beto', 'Carla'):
            Functionary.objects.create(
                delegation=larger_delegation,
                position=self.position,
                names=name,
                lastnames='Delegación grande',
            )
        self.client.force_login(self.staff)

        first_page = self.client.get(
            reverse('dashboard_redirect'),
            {'q': 'DP-', 'funcionarios': 'con', 'per_page': 1},
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(
            first_page.context['delegation_summaries'][0]['delegation'],
            larger_delegation,
        )
        self.assertEqual(first_page.context['page_obj'].paginator.count, 2)
        self.assertEqual(first_page.context['page_size_options'], (1, 3))

        second_page = self.client.get(
            reverse('dashboard_redirect'),
            {
                'q': 'DP-',
                'funcionarios': 'con',
                'per_page': 1,
                'page': 2,
            },
        )

        self.assertEqual(
            second_page.context['delegation_summaries'][0]['delegation'],
            self.delegation,
        )
        self.assertTrue(second_page.context['page_obj'].has_previous())
        self.assertNotEqual(
            second_page.context['delegation_summaries'][0]['delegation'],
            empty_delegation,
        )

    def test_functionary_cannot_open_global_or_other_delegation_dashboard(self):
        self.client.force_login(self.user)

        dashboard_response = self.client.get(reverse('dashboard_redirect'))
        detail_response = self.client.get(
            reverse(
                'dashboard_delegation_detail',
                args=[self.delegation.pk],
            ),
        )

        self.assertRedirects(
            dashboard_response,
            reverse('user_dashboard'),
        )
        self.assertEqual(detail_response.status_code, 403)

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
        self.assertContains(response, reverse('dashboard_redirect'))
        self.assertContains(response, reverse('admin_dashboard'))
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
