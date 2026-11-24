from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from atenciones.models import Attention, AttentionFollowUp, AttentionType, SubAttention
from personal.models import Delegation, Functionary, FunctionaryRole, Role
from .models import OfficeLetter
from . import tests as letter_tests


class LetterAttentionLinkTests(TestCase):
    def setUp(self):
        letter_tests.OfficeLetterWorkflowTests.setUp(self)
        self.letter = OfficeLetter.objects.create(
            delegation=self.delegation, received_at=timezone.localdate(),
            registry_number='OP-101', recipient='Delegación', sender='Vecina de prueba',
            contact_phone='912345678', subject='Solicita limpieza del terreno.',
            responsible=self.functionary, registered_by=self.functionary,
        )
        self.attention_type = AttentionType.objects.create(code='LINK', name='Servicios comunitarios')
        self.subattention = SubAttention.objects.create(code='LINK-S', name='Limpieza', attention_type=self.attention_type)
        self.detail_url = reverse('correspondence:letter_detail', args=[self.letter.pk])
        self.create_url = reverse('correspondence:letter_attention_create', args=[self.letter.pk])
        self.link_url = reverse('correspondence:letter_attention_link', args=[self.letter.pk])

    def attention(self, **overrides):
        data = dict(requester_name='Vecina registrada', requester_contact='912345678',
                    attention_type=self.attention_type, sub_attention=self.subattention,
                    description='Solicitud ya ingresada.', delegation=self.delegation,
                    functionary=self.functionary, followup_responsible=self.functionary)
        data.update(overrides)
        return Attention.objects.create(**data)

    def payload(self, **overrides):
        data = dict(requester_name=self.letter.sender, requester_contact=self.letter.contact_phone,
                    attention_type=self.attention_type.pk, sub_attention=self.subattention.pk,
                    description=self.letter.subject, followup_responsible=self.functionary.pk)
        data.update(overrides)
        return data

    def test_detail_offers_both_actions_without_creating_an_attention(self):
        response = self.client.get(self.detail_url)
        self.assertContains(response, 'Crear atención desde esta carta')
        self.assertContains(response, 'Vincular atención existente')
        self.assertFalse(Attention.objects.exists())

    def test_creation_form_prefills_letter_data_and_embeds_subattention_catalog(self):
        response = self.client.get(self.create_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form['requester_name'].value(), self.letter.sender)
        self.assertEqual(form['requester_contact'].value(), self.letter.contact_phone)
        self.assertEqual(form['description'].value(), self.letter.subject)
        self.assertEqual(form['followup_responsible'].value(), self.functionary.pk)
        self.assertContains(response, 'data-subattention-catalog')
        self.assertContains(response, 'Crear y vincular atención')

    def test_creation_links_letter_and_records_history_without_changing_letter_state(self):
        response = self.client.post(self.create_url, self.payload())
        attention = Attention.objects.get()
        self.assertRedirects(response, reverse('atenciones:attention_detail', args=[attention.pk]))
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.attention, attention)
        self.assertEqual(self.letter.state, OfficeLetter.State.IN_PROGRESS)
        self.assertEqual(attention.status, Attention.Status.PENDING)
        self.assertEqual(attention.functionary, self.functionary)
        self.assertEqual(attention.delegation, self.delegation)
        entry = AttentionFollowUp.objects.get()
        self.assertEqual(entry.author, self.functionary)
        self.assertIn('OP-101', entry.note)
        detail = self.client.get(reverse('atenciones:attention_detail', args=[attention.pk]))
        self.assertContains(detail, 'Cartas vinculadas')
        self.assertContains(detail, self.detail_url)

    def test_repeated_creation_or_link_after_creation_does_not_duplicate(self):
        self.client.post(self.create_url, self.payload())
        other = self.attention()
        self.assertRedirects(self.client.post(self.create_url, self.payload()), self.detail_url)
        self.assertRedirects(self.client.post(self.link_url, {'attention': other.pk}), self.detail_url)
        self.assertEqual(Attention.objects.count(), 2)
        self.assertEqual(AttentionFollowUp.objects.count(), 1)
        self.letter.refresh_from_db()
        self.assertNotEqual(self.letter.attention_id, other.pk)

    def test_existing_attention_link_keeps_both_states_and_multiple_letters_can_share_attention(self):
        attention = self.attention(status=Attention.Status.CLOSED, closure_outcome=Attention.Outcome.RESOLVED,
                                   closure_details='Solicitud resuelta.', closed_at=timezone.now())
        self.letter.state = OfficeLetter.State.FINALIZED
        self.letter.save()
        self.assertRedirects(self.client.post(self.link_url, {'attention': attention.pk}), self.detail_url)
        second = OfficeLetter.objects.create(delegation=self.delegation, received_at=timezone.localdate(), sender='Otra carta', recipient='Delegación', subject='Mismo asunto', responsible=self.functionary)
        self.client.post(reverse('correspondence:letter_attention_link', args=[second.pk]), {'attention': attention.pk})
        self.assertEqual(Attention.objects.count(), 1)
        self.assertEqual(attention.office_letters.count(), 2)
        self.letter.refresh_from_db()
        attention.refresh_from_db()
        self.assertEqual(self.letter.state, OfficeLetter.State.FINALIZED)
        self.assertEqual(attention.status, Attention.Status.CLOSED)
        self.assertEqual(attention.followups.first().closure_details, 'Solicitud resuelta.')

    def test_search_filters_results_and_paginates_ten_at_a_time(self):
        match = self.attention(requester_name='Persona buscada')
        for i in range(11):
            self.attention(requester_name=f'Otro vecino {i}')
        response = self.client.get(self.link_url, {'q': 'Persona buscada'})
        self.assertEqual(list(response.context['page_obj']), [match])
        self.assertEqual(self.client.get(self.link_url).context['page_obj'].paginator.num_pages, 2)
        self.assertContains(self.client.get(self.link_url), 'Siguiente')

    def test_invalid_classification_preserves_data_and_creates_nothing(self):
        other_type = AttentionType.objects.create(code='OTHER', name='Otro tipo')
        response = self.client.post(self.create_url, self.payload(attention_type=other_type.pk))
        self.assertIn('sub_attention', response.context['form'].errors)
        self.assertEqual(response.context['form']['requester_name'].value(), self.letter.sender)
        self.assertFalse(Attention.objects.exists())
        self.letter.refresh_from_db()
        self.assertIsNone(self.letter.attention_id)

    def test_cannot_assign_new_attention_to_other_delegation_or_inactive_person(self):
        other = Delegation.objects.create(name='Otra delegación cartas', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        response = self.client.post(self.create_url, self.payload(followup_responsible=colleague.pk))
        self.assertIn('followup_responsible', response.context['form'].errors)
        colleague.delegation = self.delegation
        colleague.is_active = False
        colleague.save()
        response = self.client.post(self.create_url, self.payload(followup_responsible=colleague.pk))
        self.assertIn('followup_responsible', response.context['form'].errors)

    def test_unavailable_or_other_delegation_attentions_cannot_be_linked(self):
        other = Delegation.objects.create(name='Fuera de alcance cartas', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        other_attention = self.attention(delegation=other, functionary=colleague, followup_responsible=colleague)
        archived = self.attention(deleted_at=timezone.now())
        for candidate in (other_attention, archived):
            response = self.client.post(self.link_url, {'attention': candidate.pk})
            self.assertIn('attention', response.context['form'].errors)
        self.assertFalse(AttentionFollowUp.objects.exists())

    def test_other_owners_attention_in_same_delegation_is_not_exposed(self):
        colleague = Functionary.objects.create(delegation=self.delegation, position=self.position, names='Otra', lastnames='Persona')
        candidate = self.attention(functionary=colleague, followup_responsible=colleague)
        response = self.client.get(self.link_url)
        self.assertEqual(response.context['page_obj'].paginator.count, 0)
        response = self.client.post(self.link_url, {'attention': candidate.pk})
        self.assertIn('attention', response.context['form'].errors)

    def test_other_letter_owner_and_archived_letter_are_not_accessible(self):
        colleague = Functionary.objects.create(delegation=self.delegation, position=self.position, names='Otra', lastnames='Persona')
        self.letter.responsible = colleague
        self.letter.save()
        for url in (self.detail_url, self.create_url, self.link_url):
            self.assertEqual(self.client.get(url).status_code, 404)
        for url in (self.create_url, self.link_url):
            self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.letter.responsible = self.functionary
        self.letter.deleted_at = timezone.now()
        self.letter.save()
        self.assertEqual(self.client.post(self.create_url, self.payload()).status_code, 404)

    def test_global_admin_records_actual_author_and_uses_letter_delegation(self):
        other = Delegation.objects.create(name='Delegación admin cartas', field='RURAL')
        admin_user = User.objects.create_user(username='global_letter_admin', password='test-password')
        admin = Functionary.objects.create(user=admin_user, delegation=other, position=self.position, names='Admin', lastnames='Global')
        role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(functionary=admin, role=role)
        self.client.force_login(admin_user)
        self.client.post(self.create_url, self.payload())
        attention = Attention.objects.get()
        self.assertEqual(attention.functionary, admin)
        self.assertEqual(attention.delegation, self.delegation)
        self.assertEqual(attention.followup_responsible, self.functionary)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('atenciones:attention_detail', args=[attention.pk])).status_code, 200)

    def test_link_prevents_changing_letter_delegation(self):
        self.letter.attention = self.attention()
        other = Delegation.objects.create(name='Delegación incompatible', field='RURAL')
        self.letter.delegation = other
        with self.assertRaises(ValidationError):
            self.letter.full_clean()

    def test_linked_attention_does_not_reveal_other_owners_letters(self):
        attention = self.attention()
        self.client.post(self.link_url, {'attention': attention.pk})
        colleague = Functionary.objects.create(delegation=self.delegation, position=self.position, names='Otra', lastnames='Persona')
        hidden_letter = OfficeLetter.objects.create(delegation=self.delegation, responsible=colleague,
            received_at=timezone.localdate(), sender='Remitente reservado', recipient='Delegación',
            subject='Otro documento', attention=attention, registry_number='OCULTA-77')
        response = self.client.get(reverse('atenciones:attention_detail', args=[attention.pk]))
        self.assertContains(response, 'OP-101')
        self.assertNotContains(response, hidden_letter.registry_number)
        self.assertNotContains(response, hidden_letter.sender)

    def test_ordinary_functionary_cannot_register_attention_in_other_delegation(self):
        other = Delegation.objects.create(name='Registro no permitido', field='RURAL')
        attention = Attention(requester_name='Persona', description='Solicitud', delegation=other,
            functionary=self.functionary, attention_type=self.attention_type, sub_attention=self.subattention)
        with self.assertRaises(ValidationError):
            attention.full_clean()

    def test_staff_without_functionary_can_read_letter_but_cannot_create_attention(self):
        staff = User.objects.create_user(username='letter_staff_without_profile', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)
        self.assertNotContains(self.client.get(self.detail_url), 'Crear atención desde esta carta')
        self.assertEqual(self.client.post(self.create_url, self.payload()).status_code, 403)

    def test_archived_linked_attention_keeps_link_and_disables_duplicate_creation(self):
        archived = self.attention(deleted_at=timezone.now())
        self.letter.attention = archived
        self.letter.save()
        self.assertContains(self.client.get(self.detail_url), 'que está archivada')
        self.assertRedirects(self.client.post(self.create_url, self.payload()), self.detail_url)
        self.assertEqual(Attention.objects.count(), 1)
