import uuid
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from organizations import tests as setup_tests
from personal.models import Functionary, Delegation, Role, FunctionaryRole
from .models import Meeting, MeetingAgreement, Commitment


class MeetingTests(TestCase):
    def setUp(self):
        setup_tests.OrganizationTests.setUp(self)
        self.meeting = Meeting.objects.create(delegation=self.delegation, title='Coordinación semanal', starts_at=timezone.now()-timedelta(days=1), location='Delegación', created_by=self.fn)

    def meeting_data(self, **overrides):
        data = {'creation_token':str(uuid.uuid4()), 'title':'Nueva reunión', 'starts_at':timezone.localtime(timezone.now()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'), 'location':'Sede', 'status':'SCHEDULED', 'participants':[self.fn.pk]}
        data.update(overrides)
        return data

    def agreement(self):
        return MeetingAgreement.objects.create(meeting=self.meeting, description='Coordinar operativo', responsible=self.fn, due_date=timezone.localdate()+timedelta(days=3))

    def test_create_meeting_participants_and_repeated_submission(self):
        data=self.meeting_data()
        url=reverse('agenda:meeting_create')
        self.assertEqual(self.client.get(url).status_code,200)
        for _ in range(3): self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(Meeting.objects.filter(title='Nueva reunión').count(),1)
        meeting=Meeting.objects.get(title='Nueva reunión')
        self.assertEqual(list(meeting.participants.all()),[self.fn])
        self.assertContains(self.client.get(reverse('agenda:meeting_detail',args=[meeting.pk])),'Nueva reunión')

    def test_edit_preserves_creator_and_can_record_conclusions(self):
        url=reverse('agenda:meeting_update',args=[self.meeting.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        data=self.meeting_data(title='Actualizada',notes='Conclusiones',status='HELD',starts_at=timezone.localtime(self.meeting.starts_at).strftime('%Y-%m-%dT%H:%M'))
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.created_by,self.fn)
        self.assertEqual(self.meeting.notes,'Conclusiones')

    def test_unrelated_or_other_delegation_meetings_are_hidden(self):
        colleague=Functionary.objects.create(delegation=self.delegation,position=self.position,names='Otra',lastnames='Persona')
        self.meeting.created_by=colleague;self.meeting.save()
        self.assertEqual(self.client.get(reverse('agenda:meeting_detail',args=[self.meeting.pk])).status_code,404)
        self.meeting.participants.add(self.fn)
        self.assertEqual(self.client.get(reverse('agenda:meeting_detail',args=[self.meeting.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('agenda:meeting_update',args=[self.meeting.pk])).status_code,403)
        self.meeting.delegation=Delegation.objects.create(name='Otra delegación reunión',field='RURAL');self.meeting.save()
        self.assertEqual(self.client.get(reverse('agenda:meeting_detail',args=[self.meeting.pk])).status_code,404)

    def test_foreign_participants_and_responsibles_rejected(self):
        other=Delegation.objects.create(name='Fuera de reunión',field='RURAL')
        colleague=Functionary.objects.create(delegation=other,position=self.position,names='Otra',lastnames='Persona')
        response=self.client.post(reverse('agenda:meeting_create'),self.meeting_data(participants=[colleague.pk]))
        self.assertIn('participants',response.context['form'].errors)
        response=self.client.post(reverse('agenda:agreement_create',args=[self.meeting.pk]),{'description':'Acuerdo','responsible':colleague.pk,'due_date':timezone.localdate().isoformat()})
        self.assertIn('responsible',response.context['form'].errors)

    def test_agreement_and_conversion_do_not_duplicate(self):
        data={'description':'Coordinar operativo','responsible':self.fn.pk,'due_date':(timezone.localdate()+timedelta(days=3)).isoformat()}
        url=reverse('agenda:agreement_create',args=[self.meeting.pk])
        for _ in range(3): self.assertEqual(self.client.post(url,data).status_code,302)
        agreement=self.meeting.agreements.get()
        url=reverse('agenda:agreement_convert',args=[self.meeting.pk,agreement.pk])
        self.assertContains(self.client.get(url),'Crear compromiso desde acuerdo')
        payload={'applic_name':'Reunión semanal','territory':'Sector norte','functionary':self.fn.pk,'commitment_date':data['due_date'],'observation':data['description']}
        for _ in range(3): self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(Commitment.objects.count(),1)
        agreement.refresh_from_db()
        self.assertEqual(agreement.description,'Coordinar operativo')
        self.assertIsNotNone(agreement.commitment_id)

    def test_cancelled_meeting_and_readonly_cannot_create_agreements(self):
        agreement=self.agreement()
        self.meeting.status=Meeting.Status.CANCELLED;self.meeting.save()
        self.assertEqual(self.client.get(reverse('agenda:agreement_convert',args=[self.meeting.pk,agreement.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse('agenda:agreement_create',args=[self.meeting.pk])).status_code,403)
        role=Role.objects.create(role_name=Role.READONLY);FunctionaryRole.objects.create(functionary=self.fn,role=role)
        self.assertEqual(self.client.get(reverse('agenda:meeting_detail',args=[self.meeting.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('agenda:meeting_create')).status_code,403)

    def test_converted_agreement_is_edited_through_commitment(self):
        agreement=self.agreement()
        agreement.commitment=Commitment.objects.create(origin='Reunión',applic_name='Solicitud',territory='Sector',commitment_date=agreement.due_date,functionary=self.fn)
        agreement.save()
        self.assertEqual(self.client.get(reverse('agenda:agreement_update',args=[self.meeting.pk,agreement.pk])).status_code,403)
        self.assertContains(self.client.get(reverse('agenda:commitment_update',args=[agreement.commitment_id])),'Volver al acuerdo y la reunión')

    def test_future_meeting_cannot_be_marked_held(self):
        response=self.client.post(reverse('agenda:meeting_create'),self.meeting_data(status='HELD'))
        self.assertIn('starts_at',response.context['form'].errors)

    def test_agreement_cannot_be_converted_from_another_meeting(self):
        agreement=self.agreement()
        other=Meeting.objects.create(delegation=self.delegation,title='Otra',starts_at=timezone.now(),location='Sede',created_by=self.fn)
        self.assertEqual(self.client.get(reverse('agenda:agreement_convert',args=[other.pk,agreement.pk])).status_code,404)

    def test_creator_can_open_commitment_assigned_to_colleague(self):
        colleague=Functionary.objects.create(delegation=self.delegation,position=self.position,names='Colega',lastnames='Asignado')
        agreement=self.agreement()
        agreement.commitment=Commitment.objects.create(origin='Reunión',applic_name='Solicitud',territory='Sector',commitment_date=agreement.due_date,functionary=colleague)
        agreement.save()
        self.assertEqual(self.client.get(reverse('agenda:commitment_update',args=[agreement.commitment_id])).status_code,200)
