from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from personal.models import Delegation, Position, Functionary, Role, FunctionaryRole
from .models import Organization, OrganizationLeader

class OrganizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='org_user', password='test-password')
        self.delegation = Delegation.objects.create(name='Delegación organizaciones', field='URBANO')
        self.position = Position.objects.create(name='Gestor comunitario')
        self.fn = Functionary.objects.create(user=self.user, delegation=self.delegation, position=self.position, names='Gestor', lastnames='Comunitario')
        self.org = Organization.objects.create(name='Junta vecinal', delegation=self.delegation, created_by=self.fn)
        self.client.force_login(self.user)
    def test_create_with_optional_identifiers_and_open_detail(self):
        response = self.client.post(reverse('organizations:create'), {'name':'Club deportivo', 'status':'FORMING'})
        org = Organization.objects.get(name='Club deportivo')
        self.assertRedirects(response, reverse('organizations:detail',args=[org.pk]))
        self.assertEqual(org.created_by,self.fn)
        self.assertIsNone(org.rut)
    def test_edit_loads_existing_organization_and_keeps_original_author(self):
        url = reverse('organizations:update', args=[self.org.pk])
        self.assertContains(self.client.get(url), 'Junta vecinal')
        self.assertRedirects(self.client.post(url, {'name':'Nombre actualizado','status':'INACTIVE'}), reverse('organizations:detail',args=[self.org.pk]))
        self.org.refresh_from_db()
        self.assertEqual(self.org.name,'Nombre actualizado')
        self.assertEqual(self.org.created_by,self.fn)
    def test_other_delegation_cannot_be_read_or_edited(self):
        other = Delegation.objects.create(name='Otra delegación',field='RURAL')
        org = Organization.objects.create(name='Organización reservada',delegation=other,created_by=self.fn)
        self.assertNotContains(self.client.get(reverse('organizations:list')), org.name)
        for name in ['detail','update']:
            self.assertEqual(self.client.get(reverse('organizations:'+name,args=[org.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('organizations:leader_create',args=[org.pk]),{'name':'Persona','position':'Presidente'}).status_code,404)
    def test_readonly_cannot_create_or_edit(self):
        role = Role.objects.create(role_name=Role.READONLY)
        FunctionaryRole.objects.create(functionary=self.fn,role=role)
        self.assertEqual(self.client.get(reverse('organizations:list')).status_code,200)
        self.assertEqual(self.client.post(reverse('organizations:create'),{'name':'No autorizado','status':'ACTIVE'}).status_code,403)
    def test_leader_create_edit_and_dates(self):
        url = reverse('organizations:leader_create',args=[self.org.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        response = self.client.post(url,{'name':'Vecina dirigente','position':'Presidenta','is_active':'on'})
        self.assertRedirects(response,reverse('organizations:detail',args=[self.org.pk]))
        leader = self.org.leaders.get()
        edit = reverse('organizations:leader_update',args=[self.org.pk,leader.pk])
        self.assertContains(self.client.get(edit),'Vecina dirigente')
        self.client.post(edit,{'name':'Vecina dirigente','position':'Secretaria','is_active':'on'})
        leader.refresh_from_db()
        self.assertEqual(leader.position,'Secretaria')
        self.assertEqual(leader.validity_label,'Sin término registrado')
        response = self.client.post(edit,{'name':'Vecina dirigente','position':'Secretaria','starts_on':'2026-12-01','ends_on':'2026-11-01'})
        self.assertIn('ends_on',response.context['form'].errors)
    def test_leader_cannot_be_opened_under_another_organization(self):
        leader = OrganizationLeader.objects.create(organization=self.org,name='Nombre',position='Cargo')
        other = Organization.objects.create(name='Otra',delegation=self.delegation,created_by=self.fn)
        self.assertEqual(self.client.get(reverse('organizations:leader_update',args=[other.pk,leader.pk])).status_code,404)

    def test_repeated_leader_submission_creates_one_record(self):
        url = reverse('organizations:leader_create', args=[self.org.pk])
        data = {'name': 'Dirigente de prueba', 'position': 'Presidente', 'is_active': 'on', 'email': 'dirigente@example.com'}
        for _ in range(3):
            self.assertRedirects(self.client.post(url, data), reverse('organizations:detail', args=[self.org.pk]))
        self.assertEqual(self.org.leaders.count(), 1)

    def test_distinct_periods_and_organizations_are_not_treated_as_duplicates(self):
        data = {'name': 'Dirigente de prueba', 'position': 'Presidente', 'is_active': 'on'}
        url = reverse('organizations:leader_create', args=[self.org.pk])
        self.client.post(url, {**data, 'starts_on': '2025-01-01', 'ends_on': '2025-12-31'})
        self.client.post(url, {**data, 'starts_on': '2026-01-01', 'ends_on': '2026-12-31'})
        other = Organization.objects.create(name='Otra agrupación', delegation=self.delegation, created_by=self.fn)
        self.client.post(reverse('organizations:leader_create', args=[other.pk]), data)
        self.assertEqual(self.org.leaders.count(), 2)
        self.assertEqual(other.leaders.count(), 1)
    def test_rut_validation_and_duplicate(self):
        data = {'name':'Con RUT','status':'ACTIVE','rut':'12.345.678-5'}
        self.client.post(reverse('organizations:create'),data)
        self.assertTrue(Organization.objects.filter(rut='12345678-5').exists())
        response = self.client.post(reverse('organizations:create'),data)
        self.assertIn('rut',response.context['form'].errors)
        data['rut']='12345678-0'
        self.assertIn('rut',self.client.post(reverse('organizations:create'),data).context['form'].errors)
    def test_search_and_expired_period(self):
        self.assertContains(self.client.get(reverse('organizations:list'),{'q':'vecinal'}),self.org.name)
        self.assertNotContains(self.client.get(reverse('organizations:list'),{'q':'Sin coincidencias'}),self.org.name)
        leader = OrganizationLeader(organization=self.org,name='Nombre',position='Cargo',ends_on=timezone.localdate()-timedelta(days=1))
        self.assertEqual(leader.validity_label,'Período vencido')
