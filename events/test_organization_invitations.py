from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from organizations import tests as organization_tests
from organizations.models import Organization
from personal.models import Delegation, Role, FunctionaryRole
from .models import CommunityEvent, EventOrganization, EventRegistration


class OrganizationInvitationTests(TestCase):
    def setUp(self):
        organization_tests.OrganizationTests.setUp(self)
        self.event = CommunityEvent.objects.create(delegation=self.delegation, title='Taller comunitario', description='Taller', starts_at=timezone.now()+timedelta(days=2), location='Sede vecinal')
        self.url = reverse('events:organization_invitations', args=[self.event.pk])

    def invite(self):
        return self.client.post(self.url, {'organizations': [self.org.pk]})

    def test_add_and_repeat_does_not_duplicate_or_reserve_individual_places(self):
        for _ in range(3):
            self.assertRedirects(self.invite(), self.url)
        self.assertEqual(EventOrganization.objects.count(), 1)
        self.assertEqual(EventRegistration.objects.count(), 0)
        invitation = EventOrganization.objects.get()
        self.assertEqual(invitation.invited_by, self.user)
        self.assertEqual(invitation.status, EventOrganization.Status.INVITED)
        self.assertContains(self.client.get(reverse('organizations:detail',args=[self.org.pk])), self.event.title)

    def test_other_delegation_and_inactive_organization_cannot_be_invited(self):
        other = Delegation.objects.create(name='Otra delegación evento', field='RURAL')
        org = Organization.objects.create(name='Fuera del evento', delegation=other, created_by=self.fn)
        response = self.client.post(self.url, {'organizations':[org.pk]})
        self.assertIn('organizations', response.context['form'].errors)
        self.org.status = Organization.Status.INACTIVE
        self.org.save()
        self.assertIn('organizations', self.invite().context['form'].errors)
        self.assertFalse(EventOrganization.objects.exists())

    def test_participation_is_explicit_and_cannot_be_recorded_before_event(self):
        self.invite()
        invitation = EventOrganization.objects.get()
        url = reverse('events:organization_participation_update',args=[self.event.pk,invitation.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        response = self.client.post(url, {'status':'PARTICIPATED','observations':'Confirmado en terreno'})
        self.assertIn('status', response.context['form'].errors)
        CommunityEvent.objects.filter(pk=self.event.pk).update(starts_at=timezone.now()-timedelta(days=1))
        self.assertRedirects(self.client.post(url, {'status':'PARTICIPATED','observations':'Confirmado en terreno'}),self.url)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status,'PARTICIPATED')
        self.assertEqual(invitation.updated_by,self.user)

    def test_readonly_can_consult_but_cannot_add_or_update(self):
        self.invite()
        invitation = EventOrganization.objects.get()
        role=Role.objects.create(role_name=Role.READONLY)
        FunctionaryRole.objects.create(functionary=self.fn,role=role)
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.invite().status_code,403)
        url=reverse('events:organization_participation_update',args=[self.event.pk,invitation.pk])
        self.assertEqual(self.client.post(url,{'status':'CONFIRMED'}).status_code,403)

    def test_cancellation_preserves_history_and_blocks_new_changes(self):
        self.invite()
        self.event.status=CommunityEvent.Status.CANCELLED
        self.event.save()
        self.assertContains(self.client.get(self.url),'cancelado')
        self.assertEqual(self.invite().status_code,403)
        self.assertEqual(EventOrganization.objects.count(),1)

    def test_inaccessible_event_and_mismatched_invitation_are_rejected(self):
        self.invite()
        invitation=EventOrganization.objects.get()
        other=Delegation.objects.create(name='Fuera de alcance evento',field='RURAL')
        foreign=CommunityEvent.objects.create(delegation=other,title='Privado',description='Evento',starts_at=timezone.now(),location='Sede')
        self.assertEqual(self.client.get(reverse('events:organization_invitations',args=[foreign.pk])).status_code,404)
        same=CommunityEvent.objects.create(delegation=self.delegation,title='Otro evento',description='Evento',starts_at=timezone.now(),location='Sede')
        url=reverse('events:organization_participation_update',args=[same.pk,invitation.pk])
        self.assertEqual(self.client.post(url,{'status':'CONFIRMED'}).status_code,404)

    def test_event_delegation_cannot_change_after_inviting_organizations(self):
        self.invite()
        self.event.delegation=Delegation.objects.create(name='Cambio no permitido',field='RURAL')
        with self.assertRaises(ValidationError):
            self.event.full_clean()

    def test_search_and_pagination(self):
        for number in range(21):
            Organization.objects.create(name=f'Agrupación {number}',delegation=self.delegation,created_by=self.fn)
        self.assertEqual(self.client.get(self.url).context['candidates'].paginator.num_pages,2)
        self.assertEqual(self.client.get(self.url,{'q':'vecinal'}).context['candidates'].paginator.count,1)

    def test_public_event_page_does_not_expose_invitation_list(self):
        self.invite()
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('events:public_list')),self.org.name)

    def test_live_search_returns_only_matching_candidate_fragment(self):
        response = self.client.get(self.url, {'q': 'vecinal'}, HTTP_X_ORGANIZATION_SEARCH='1')
        self.assertContains(response, 'data-candidate-content')
        self.assertContains(response, self.org.name)
        self.assertNotContains(response, '<!DOCTYPE html>')
        response = self.client.get(self.url, {'q': 'no coincide'}, HTTP_X_ORGANIZATION_SEARCH='1')
        self.assertEqual(response.context['candidates'].paginator.count, 0)

    def test_live_search_excludes_already_invited_and_foreign_organizations(self):
        self.invite()
        other = Delegation.objects.create(name='Fuera de búsqueda', field='RURAL')
        Organization.objects.create(name='Junta vecinal externa', delegation=other, created_by=self.fn)
        response = self.client.get(self.url, {'q': 'vecinal'}, HTTP_X_ORGANIZATION_SEARCH='1')
        self.assertEqual(response.context['candidates'].paginator.count, 0)

    def test_live_search_cannot_bypass_event_permissions(self):
        other = Delegation.objects.create(name='Evento fuera de búsqueda', field='RURAL')
        event = CommunityEvent.objects.create(delegation=other, title='Otro evento', description='Evento', starts_at=timezone.now(), location='Sede')
        url = reverse('events:organization_invitations', args=[event.pk])
        self.assertEqual(self.client.get(url, HTTP_X_ORGANIZATION_SEARCH='1').status_code, 404)
