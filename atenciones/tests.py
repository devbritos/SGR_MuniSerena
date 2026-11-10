from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from personal.models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)

from .models import Attention, AttentionType, SubAttention


class CitizenAttentionTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            code='D-TEST',
            name='Delegación de prueba',
            address='Calle de prueba 100',
            commune='La Serena',
            field='URBANO',
        )
        self.position = Position.objects.create(name='Funcionario de prueba')
        self.user = User.objects.create_user(
            username='funcionario_atencion',
            email='atencion@example.com',
            password='test-password',
        )
        self.functionary = Functionary.objects.create(
            user=self.user,
            delegation=self.delegation,
            position=self.position,
            names='Funcionario',
            lastnames='Prueba',
        )
        self.attention_type = AttentionType.objects.create(
            code='AT-01',
            name='Ayuda social',
        )
        self.sub_attention = SubAttention.objects.create(
            code='SUB-01',
            name='Apoyo vecinal',
            attention_type=self.attention_type,
        )
        self.client.force_login(self.user)

    def test_attention_uses_logged_in_functionary_and_delegation(self):
        response = self.client.post(
            reverse('atenciones:attention_create'),
            {
                'requester_name': 'Vecina de prueba',
                'requester_contact': 'vecina@example.com',
                'attention_type': self.attention_type.pk,
                'sub_attention': self.sub_attention.pk,
                'description': 'Solicitud de apoyo comunitario.',
            },
        )
        self.assertRedirects(response, reverse('atenciones:attention_list'))
        attention = Attention.objects.get()
        self.assertEqual(attention.functionary, self.functionary)
        self.assertEqual(attention.delegation, self.delegation)
        self.assertIsNotNone(attention.created_at)

    def test_attention_can_be_edited_by_its_responsible_functionary(self):
        attention = Attention.objects.create(
            requester_name='Solicitante anterior',
            requester_contact='anterior@example.com',
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description='Descripción anterior.',
            delegation=self.delegation,
            functionary=self.functionary,
        )

        edit_page = self.client.get(
            reverse('atenciones:attention_update', args=[attention.pk])
        )
        self.assertEqual(edit_page.status_code, 200)
        self.assertContains(edit_page, 'Editar atención ciudadana')
        self.assertContains(edit_page, 'Datos de la persona')
        self.assertContains(edit_page, 'Clasificación')
        self.assertContains(edit_page, 'Detalle de la atención')
        self.assertContains(edit_page, 'La delegación y el usuario responsable no se pueden modificar')
        self.assertContains(edit_page, 'Delegación de prueba')
        self.assertContains(edit_page, 'Funcionario Prueba')

        response = self.client.post(
            reverse('atenciones:attention_update', args=[attention.pk]),
            {
                'requester_name': 'Solicitante actualizado',
                'requester_contact': 'actualizado@example.com',
                'attention_type': self.attention_type.pk,
                'sub_attention': self.sub_attention.pk,
                'description': 'Descripción actualizada.',
            },
        )

        self.assertRedirects(response, reverse('atenciones:attention_list'))
        attention.refresh_from_db()
        self.assertEqual(attention.requester_name, 'Solicitante actualizado')
        self.assertEqual(attention.requester_contact, 'actualizado@example.com')
        self.assertEqual(attention.description, 'Descripción actualizada.')
        self.assertEqual(attention.delegation, self.delegation)
        self.assertEqual(attention.functionary, self.functionary)

    def test_attention_can_be_deleted_and_is_soft_deleted(self):
        attention = Attention.objects.create(
            requester_name='Solicitante por eliminar',
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description='Descripción para eliminar.',
            delegation=self.delegation,
            functionary=self.functionary,
        )

        confirmation = self.client.get(
            reverse('atenciones:attention_delete', args=[attention.pk])
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, 'se conservará en el historial')

        response = self.client.post(
            reverse('atenciones:attention_delete', args=[attention.pk])
        )

        self.assertRedirects(response, reverse('atenciones:attention_list'))
        attention.refresh_from_db()
        self.assertIsNotNone(attention.deleted_at)
        self.assertNotContains(
            self.client.get(reverse('atenciones:attention_list')),
            'Solicitante por eliminar',
        )

    def test_attention_edit_and_delete_are_limited_to_visible_records(self):
        other_delegation = Delegation.objects.create(
            code='D-OTHER-CRUD',
            name='Otra delegación CRUD',
            field='RURAL',
        )
        other_user = User.objects.create_user(
            username='otro_funcionario_crud',
            password='test-password',
        )
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=other_delegation,
            position=self.position,
            names='Otro',
            lastnames='Funcionario',
        )
        attention = Attention.objects.create(
            requester_name='Atención de otra delegación',
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description='No debe ser accesible.',
            delegation=other_delegation,
            functionary=other_functionary,
        )

        for action in ('attention_update', 'attention_delete'):
            with self.subTest(action=action):
                response = self.client.get(
                    reverse(f'atenciones:{action}', args=[attention.pk])
                )
                self.assertEqual(response.status_code, 404)

        attention.refresh_from_db()
        self.assertIsNone(attention.deleted_at)

    def test_mismatched_subattention_is_rejected(self):
        other_type = AttentionType.objects.create(
            code='AT-02',
            name='Otra atención',
        )
        response = self.client.post(
            reverse('atenciones:attention_create'),
            {
                'requester_name': 'Vecina de prueba',
                'requester_contact': '',
                'attention_type': other_type.pk,
                'sub_attention': self.sub_attention.pk,
                'description': 'Descripción de prueba.',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attention.objects.exists())
        self.assertIn('sub_attention', response.context['form'].errors)

    def test_attention_form_explains_when_type_catalog_is_empty(self):
        self.sub_attention.delete()
        self.attention_type.delete()

        response = self.client.get(reverse('atenciones:attention_create'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['has_active_attention_types'])
        self.assertContains(response, 'No hay tipos de atención activos')
        self.assertContains(response, 'Solicita al administrador')
        self.assertNotContains(response, 'Guardar atención')

    def test_admin_sees_shortcut_to_create_first_attention_type(self):
        self.sub_attention.delete()
        self.attention_type.delete()
        admin_role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(
            functionary=self.functionary,
            role=admin_role,
        )

        response = self.client.get(reverse('atenciones:attention_create'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_manage_attention_types'])
        self.assertContains(response, 'Crear tipo de atención')
        self.assertContains(
            response,
            reverse('atenciones:attention_type_create'),
        )

    def test_subattention_endpoint_returns_only_active_children(self):
        inactive = SubAttention.objects.create(
            code='SUB-02',
            name='Desactivada',
            attention_type=self.attention_type,
            is_active=False,
        )
        response = self.client.get(
            reverse(
                'atenciones:subattention_options',
                args=[self.attention_type.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        result_ids = {item['id'] for item in response.json()['results']}
        self.assertIn(self.sub_attention.pk, result_ids)
        self.assertNotIn(inactive.pk, result_ids)

    def test_attention_list_is_scoped_and_exports_to_excel(self):
        Attention.objects.create(
            requester_name='Vecino de mi delegación',
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description='Solicitud propia.',
            delegation=self.delegation,
            functionary=self.functionary,
        )
        other_delegation = Delegation.objects.create(
            code='D-OTHER',
            name='Otra delegación',
            field='RURAL',
        )
        other_user = User.objects.create_user(
            username='otro_funcionario',
            password='test-password',
        )
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=other_delegation,
            position=self.position,
            names='Otro',
            lastnames='Funcionario',
        )
        Attention.objects.create(
            requester_name='Vecino de otra delegación',
            attention_type=self.attention_type,
            sub_attention=self.sub_attention,
            description='Solicitud ajena.',
            delegation=other_delegation,
            functionary=other_functionary,
        )

        response = self.client.get(reverse('atenciones:attention_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registrar atención')
        self.assertContains(response, 'Vecino de mi delegación')
        self.assertContains(response, 'Editar atención de Vecino de mi delegación')
        self.assertNotContains(response, 'Vecino de otra delegación')

        export = self.client.get(
            reverse('atenciones:attention_list'),
            {'export': 'xlsx'},
        )
        self.assertEqual(export.status_code, 200)
        self.assertEqual(
            export['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )


class AttentionCatalogPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_catalogos',
            email='admin@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)

    def test_catalog_lists_render_and_export(self):
        attention_type = AttentionType.objects.create(
            code='AT-CAT',
            name='Tipo para listado',
        )
        SubAttention.objects.create(
            code='SUB-CAT',
            name='Subtipo para listado',
            attention_type=attention_type,
        )
        for name, route in (
            ('Tipo para listado', 'atenciones:attention_type_list'),
            ('Subtipo para listado', 'atenciones:subattention_list'),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, name)
                export = self.client.get(
                    reverse(route),
                    {'export': 'xlsx'},
                )
                self.assertEqual(export.status_code, 200)
                self.assertEqual(
                    export['Content-Type'],
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )

        response = self.client.get(
            reverse(
                'atenciones:attention_type_deactivate',
                args=[attention_type.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse(
                'atenciones:attention_type_deactivate',
                args=[attention_type.pk],
            )
        )
        self.assertRedirects(response, reverse('atenciones:attention_type_list'))
        attention_type.refresh_from_db()
        self.assertFalse(attention_type.is_active)

    def test_admin_can_create_attention_type_from_catalog(self):
        response = self.client.post(
            reverse('atenciones:attention_type_create'),
            {
                'code': 'AT-NUEVO',
                'name': 'Orientación municipal',
                'description': 'Información y orientación a vecinos.',
                'is_active': 'on',
            },
        )

        self.assertRedirects(
            response,
            reverse('atenciones:attention_type_list'),
        )
        attention_type = AttentionType.objects.get(code='AT-NUEVO')
        self.assertTrue(attention_type.is_active)
        self.assertContains(
            self.client.get(reverse('atenciones:attention_type_list')),
            'Orientación municipal',
        )

    def test_subattention_deactivation_preserves_historical_record(self):
        attention_type = AttentionType.objects.create(
            code='AT-DESACT',
            name='Tipo desactivable',
        )
        subattention = SubAttention.objects.create(
            code='SUB-DESACT',
            name='Subatención desactivable',
            attention_type=attention_type,
        )
        url = reverse(
            'atenciones:subattention_deactivate',
            args=[subattention.pk],
        )

        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url)

        self.assertRedirects(response, reverse('atenciones:subattention_list'))
        subattention.refresh_from_db()
        self.assertFalse(subattention.is_active)
        self.assertTrue(
            SubAttention.objects.filter(pk=subattention.pk).exists()
        )
