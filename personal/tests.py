import base64
from io import BytesIO
import os
import tempfile

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .forms import (
    DelegationForm,
    FunctionaryCustomForm,
    FunctionaryUpdateForm,
    ProfilePhotoForm,
)
from .models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
    UserProfile,
)
from .validators import validate_profile_photo


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

    def test_form_rejects_case_insensitive_duplicate_names_and_codes(self):
        Delegation.objects.create(
            name='Delegación Central',
            code='DEL-CENTRAL',
            address='Calle Uno 1',
            commune='Centro',
            state='ACTIVO',
            field='URBANO',
        )
        for field, value in (
            ('name', 'delegación central'),
            ('code', 'del-central'),
        ):
            with self.subTest(field=field):
                data = {
                    'name': 'Delegación Nueva',
                    'code': 'DEL-NUEVA',
                    'address': 'Calle Dos 2',
                    'commune': 'Norte',
                    'state': 'ACTIVO',
                    'field': 'RURAL',
                }
                data[field] = value
                form = DelegationForm(data=data)

                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_form_rejects_missing_required_fields(self):
        form = DelegationForm(data={
            'name': '',
            'code': '',
            'address': '',
            'commune': '',
            'state': 'ACTIVO',
            'field': 'URBANO',
        })

        self.assertFalse(form.is_valid())
        for field in ('name', 'code', 'address', 'commune'):
            self.assertIn(field, form.errors)


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

    def test_functionary_list_sorts_and_selects_page_size(self):
        first = Functionary.objects.create(
            delegation=self.delegation,
            position=self.position,
            names='Alfa',
            lastnames='Prueba',
        )
        last = Functionary.objects.create(
            delegation=self.delegation,
            position=self.position,
            names='Zulu',
            lastnames='Prueba',
        )

        response = self.client.get(
            reverse('personal:functionary_list'),
            {'sort': 'name_za', 'per_page': '30'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_page_size'], 30)
        self.assertEqual(response.context['page_obj'].paginator.per_page, 30)
        results = list(response.context['object_list'])
        self.assertEqual(results[0].pk, last.pk)
        self.assertEqual(results[-1].pk, first.pk)

    def test_functionary_list_restores_its_state_after_visiting_detail(self):
        list_url = reverse('personal:functionary_list')
        response = self.client.get(
            list_url,
            {
                'q': 'María',
                'status': 'active',
                'sort': 'name_az',
                'per_page': '5',
            },
        )
        self.assertEqual(response.status_code, 200)

        detail_response = self.client.get(
            reverse(
                'personal:functionary_detail',
                kwargs={'pk': self.functionary.pk},
            )
        )
        self.assertEqual(detail_response.status_code, 200)

        restored = self.client.get(list_url)

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.context['search_query'], 'María')
        self.assertEqual(restored.context['selected_page_size'], 5)
        self.assertEqual(restored.context['selected_sort'], 'name_az')
        self.assertEqual(restored.context['page_obj'].number, 1)

    def test_changing_search_resets_functionary_page_to_one(self):
        for index in range(7):
            Functionary.objects.create(
                delegation=self.delegation,
                position=self.position,
                names=f'Funcionario {index}',
                lastnames='Prueba',
            )

        response = self.client.get(
            reverse('personal:functionary_list'),
            {'all': '1', 'per_page': '5', 'page': '2', 'sort': 'recent'},
        )
        self.assertEqual(response.context['page_obj'].number, 2)

        changed_search = self.client.get(
            reverse('personal:functionary_list'),
            {
                'all': '1',
                'per_page': '5',
                'page': '2',
                'sort': 'recent',
                'q': 'sin coincidencias',
            },
        )

        self.assertEqual(changed_search.context['page_obj'].number, 1)
        self.assertEqual(changed_search.context['page_obj'].paginator.count, 0)

    def test_invalid_page_size_falls_back_to_fifteen(self):
        response = self.client.get(
            reverse('personal:functionary_list'),
            {'per_page': '100'},
        )

        self.assertEqual(response.context['selected_page_size'], 15)
        self.assertEqual(response.context['page_obj'].paginator.per_page, 15)

    def test_functionary_form_rejects_duplicate_name_and_out_of_scope_delegation(self):
        duplicate_data = {
            'names': self.functionary.names,
            'lastnames': self.functionary.lastnames,
            'delegation': str(self.delegation.pk),
            'position': str(self.position.pk),
            'username': 'duplicate_name',
            'email': 'duplicate_name@example.com',
            'password': 'Safe-Test-Password-742!',
        }
        duplicate_form = FunctionaryCustomForm(data=duplicate_data)
        self.assertFalse(duplicate_form.is_valid())
        self.assertIn('lastnames', duplicate_form.errors)

        other_delegation = Delegation.objects.create(
            name='Delegación Fuera de Alcance',
            field='URBANO',
        )
        scoped_form = FunctionaryCustomForm(
            data={
                **duplicate_data,
                'names': 'Nombre Distinto',
                'lastnames': 'Apellido Distinto',
                'username': 'fuera_de_alcance',
                'email': 'fuera@example.com',
                'delegation': str(other_delegation.pk),
            },
            authorized_delegations=Delegation.objects.filter(
                pk=self.delegation.pk,
            ),
        )
        self.assertFalse(scoped_form.is_valid())
        self.assertIn('delegation', scoped_form.errors)

    def test_archiving_functionary_is_post_only_and_persists_deleted_at(self):
        delete_url = reverse(
            'personal:functionary_delete',
            kwargs={'pk': self.functionary.pk},
        )

        confirmation = self.client.get(delete_url)
        self.assertEqual(confirmation.status_code, 200)
        self.functionary.refresh_from_db()
        self.assertIsNone(self.functionary.deleted_at)

        response = self.client.post(delete_url)

        self.assertRedirects(response, reverse('personal:functionary_list'))
        self.functionary.refresh_from_db()
        self.assertIsNotNone(self.functionary.deleted_at)
        self.assertFalse(self.functionary.is_active)

    def test_functionary_export_includes_all_filtered_pages_but_not_archived_rows(self):
        for index in range(17):
            Functionary.objects.create(
                delegation=self.delegation,
                position=self.position,
                names=f'Exportable {index}',
                lastnames='Prueba',
            )
        archived = Functionary.objects.create(
            delegation=self.delegation,
            position=self.position,
            names='Exportable Archivado',
            lastnames='Prueba',
            is_active=False,
            deleted_at=timezone.now(),
        )

        response = self.client.get(
            reverse('personal:functionary_list'),
            {
                'q': 'Exportable',
                'all': '1',
                'per_page': '5',
                'export': 'xlsx',
            },
        )

        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        rows = list(workbook.active.values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 18)
        self.assertNotIn(archived.full_name, {row[0] for row in rows[1:]})
        workbook.close()

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


class DelegationCRUDViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='delegation_crud_admin',
            email='delegation_crud_admin@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)
        self.delegation = Delegation.objects.create(
            name='Delegación Inicial',
            code='DEL-INI',
            address='Calle Principal 10',
            commune='Centro',
            state='ACTIVO',
            field='URBANO',
        )

    @staticmethod
    def _form_data(**overrides):
        data = {
            'name': 'Delegación Nueva',
            'code': 'DEL-NUE',
            'address': 'Calle Nueva 20',
            'commune': 'Norte',
            'state': 'ACTIVO',
            'field': 'RURAL',
        }
        data.update(overrides)
        return data

    def test_create_detail_update_and_archive_delegation(self):
        list_url = reverse('personal:delegation_list')
        create_response = self.client.post(
            reverse('personal:delegation_create'),
            self._form_data(),
        )
        self.assertRedirects(create_response, list_url)
        delegation = Delegation.objects.get(code='DEL-NUE')

        detail_response = self.client.get(
            reverse('personal:delegation_detail', args=[delegation.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Delegación Nueva')

        update_response = self.client.post(
            reverse('personal:delegation_update', args=[delegation.pk]),
            self._form_data(
                name='Delegación Actualizada',
                code='DEL-ACT',
            ),
        )
        self.assertRedirects(update_response, list_url)
        delegation.refresh_from_db()
        self.assertEqual(delegation.name, 'Delegación Actualizada')

        delete_url = reverse('personal:delegation_delete', args=[delegation.pk])
        confirmation = self.client.get(delete_url)
        self.assertEqual(confirmation.status_code, 200)
        delegation.refresh_from_db()
        self.assertIsNone(delegation.deleted_at)

        archive_response = self.client.post(delete_url)
        self.assertRedirects(archive_response, list_url)
        delegation.refresh_from_db()
        self.assertIsNotNone(delegation.deleted_at)
        self.assertEqual(delegation.state, 'INACTIVO')

        ordinary_list = self.client.get(list_url)
        self.assertNotContains(ordinary_list, 'Delegación Actualizada')
        archived_list = self.client.get(list_url, {'all': '1'})
        self.assertContains(archived_list, 'Delegación Actualizada')

    def test_invalid_delegation_form_does_not_save_and_retains_valid_values(self):
        response = self.client.post(
            reverse('personal:delegation_create'),
            self._form_data(
                name='Delegación Inicial',
                code='DEL-NUE',
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya existe una delegación con ese nombre')
        self.assertContains(response, 'DEL-NUE')
        self.assertFalse(Delegation.objects.filter(code='DEL-NUE').exists())

    def test_delegation_archive_is_blocked_while_active_functionaries_remain(self):
        position = Position.objects.create(name='Cargo activo')
        Functionary.objects.create(
            delegation=self.delegation,
            position=position,
            names='Funcionario',
            lastnames='Activo',
        )

        response = self.client.post(
            reverse('personal:delegation_delete', args=[self.delegation.pk])
        )

        self.assertRedirects(response, reverse('personal:delegation_list'))
        self.delegation.refresh_from_db()
        self.assertIsNone(self.delegation.deleted_at)
        self.assertEqual(self.delegation.state, 'ACTIVO')
        self.assertContains(
            self.client.get(reverse('personal:delegation_list')),
            'No se puede archivar esta delegación',
        )

    def test_delegation_list_restores_search_and_order_after_detail(self):
        list_url = reverse('personal:delegation_list')
        response = self.client.get(
            list_url,
            {'q': 'Inicial', 'field': 'URBANO', 'sort': 'name_za', 'per_page': '5'},
        )
        self.assertEqual(response.status_code, 200)

        detail_response = self.client.get(
            reverse('personal:delegation_detail', args=[self.delegation.pk])
        )
        self.assertEqual(detail_response.status_code, 200)

        restored = self.client.get(list_url)
        self.assertEqual(restored.context['search_query'], 'Inicial')
        self.assertEqual(restored.context['selected_field'], 'URBANO')
        self.assertEqual(restored.context['selected_sort'], 'name_za')
        self.assertEqual(restored.context['selected_page_size'], 5)

    def test_delegation_export_contains_every_filtered_page_and_excludes_archived(self):
        for index in range(17):
            Delegation.objects.create(
                name=f'Export Norte {index}',
                code=f'EXP-{index}',
                address=f'Calle {index}',
                commune='Norte',
                state='ACTIVO',
                field='RURAL',
            )
        Delegation.objects.create(
            name='Export Norte Archivada',
            code='EXP-ARCH',
            address='Calle Archivada',
            commune='Norte',
            state='INACTIVO',
            field='RURAL',
            deleted_at=timezone.now(),
        )

        response = self.client.get(
            reverse('personal:delegation_list'),
            {
                'q': 'Export Norte',
                'field': 'RURAL',
                'all': '1',
                'per_page': '5',
                'export': 'xlsx',
            },
        )

        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        rows = list(workbook.active.values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 18)
        self.assertNotIn('Export Norte Archivada', {row[1] for row in rows[1:]})
        workbook.close()


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


class ProfilePhotoViewTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = User.objects.create_user(
            username='profile_owner',
            password='test-password',
        )
        self.client.force_login(self.user)

    @staticmethod
    def _image_data_uri(color='red', size=(512, 512), mime='jpeg'):
        image = Image.new('RGB', size, color)
        output = BytesIO()
        image.save(output, format=mime.upper())
        encoded = base64.b64encode(output.getvalue()).decode('ascii')
        return f'data:image/{mime};base64,{encoded}'

    def _post_photo(self, image_data=None, **extra_data):
        data = {'cropped_image': image_data or self._image_data_uri()}
        data.update(extra_data)
        return self.client.post(reverse('personal:profile_update'), data)

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get(reverse('personal:profile_update'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_profile_page_exposes_cropper_and_preview_controls(self):
        response = self.client.get(reverse('personal:profile_update'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'croppr@2.3.1/dist/croppr.min.js')
        self.assertContains(response, 'id="photoFile"')
        self.assertContains(response, 'id="cropPreview"')

    def test_profile_photo_is_displayed_in_the_navigation_bar(self):
        response = self._post_photo()

        self.assertRedirects(response, reverse('personal:profile_update'))
        response = self.client.get(reverse('personal:profile_update'))

        self.assertContains(
            response,
            f'<img class="user-menu-avatar rounded-circle" src="{reverse("personal:profile_photo")}" alt="">',
        )

    def test_functionary_list_displays_profile_photo_through_authorized_view(self):
        delegation = Delegation.objects.create(
            name='Delegación Foto',
            field='URBANO',
        )
        position = Position.objects.create(name='Cargo Foto')
        Functionary.objects.create(
            user=self.user,
            delegation=delegation,
            position=position,
            names='Perfil',
            lastnames='Con Foto',
        )
        profile = UserProfile.objects.create(user=self.user)
        profile.photo.save(
            'profile.jpg',
            ContentFile(
                validate_profile_photo(
                    base64.b64decode(
                        self._image_data_uri().split(',', 1)[1]
                    )
                )
            ),
        )
        admin = User.objects.create_superuser(
            username='admin_profile_list',
            email='admin_profile_list@example.com',
            password='test-password',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('personal:functionary_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                'personal:functionary_photo',
                kwargs={'pk': Functionary.objects.get(user=self.user).pk},
            ),
        )
        self.assertContains(response, 'alt="Foto de Perfil Con Foto"')

        photo_response = self.client.get(
            reverse(
                'personal:functionary_photo',
                kwargs={'pk': Functionary.objects.get(user=self.user).pk},
            )
        )
        self.assertEqual(photo_response.status_code, 200)
        self.assertEqual(photo_response['Content-Type'], 'image/jpeg')
        photo_response.close()

    def test_profile_photo_form_accepts_multipart_jpeg_source_and_saves_crop(self):
        source = Image.new('RGB', (512, 256), 'blue')
        source_data = BytesIO()
        source.save(source_data, format='JPEG')
        source_file = SimpleUploadedFile(
            'foto.jpg',
            source_data.getvalue(),
            content_type='image/jpeg',
        )

        response = self.client.post(
            reverse('personal:profile_update'),
            {
                'cropped_image': self._image_data_uri('red'),
                'photo_upload': source_file,
            },
        )

        self.assertRedirects(response, reverse('personal:profile_update'))
        profile = UserProfile.objects.get(user=self.user)
        with Image.open(profile.photo.path) as saved_image:
            self.assertEqual(saved_image.size, (512, 512))
            self.assertEqual(saved_image.getpixel((256, 256))[0], 254)

    def test_profile_photo_rejects_non_jpeg_or_png_upload(self):
        gif = Image.new('RGB', (512, 512), 'red')
        gif_data = BytesIO()
        gif.save(gif_data, format='GIF')
        upload = SimpleUploadedFile(
            'foto.gif',
            gif_data.getvalue(),
            content_type='image/gif',
        )
        form = ProfilePhotoForm(
            data={'cropped_image': self._image_data_uri()},
            files={'photo_upload': upload},
        )

        self.assertFalse(form.is_valid())
        self.assertIn('JPG o PNG', str(form.errors))

    def test_profile_photo_rejects_uploads_larger_than_two_mib(self):
        source = Image.frombytes(
            'RGB',
            (1024, 1024),
            os.urandom(1024 * 1024 * 3),
        )
        source_data = BytesIO()
        source.save(source_data, format='PNG')
        self.assertGreater(len(source_data.getvalue()), 2 * 1024 * 1024)
        upload = SimpleUploadedFile(
            'foto.png',
            source_data.getvalue(),
            content_type='image/png',
        )
        form = ProfilePhotoForm(
            data={'cropped_image': self._image_data_uri()},
            files={'photo_upload': upload},
        )

        self.assertFalse(form.is_valid())
        self.assertIn('no puede superar 2 MiB', str(form.errors))

    def test_functionary_photo_requires_list_permission(self):
        delegation = Delegation.objects.create(
            name='Delegación Foto Restringida',
            field='URBANO',
        )
        position = Position.objects.create(name='Cargo Foto Restringida')
        functionary = Functionary.objects.create(
            user=self.user,
            delegation=delegation,
            position=position,
            names='Perfil',
            lastnames='Restringido',
        )

        response = self.client.get(
            reverse(
                'personal:functionary_photo',
                kwargs={'pk': functionary.pk},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_crop_is_saved_as_the_persisted_square_photo(self):
        response = self._post_photo()

        self.assertRedirects(response, reverse('personal:profile_update'))
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.photo)
        with Image.open(profile.photo.path) as saved_image:
            self.assertEqual(saved_image.format, 'JPEG')
            self.assertEqual(saved_image.size, (512, 512))

        response = self.client.get(reverse('personal:profile_photo'))
        self.assertEqual(response.status_code, 200)
        with Image.open(BytesIO(b''.join(response.streaming_content))) as photo:
            self.assertEqual(photo.size, (512, 512))

    def test_empty_submission_preserves_existing_photo(self):
        self._post_photo()
        profile = UserProfile.objects.get(user=self.user)
        original_name = profile.photo.name

        response = self.client.post(
            reverse('personal:profile_update'),
            {'cropped_image': ''},
        )

        self.assertRedirects(response, reverse('personal:profile_update'))
        profile.refresh_from_db()
        self.assertEqual(profile.photo.name, original_name)

    def test_replacing_photo_removes_the_previous_file(self):
        self._post_photo(self._image_data_uri('red'))
        profile = UserProfile.objects.get(user=self.user)
        previous_photo_name = profile.photo.name

        response = self._post_photo(self._image_data_uri('blue'))

        self.assertRedirects(response, reverse('personal:profile_update'))
        profile.refresh_from_db()
        self.assertNotEqual(profile.photo.name, previous_photo_name)
        self.assertFalse(profile.photo.storage.exists(previous_photo_name))
        with Image.open(profile.photo.path) as saved_image:
            red, green, blue = saved_image.getpixel((256, 256))
            self.assertLess(red, 50)
            self.assertLess(green, 50)
            self.assertGreater(blue, 200)

    def test_rejects_invalid_image_without_replacing_existing_photo(self):
        self._post_photo()
        profile = UserProfile.objects.get(user=self.user)
        original_name = profile.photo.name

        response = self._post_photo('data:image/jpeg;base64,bm90LWFuLWltYWdl')

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.photo.name, original_name)
        self.assertContains(response, 'No se pudo validar la imagen')

    def test_ignores_another_users_id_and_only_updates_authenticated_user(self):
        other_user = User.objects.create_user(
            username='another_profile',
            password='test-password',
        )
        other_profile = UserProfile.objects.create(user=other_user)
        other_profile.photo.save(
            'profile.jpg',
            ContentFile(
                validate_profile_photo(
                    base64.b64decode(self._image_data_uri('blue').split(',', 1)[1])
                )
            ),
        )
        other_photo_name = other_profile.photo.name

        response = self._post_photo(user_id=str(other_user.pk))

        self.assertRedirects(response, reverse('personal:profile_update'))
        self.assertTrue(UserProfile.objects.get(user=self.user).photo)
        other_profile.refresh_from_db()
        self.assertEqual(other_profile.photo.name, other_photo_name)

    def test_rejects_non_square_crop(self):
        response = self._post_photo(
            self._image_data_uri(size=(512, 256)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserProfile.objects.get(user=self.user).photo)
        self.assertContains(response, 'debe tener formato cuadrado')

    def test_accepts_png_and_stores_a_validated_jpeg(self):
        response = self._post_photo(self._image_data_uri(mime='png'))

        self.assertRedirects(response, reverse('personal:profile_update'))
        profile = UserProfile.objects.get(user=self.user)
        with Image.open(profile.photo.path) as saved_image:
            self.assertEqual(saved_image.format, 'JPEG')
            self.assertEqual(saved_image.size, (512, 512))

    def test_rejects_declared_format_that_does_not_match_image_bytes(self):
        jpeg_data = self._image_data_uri().split(',', 1)[1]
        response = self._post_photo(f'data:image/png;base64,{jpeg_data}')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserProfile.objects.get(user=self.user).photo)
        self.assertContains(response, 'formato declarado no coincide')

    def test_form_enforces_cropped_image_size_limit(self):
        oversized_value = 'A' * (((1536 * 1024) * 4 // 3) + 129)
        form = ProfilePhotoForm(data={'cropped_image': oversized_value})

        self.assertFalse(form.is_valid())
        self.assertIn('1,5 MiB', str(form.errors))
