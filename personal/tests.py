from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from .forms import DelegationForm, FunctionaryCustomForm, FunctionaryUpdateForm
from .models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)


class FunctionaryNameValidationTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name='Validación de nombres',
            field='URBANO',
        )
        self.position = Position.objects.create(name='Cargo de prueba')
        self.functionary = Functionary.objects.create(
            names='María José',
            lastnames='Pérez Soto',
            delegation=self.delegation,
            position=self.position,
        )

    def _create_form_data(self, **overrides):
        data = {
            'names': 'María José',
            'lastnames': 'Pérez Soto',
            'delegation': str(self.delegation.pk),
            'position': str(self.position.pk),
            'username': 'usuario_prueba',
            'email': 'usuario@example.com',
            'password': 'Safe-Test-Password-742!',
        }
        data.update(overrides)
        return data

    def _update_form_data(self, **overrides):
        data = {
            'names': 'María José',
            'lastnames': 'Pérez Soto',
            'delegation': str(self.delegation.pk),
            'position': str(self.position.pk),
        }
        data.update(overrides)
        return data

    def test_create_form_rejects_digits_in_names_and_lastnames(self):
        for field, value in (
            ('names', 'María2'),
            ('lastnames', 'Pérez2'),
        ):
            with self.subTest(field=field):
                form = FunctionaryCustomForm(
                    data=self._create_form_data(**{field: value})
                )
                self.assertFalse(form.is_valid())
                self.assertIn('no deben contener números', str(form.errors[field]))

    def test_update_form_rejects_digits_in_names_and_lastnames(self):
        for field, value in (
            ('names', 'María2'),
            ('lastnames', 'Pérez2'),
        ):
            with self.subTest(field=field):
                form = FunctionaryUpdateForm(
                    data=self._update_form_data(**{field: value}),
                    instance=self.functionary,
                )
                self.assertFalse(form.is_valid())
                self.assertIn('no deben contener números', str(form.errors[field]))

    def test_model_validation_rejects_digits_in_names_and_lastnames(self):
        for field, value in (
            ('names', 'María2'),
            ('lastnames', 'Pérez2'),
        ):
            with self.subTest(field=field):
                functionary = Functionary(
                    names='María José',
                    lastnames='Pérez Soto',
                    delegation=self.delegation,
                    position=self.position,
                )
                setattr(functionary, field, value)
                with self.assertRaises(ValidationError):
                    functionary.full_clean()

    def test_create_and_update_forms_accept_accents_and_hyphens(self):
        names = 'María-José'
        lastnames = 'Pérez-Soto'
        create_form = FunctionaryCustomForm(
            data=self._create_form_data(names=names, lastnames=lastnames)
        )
        update_form = FunctionaryUpdateForm(
            data=self._update_form_data(names=names, lastnames=lastnames),
            instance=self.functionary,
        )

        self.assertTrue(create_form.is_valid(), create_form.errors)
        self.assertTrue(update_form.is_valid(), update_form.errors)


class DelegationFormTests(TestCase):
    def test_labels_are_in_spanish_and_validation_required_fields_are_required(self):
        form = DelegationForm()

        self.assertEqual(form.fields['state'].label, 'Estado')
        self.assertEqual(form.fields['field'].label, 'Ámbito territorial')
        self.assertEqual(form.fields['code'].label, 'Código de delegación')
        self.assertTrue(form.fields['code'].required)
        self.assertTrue(form.fields['address'].required)
        self.assertTrue(form.fields['commune'].required)


class FunctionaryFormViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_funcionarios',
            email='admin_funcionarios@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)
        self.delegation = Delegation.objects.create(
            name='Delegación Formularios',
            field='URBANO',
        )
        self.position = Position.objects.create(name='Cargo Formularios')
        self.functionary = Functionary.objects.create(
            delegation=self.delegation,
            position=self.position,
            names='María',
            lastnames='Pérez',
        )

    def test_standard_roles_have_distinct_badges_in_role_catalog(self):
        role_names = (
            Role.ADMIN,
            Role.COORDINATOR,
            Role.DELEGATE,
            Role.FUNCTIONARY,
            Role.VERIFIER,
            Role.READONLY,
            'Administrador',
            'Coordinador del Sistema',
            'Delegado / Jefatura',
            'Funcionario Operativo',
            'Verificador',
            'Usuario de Consulta',
        )
        for role_name in role_names:
            Role.objects.create(role_name=role_name)

        response = self.client.get(reverse('personal:role_list'))

        self.assertEqual(response.status_code, 200)
        for role_class in (
            'role-badge--admin',
            'role-badge--coordinator',
            'role-badge--delegate',
            'role-badge--functionary',
            'role-badge--verifier',
            'role-badge--readonly',
        ):
            self.assertContains(response, role_class)

    def test_delegation_form_has_spanish_labels_and_clear_sections(self):
        response = self.client.get(reverse('personal:delegation_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Crear delegación')
        self.assertContains(response, 'Código de delegación')
        self.assertContains(response, 'Nombre de la delegación')
        self.assertContains(response, 'Ámbito territorial')
        self.assertContains(response, 'Identificación')
        self.assertContains(response, 'Ubicación')
        self.assertContains(response, 'Configuración')
        self.assertNotContains(response, '>State<')
        self.assertNotContains(response, '>Field<')

    def test_create_form_is_presented_in_spanish(self):
        response = self.client.get(reverse('personal:functionary_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nuevo funcionario')
        self.assertContains(response, '/static/images/faroletras.png')
        self.assertContains(response, 'Datos del funcionario')
        self.assertContains(response, 'Acceso al sistema')
        self.assertContains(response, 'Nombres')
        self.assertContains(response, 'Apellidos')
        self.assertContains(response, 'Delegación')
        self.assertContains(response, 'Cargo')
        self.assertContains(response, 'class="role-checkbox-list"')
        self.assertNotContains(
            response,
            'id="id_roles" class="form-check-input"',
        )
        self.assertNotContains(response, '>Names<')
        self.assertNotContains(response, '>Lastnames<')

    def test_shared_menu_has_desktop_pin_control(self):
        response = self.client.get(reverse('personal:functionary_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebarPinToggle"')
        self.assertContains(response, 'id="sidebarMenuToggle"')
        self.assertContains(response, 'sgr-sidebar-pinned')
        self.assertContains(response, 'Fijar menú abierto')
        self.assertContains(
            response,
            'Mantener el menú abierto y ajustar el contenido',
        )

    def test_update_form_is_presented_in_spanish(self):
        response = self.client.get(
            reverse(
                'personal:functionary_update',
                args=[self.functionary.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Editar funcionario')
        self.assertContains(response, 'Roles del sistema')
        self.assertContains(response, 'Funcionario activo')


class FunctionaryRolePermissionTests(TestCase):
    def test_active_role_grants_its_configured_django_permissions(self):
        user = User.objects.create_user(username='usuario_rbac')
        delegation = Delegation.objects.create(name='Delegación RBAC', field='URBANO')
        position = Position.objects.create(name='Cargo RBAC')
        functionary = Functionary.objects.create(
            user=user,
            delegation=delegation,
            position=position,
            names='Usuario',
            lastnames='RBAC',
        )
        role = Role.objects.create(
            role_name=Role.READONLY,
            authorized_scope='DELEGATION',
        )
        permission = Permission.objects.get(
            content_type__app_label='activities',
            codename='view_activity',
        )
        role.permissions.add(permission)
        FunctionaryRole.objects.create(functionary=functionary, role=role)

        self.assertTrue(user.has_perm('activities.view_activity'))

        role.is_active = False
        role.save(update_fields=['is_active'])
        user = User.objects.get(pk=user.pk)
        self.assertFalse(user.has_perm('activities.view_activity'))


class RoleCatalogTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_roles',
            email='admin_roles@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)

    def test_admin_can_create_update_and_deactivate_roles(self):
        response = self.client.get(reverse('personal:role_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('personal:role_create'))
        self.assertContains(response, 'Roles y permisos')

        response = self.client.post(
            reverse('personal:role_create'),
            {
                'role_name': Role.READONLY,
                'description': 'Acceso de consulta',
                'authorized_scope': 'DELEGATION',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('personal:role_list'))
        role = Role.objects.get(role_name=Role.READONLY)
        self.assertEqual(role.description, 'Acceso de consulta')

        response = self.client.post(
            reverse('personal:role_update', args=[role.pk]),
            {
                'role_name': Role.READONLY,
                'description': 'Consulta de la delegación asignada',
                'authorized_scope': 'GLOBAL',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('personal:role_list'))
        role.refresh_from_db()
        self.assertEqual(
            role.description,
            'Consulta de la delegación asignada',
        )
        self.assertEqual(role.authorized_scope, 'GLOBAL')

        response = self.client.post(
            reverse('personal:role_delete', args=[role.pk]),
        )
        self.assertRedirects(response, reverse('personal:role_list'))
        role.refresh_from_db()
        self.assertFalse(role.is_active)

    def test_role_edit_form_preselects_current_role_and_permissions(self):
        role = Role.objects.create(
            role_name=Role.READONLY,
            description='Solo consulta',
            authorized_scope='DELEGATION',
        )
        permission = Permission.objects.get(
            content_type__app_label='activities',
            codename='view_activity',
        )
        role.permissions.add(permission)

        response = self.client.get(
            reverse('personal:role_update', args=[role.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['form']['role_name'].value(),
            'Usuario de Consulta',
        )
        self.assertEqual(
            response.context['form']['authorized_scope'].value(),
            'DELEGATION',
        )
        self.assertEqual(
            response.context['form']['permissions'].value(),
            [permission.pk],
        )
        self.assertContains(
            response,
            'value="Usuario de Consulta"',
        )
        self.assertContains(response, 'id="permission-search"')
        self.assertContains(response, 'Marcar visibles')
        self.assertContains(
            response,
            f'id="permission-{permission.pk}"',
        )
        self.assertRegex(
            response.content.decode(),
            rf'id="permission-{permission.pk}"\s+checked',
        )

    def test_role_form_saves_selected_permissions(self):
        permission = Permission.objects.get(
            content_type__app_label='activities',
            codename='view_activity',
        )

        response = self.client.post(
            reverse('personal:role_create'),
            {
                'role_name': 'Analista de seguimiento',
                'description': 'Consulta actividades.',
                'authorized_scope': 'DELEGATION',
                'permissions': [str(permission.pk)],
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('personal:role_list'))
        role = Role.objects.get(role_name='Analista de seguimiento')
        self.assertQuerySetEqual(
            role.permissions.all(),
            [permission],
            transform=lambda item: item,
        )

    def test_role_form_preserves_selected_permissions_after_validation_error(self):
        role = Role.objects.create(role_name=Role.READONLY)
        permission = Permission.objects.get(
            content_type__app_label='activities',
            codename='view_activity',
        )

        response = self.client.post(
            reverse('personal:role_update', args=[role.pk]),
            {
                'role_name': '',
                'description': 'Solo consulta',
                'authorized_scope': 'DELEGATION',
                'permissions': [str(permission.pk)],
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode(),
            rf'id="permission-{permission.pk}"\s+checked',
        )

    def test_role_edit_keeps_legacy_role_selected(self):
        role = Role.objects.create(role_name='Administrador')

        response = self.client.get(
            reverse('personal:role_update', args=[role.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['form']['role_name'].value(),
            'Administrador',
        )
        self.assertContains(response, 'value="Administrador"')

    def test_admin_can_create_custom_role_by_typing_its_name(self):
        response = self.client.get(reverse('personal:role_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'placeholder="Ej.: Analista de proyectos"')
        self.assertContains(response, 'standard-role-names')
        self.assertNotContains(response, '<select name="role_name"')

        response = self.client.post(
            reverse('personal:role_create'),
            {
                'role_name': 'Analista de proyectos',
                'description': 'Consulta y seguimiento de proyectos.',
                'authorized_scope': 'DELEGATION',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('personal:role_list'))
        role = Role.objects.get(role_name='Analista de proyectos')
        self.assertEqual(role.get_role_name_display(), 'Analista de proyectos')
        functionary = Functionary.objects.create(
            delegation=Delegation.objects.create(
                name='Delegación rol personalizado',
                field='URBANO',
            ),
            position=Position.objects.create(name='Cargo rol personalizado'),
            names='Funcionario',
            lastnames='Prueba',
        )
        FunctionaryRole.objects.create(functionary=functionary, role=role)
        self.assertFalse(functionary.is_admin)

    def test_standard_role_name_keeps_its_internal_code(self):
        response = self.client.post(
            reverse('personal:role_create'),
            {
                'role_name': 'Verificador',
                'description': 'Rol estándar.',
                'authorized_scope': 'DELEGATION',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('personal:role_list'))
        self.assertTrue(Role.objects.filter(role_name=Role.VERIFIER).exists())
