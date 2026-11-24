from django import forms
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from atenciones.models import Attention, AttentionType, SubAttention
from personal.models import Delegation, Functionary, FunctionaryRole, Role
from .forms import OfficeLetterForm
from .models import OfficeLetter
from . import tests as letter_tests


class LetterFormUsabilityTests(TestCase):
    def setUp(self):
        letter_tests.OfficeLetterWorkflowTests.setUp(self)
        self.url = reverse('correspondence:letter_create')

    def data(self, **overrides):
        data = {
            'received_at': timezone.localdate().isoformat(),
            'sender': 'Vecina del sector', 'recipient': 'Delegación',
            'subject': 'Solicita limpieza.', 'responsible': self.functionary.pk,
        }
        data.update(overrides)
        return data

    def letter(self, **overrides):
        data = dict(delegation=self.delegation, received_at=timezone.localdate(),
                    sender='Vecina del sector', recipient='Delegación',
                    subject='Solicitud inicial.', responsible=self.functionary)
        data.update(overrides)
        return OfficeLetter.objects.create(**data)

    def make_admin(self):
        role = Role.objects.create(role_name=Role.ADMIN)
        FunctionaryRole.objects.create(functionary=self.functionary, role=role)

    def test_new_letter_prefills_date_and_uses_context_for_fixed_delegation(self):
        response = self.client.get(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form['received_at'].value(), timezone.localdate())
        self.assertEqual(form['responsible'].value(), self.functionary.pk)
        self.assertEqual(form.fixed_delegation, self.delegation)
        self.assertTrue(form.fields['delegation'].disabled)
        self.assertIsInstance(form.fields['state'].widget, forms.HiddenInput)
        self.assertFalse(form.additional_open)
        self.assertContains(response, 'Datos de ingreso')
        self.assertContains(response, 'Remitente y asunto')
        self.assertContains(response, 'Delegación asignada')
        self.assertNotContains(response, '<select name="delegation"')

    def test_minimum_registration_starts_in_process_and_opens_letter_detail(self):
        response = self.client.post(self.url, self.data(state=OfficeLetter.State.FINALIZED))
        letter = OfficeLetter.objects.get()
        self.assertRedirects(response, reverse('correspondence:letter_detail', args=[letter.pk]))
        self.assertEqual(letter.state, OfficeLetter.State.IN_PROGRESS)
        self.assertEqual(letter.registry_number, '')
        self.assertEqual(letter.observation, '')

    def test_admin_responsible_choices_follow_selected_delegation(self):
        self.make_admin()
        other = Delegation.objects.create(name='Otra delegación formulario', field='RURAL')
        colleague = Functionary.objects.create(delegation=other, position=self.position, names='Otra', lastnames='Persona')
        form = OfficeLetterForm(user=self.user)
        self.assertEqual(list(form.fields['responsible'].queryset), [self.functionary])
        self.assertEqual(form.responsible_catalog[str(other.pk)], [{'id': colleague.pk, 'name': colleague.full_name}])
        response = self.client.post(self.url, self.data(delegation=other.pk, responsible=colleague.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OfficeLetter.objects.get().delegation, other)

    def test_admin_cannot_submit_responsible_from_another_delegation(self):
        self.make_admin()
        other = Delegation.objects.create(name='Delegación incompatible formulario', field='RURAL')
        form = OfficeLetterForm(self.data(delegation=other.pk), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('responsible', form.errors)

    def test_regular_functionary_catalog_does_not_expose_other_responsibles(self):
        Functionary.objects.create(delegation=self.delegation, position=self.position, names='Colega', lastnames='No asignable')
        form = OfficeLetterForm(user=self.user)
        self.assertEqual(form.responsible_catalog, {str(self.delegation.pk): [{'id': self.functionary.pk, 'name': self.functionary.full_name}]})

    def test_errors_in_additional_fields_expand_section_and_preserve_text(self):
        response = self.client.post(self.url, self.data(pronouncement='x' * 151, observation='Conservar esta nota'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('pronouncement', response.context['form'].errors)
        self.assertTrue(response.context['form'].additional_open)
        self.assertContains(response, '<details open>')
        self.assertContains(response, 'Conservar esta nota')
        self.assertFalse(OfficeLetter.objects.exists())

    def test_edit_retains_existing_data_and_can_update_status(self):
        letter = self.letter(observation='Antecedentes previos', pronouncement='En revisión')
        url = reverse('correspondence:letter_update', args=[letter.pk])
        response = self.client.get(url)
        self.assertTrue(response.context['form'].additional_open)
        self.assertFalse(response.context['form'].fields['state'].disabled)
        self.assertContains(response, 'Guardar cambios')
        response = self.client.post(url, self.data(state=OfficeLetter.State.FINALIZED,
                                  observation='Antecedentes previos', pronouncement='En revisión'))
        self.assertRedirects(response, reverse('correspondence:letter_detail', args=[letter.pk]))
        letter.refresh_from_db()
        self.assertEqual(letter.state, OfficeLetter.State.FINALIZED)
        self.assertEqual(letter.observation, 'Antecedentes previos')

    def test_inactive_historical_responsible_can_be_retained_but_not_newly_assigned(self):
        self.make_admin()
        historical = Functionary.objects.create(delegation=self.delegation, position=self.position,
            names='Responsable', lastnames='Anterior', is_active=False)
        letter = self.letter(responsible=historical)
        form = OfficeLetterForm(self.data(delegation=self.delegation.pk, responsible=historical.pk,
                               state=OfficeLetter.State.IN_PROGRESS), instance=letter, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        fresh = OfficeLetterForm(self.data(delegation=self.delegation.pk, responsible=historical.pk), user=self.user)
        self.assertFalse(fresh.is_valid())
        self.assertIn('responsible', fresh.errors)

    def test_linked_letter_keeps_delegation_fixed_even_for_global_admin(self):
        self.make_admin()
        attention_type = AttentionType.objects.create(code='FORM', name='Atención formulario')
        sub = SubAttention.objects.create(code='FORM-S', name='Subatención', attention_type=attention_type)
        attention = Attention.objects.create(requester_name='Vecina', description='Solicitud',
            delegation=self.delegation, functionary=self.functionary, attention_type=attention_type, sub_attention=sub)
        letter = self.letter(attention=attention)
        other = Delegation.objects.create(name='Delegación fuera del vínculo', field='RURAL')
        form = OfficeLetterForm(self.data(delegation=other.pk, state=OfficeLetter.State.IN_PROGRESS), instance=letter, user=self.user)
        self.assertTrue(form.fields['delegation'].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['delegation'], self.delegation)
