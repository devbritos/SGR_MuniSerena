from io import StringIO
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from atenciones.models import Attention, AttentionType, SubAttention
from core.role_access import can_access
from configuration.models import Period
from datetime import timedelta
from personal.document_roles import PROFILES, profile_permissions
from core.management.commands.configurar_roles_documento import username_for
from personal.models import Delegation, Functionary, Role


class DocumentRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(code='TEST', name='Delegacion de prueba', field='URBANO')
        cls.other = Delegation.objects.create(code='OTHER', name='Otra delegacion', field='RURAL')
        cls.password = 'Test-Password-471!'
        with patch.dict('os.environ', {'SGR_DEMO_PASSWORD': cls.password}):
            call_command('configurar_roles_documento', delegation='TEST', create_users=True, stdout=StringIO())
        cls.attention_type = AttentionType.objects.create(code='SOC', name='Social')
        cls.subattention = SubAttention.objects.create(code='SUB', name='Orientacion', attention_type=cls.attention_type)

    def user(self, username):
        return User.objects.get(username=username)

    def attention(self, username='v.herrera', delegation=None):
        return Attention.objects.create(
            functionary=self.user(username).functionary,
            delegation=delegation or self.delegation,
            attention_type=self.attention_type, sub_attention=self.subattention,
            requester_name='Vecino de prueba', description='Solicitud de prueba',
        )

    def test_seven_accounts_authenticate_without_admin_or_global_privileges(self):
        self.assertEqual(Role.objects.count(), 7)
        self.assertEqual(Functionary.objects.count(), 7)
        for code, title, names, surname, extra in PROFILES:
            with self.subTest(role=code):
                user = authenticate(username=username_for(names, surname), password=self.password)
                self.assertIsNotNone(user)
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertFalse(user.functionary.has_global_scope)
                self.assertEqual(user.functionary.roles_list, [code])
                self.assertEqual(user.get_all_permissions(), profile_permissions(extra))

    def test_username_normalizes_accents_and_uses_first_initial(self):
        self.assertEqual(username_for('Álvaro', 'Pérez'), 'a.perez')

    def test_repeating_command_preserves_accounts_and_passwords(self):
        user = self.user('m.fuentes')
        user.set_password('Changed-Password-957!')
        user.save()
        with patch.dict('os.environ', {'SGR_DEMO_PASSWORD': self.password}):
            call_command('configurar_roles_documento', delegation='TEST', create_users=True, stdout=StringIO())
        self.assertEqual(User.objects.count(), 7)
        self.assertTrue(self.user('m.fuentes').check_password('Changed-Password-957!'))

    def test_dry_run_does_not_create_anything(self):
        Functionary.objects.all().delete()
        User.objects.all().delete()
        Role.objects.update(description='Original')
        with patch.dict('os.environ', {'SGR_DEMO_PASSWORD': self.password}):
            call_command('configurar_roles_documento', delegation='TEST', create_users=True, dry_run=True, stdout=StringIO())
        self.assertFalse(User.objects.exists())
        self.assertFalse(Role.objects.exclude(description='Original').exists())

    def test_collision_rolls_back_instead_of_overwriting_existing_user(self):
        user = self.user('m.fuentes')
        user.email = 'real@example.invalid'
        user.save()
        Role.objects.update(description='Original')
        with patch.dict('os.environ', {'SGR_DEMO_PASSWORD': self.password}):
            with self.assertRaises(CommandError):
                call_command('configurar_roles_documento', delegation='TEST', create_users=True, stdout=StringIO())
        self.assertFalse(Role.objects.exclude(description='Original').exists())
        self.assertEqual(self.user('m.fuentes').email, 'real@example.invalid')

    def test_social_can_create_attention_but_cannot_manage_organizations_or_users(self):
        self.client.force_login(self.user('m.fuentes'))
        self.assertEqual(self.client.get(reverse('atenciones:attention_create')).status_code, 200)
        for route in ('organizations:create', 'personal:functionary_create', 'personal:role_list'):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)
                self.assertEqual(self.client.post(reverse(route), {}).status_code, 403)

    def test_organization_worker_can_manage_registry_but_not_roles(self):
        self.client.force_login(self.user('a.rojas'))
        self.assertEqual(self.client.get(reverse('organizations:create')).status_code, 200)
        self.assertEqual(self.client.get(reverse('personal:role_list')).status_code, 403)

    def test_procurement_does_not_receive_citizen_case_access(self):
        self.client.force_login(self.user('d.castro'))
        self.assertEqual(self.client.get(reverse('atenciones:attention_list')).status_code, 403)
        self.assertEqual(self.client.post(reverse('atenciones:attention_create'), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('correspondence:letter_create')).status_code, 200)
        response = self.client.get(reverse('user_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/atenciones/')
        self.assertNotContains(response, 'href="/organizaciones/')

    def test_planning_read_only_attention_blocks_followup_post_and_hides_actions(self):
        attention = self.attention()
        self.client.force_login(self.user('v.herrera'))
        url = reverse('atenciones:attention_detail', args=[attention.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="followup-form"')
        self.assertNotContains(response, reverse('atenciones:attention_update', args=[attention.pk]))
        self.assertEqual(self.client.post(url, {'note': 'No permitido'}).status_code, 403)
        self.assertFalse(attention.followups.exists())
        self.assertEqual(self.client.get(reverse('atenciones:attention_create')).status_code, 403)

    def test_delegate_has_own_delegation_scope_without_administration(self):
        own = self.attention('m.fuentes')
        other = self.attention('m.fuentes', delegation=self.other)
        self.client.force_login(self.user('c.valdes'))
        self.assertEqual(self.client.get(reverse('atenciones:attention_detail', args=[own.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('atenciones:attention_detail', args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 403)
        self.assertFalse(can_access(self.user('c.valdes'), 'activities:activity_delete'))

    def test_read_only_event_access_cannot_invite_by_post(self):
        user = self.user('m.fuentes')
        self.assertTrue(can_access(user, 'events:organization_invitations'))
        self.assertFalse(can_access(user, 'events:organization_invitations', 'POST'))
        self.assertTrue(can_access(self.user('a.rojas'), 'events:organization_invitations', 'POST'))

    def test_archived_or_inactive_role_does_not_grant_permissions(self):
        role = Role.objects.get(role_name='DOC_SOCIAL')
        role.is_active = False
        role.save()
        self.assertFalse(self.user('m.fuentes').has_perm('atenciones.add_attention'))
        self.assertFalse(can_access(self.user('m.fuentes'), 'atenciones:attention_list'))
        role.is_active = True
        role.deleted_at = timezone.now()
        role.save()
        self.assertFalse(self.user('m.fuentes').has_perm('atenciones.add_attention'))

    def test_unknown_routes_fail_closed_for_document_profile(self):
        self.assertFalse(can_access(self.user('m.fuentes'), 'atenciones:new_unmapped_action', 'POST'))

    def test_all_accounts_can_open_dashboard_and_operational_modules(self):
        for code, title, names, surname, extra in PROFILES:
            self.client.force_login(self.user(username_for(names, surname)))
            for route in ('user_dashboard', 'activities:traffic_light', 'activities:activity_list',
                          'activities:evidence_list', 'agenda:commitment_list', 'agenda:meeting_list'):
                with self.subTest(role=code, route=route):
                    self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_authenticated_root_redirect_still_works(self):
        self.client.force_login(self.user('m.fuentes'))
        response = self.client.get('/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], reverse('user_dashboard'))

    def test_planning_monitors_own_delegation_without_global_scope(self):
        today = timezone.localdate()
        Period.objects.create(
            start_date=today - timedelta(days=5), end_date=today + timedelta(days=5),
            computable_days=11, version_parameter='TEST', minimum_threshold=0,
            maximum_computable_days=11, semaphore='TEST',
        )
        outsider = self.user('j.navarro').functionary
        outsider.delegation = self.other
        outsider.save()
        self.client.force_login(self.user('v.herrera'))
        response = self.client.get(reverse('activities:traffic_light'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Carlos')
        self.assertNotContains(response, 'Javier')
        self.assertEqual(self.client.get(reverse('dashboard_delegation_detail', args=[self.other.pk])).status_code, 403)
