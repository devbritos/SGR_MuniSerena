from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from personal.models import Delegation, Functionary, Role, FunctionaryRole
from atenciones.models import Attention, AttentionType, SubAttention, AttentionFollowUp
from .models import Organization
from . import tests as org_tests

class OrganizationAttentionLinkTests(TestCase):
    def setUp(self):
        org_tests.OrganizationTests.setUp(self)
        self.kind = AttentionType.objects.create(code='ORG-L',name='Comunitaria')
        self.sub = SubAttention.objects.create(code='ORG-L-S',name='Solicitud',attention_type=self.kind)
        self.attention = Attention.objects.create(requester_name='Vecina de prueba',description='Limpieza del terreno',delegation=self.delegation,functionary=self.fn,attention_type=self.kind,sub_attention=self.sub)
        self.url = reverse('organizations:attention_link',args=[self.org.pk])
        self.detail = reverse('organizations:detail',args=[self.org.pk])
    def test_link_keeps_original_fields_and_records_history_once(self):
        payload={'attention':self.attention.pk}
        self.assertRedirects(self.client.post(self.url,payload),self.detail)
        self.client.post(self.url,payload)
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.organization,self.org)
        self.assertEqual(self.attention.requester_name,'Vecina de prueba')
        self.assertEqual(self.attention.status,Attention.Status.PENDING)
        self.assertEqual(self.attention.followups.count(),1)
        self.assertEqual(self.attention.followups.get().author,self.fn)
        self.assertContains(self.client.get(self.detail),f'Atención #{self.attention.pk}')
        self.assertContains(self.client.get(reverse('atenciones:attention_detail',args=[self.attention.pk])),self.org.name)
    def test_existing_other_organization_cannot_be_replaced(self):
        other=Organization.objects.create(name='Otra agrupación',delegation=self.delegation,created_by=self.fn)
        self.attention.organization=other;self.attention.save()
        response=self.client.post(self.url,{'attention':self.attention.pk})
        self.assertContains(response,'ya está vinculada a otra organización')
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.organization,other)
        self.assertEqual(self.attention.followups.count(),0)
        self.assertEqual(self.client.get(self.url).context['page_obj'].paginator.count,0)
    def test_inaccessible_attentions_are_not_shown_or_linkable(self):
        colleague=Functionary.objects.create(delegation=self.delegation,position=self.position,names='Otra',lastnames='Persona')
        self.attention.functionary=colleague;self.attention.save()
        self.assertNotContains(self.client.get(self.url),'Vecina de prueba')
        self.assertIn('attention',self.client.post(self.url,{'attention':self.attention.pk}).context['form'].errors)
        self.attention.organization=self.org;self.attention.save()
        self.assertNotContains(self.client.get(self.detail),'Vecina de prueba')
    def test_other_delegation_and_archived_attention_are_rejected(self):
        other=Delegation.objects.create(name='Otra delegación vinculada',field='RURAL')
        self.attention.delegation=other;self.attention.save()
        self.assertIn('attention',self.client.post(self.url,{'attention':self.attention.pk}).context['form'].errors)
        self.attention.delegation=self.delegation;self.attention.deleted_at=timezone.now();self.attention.save()
        self.assertIn('attention',self.client.post(self.url,{'attention':self.attention.pk}).context['form'].errors)
    def test_readonly_cannot_link_and_has_no_write_buttons(self):
        role=Role.objects.create(role_name=Role.READONLY);FunctionaryRole.objects.create(functionary=self.fn,role=role)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.client.post(self.url,{'attention':self.attention.pk}).status_code,403)
        self.assertNotContains(self.client.get(self.detail),'Vincular atención existente')
        self.assertNotContains(self.client.get(self.detail),'Registrar atención')
    def test_search_by_id_text_and_dates(self):
        self.assertEqual(list(self.client.get(self.url,{'q':str(self.attention.pk)}).context['page_obj']),[self.attention])
        self.assertEqual(list(self.client.get(self.url,{'q':'terreno'}).context['page_obj']),[self.attention])
        self.assertEqual(self.client.get(self.url,{'date_to':(timezone.localdate()-timedelta(days=1)).isoformat()}).context['page_obj'].paginator.count,0)
        response=self.client.get(self.url,{'date_from':'2026-12-01','date_to':'2026-11-01'})
        self.assertTrue(response.context['search_form'].errors)
        self.assertEqual(response.context['page_obj'].paginator.count,0)
    def test_linked_attention_list_is_paginated_without_truncation(self):
        for i in range(11):
            Attention.objects.create(requester_name=f'Persona {i}',description='Solicitud',delegation=self.delegation,functionary=self.fn,attention_type=self.kind,sub_attention=self.sub,organization=self.org)
        page=self.client.get(self.detail).context['attention_page']
        self.assertEqual(page.paginator.count,11)
        self.assertEqual(len(page.object_list),10)
        self.assertEqual(len(self.client.get(self.detail,{'attention_page':2}).context['attention_page'].object_list),1)
    def test_inactive_organization_remains_selected_when_editing_attention(self):
        self.attention.organization=self.org;self.attention.save()
        self.org.status=Organization.Status.INACTIVE;self.org.save()
        url=reverse('atenciones:attention_update',args=[self.attention.pk])
        response=self.client.post(url,{'requester_name':'Vecina','requester_contact':'','organization':self.org.pk,'description':'Actualizada','attention_type':self.kind.pk,'sub_attention':self.sub.pk})
        self.assertEqual(response.status_code,302)
        self.attention.refresh_from_db();self.assertEqual(self.attention.organization,self.org)
    def test_source_organization_prefills_requester_and_global_creation_uses_source_delegation(self):
        role=Role.objects.create(role_name=Role.ADMIN);FunctionaryRole.objects.create(functionary=self.fn,role=role)
        other=Delegation.objects.create(name='Delegación administrada organización',field='RURAL')
        org=Organization.objects.create(name='Club administrado',phone='912345678',delegation=other,created_by=self.fn)
        url=reverse('atenciones:attention_create')+f'?organization={org.pk}'
        form=self.client.get(url).context['form']
        self.assertEqual(form['requester_name'].value(),org.name)
        self.assertTrue(form.fields['organization'].disabled)
        response=self.client.post(url,{'requester_name':org.name,'requester_contact':org.phone,'description':'Solicitud','attention_type':self.kind.pk,'sub_attention':self.sub.pk})
        created=Attention.objects.get(organization=org)
        self.assertRedirects(response,reverse('atenciones:attention_detail',args=[created.pk]))
        self.assertEqual(created.delegation,other)
    def test_closed_attention_link_preserves_closure_and_does_not_reopen(self):
        self.attention.status=Attention.Status.CLOSED;self.attention.closure_outcome=Attention.Outcome.GUIDANCE;self.attention.closure_details='Orientación entregada';self.attention.closed_at=timezone.now();self.attention.save()
        self.client.post(self.url,{'attention':self.attention.pk})
        self.attention.refresh_from_db()
        self.assertEqual(self.attention.status,Attention.Status.CLOSED)
        self.assertEqual(self.attention.followups.get().closure_details,'Orientación entregada')

    def test_readonly_cannot_bypass_link_permissions_by_editing_attention(self):
        role = Role.objects.create(role_name=Role.READONLY)
        FunctionaryRole.objects.create(functionary=self.fn, role=role)
        response = self.client.post(reverse('atenciones:attention_update', args=[self.attention.pk]), {
            'requester_name': self.attention.requester_name, 'description': self.attention.description,
            'attention_type': self.kind.pk, 'sub_attention': self.sub.pk, 'organization': self.org.pk,
        })
        self.assertIn('organization', response.context['form'].errors)
        self.attention.refresh_from_db()
        self.assertIsNone(self.attention.organization_id)

    def test_other_delegation_organization_cannot_be_link_target(self):
        other = Delegation.objects.create(name='Fuera del alcance', field='RURAL')
        organization = Organization.objects.create(name='Otra organización', delegation=other, created_by=self.fn)
        url = reverse('organizations:attention_link', args=[organization.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'attention': self.attention.pk}).status_code, 404)
