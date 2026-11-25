from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from organizations.models import Neighbor, Organization
from personal.models import Delegation, Functionary, Position


class NeighborSmokeTest(TestCase):
    def test_directory_and_membership_lifecycle(self):
        user = User.objects.create_user(username='neighbor-clerk')
        delegation = Delegation.objects.create(name='Delegación', field='URBANO')
        profile = Functionary.objects.create(
            user=user, delegation=delegation, position=Position.objects.create(name='Gestor'),
            names='Gestor', lastnames='Comunitario',
        )
        junta = Organization.objects.create(delegation=delegation, created_by=profile, name='Junta')
        self.client.force_login(user)
        url = reverse('organizations:neighbors')
        self.assertContains(self.client.get(url), 'data-bs-target="#neighbor-modal"')
        payload = {'action': 'create', 'name': 'Vecina', 'rut': '12.345.678-5'}
        self.assertRedirects(self.client.post(url, payload), url)
        neighbor = Neighbor.objects.get(rut='12345678-5')
        self.assertFalse(neighbor.organizations.exists())
        self.assertEqual(User.objects.count(), 1)
        self.assertIn('rut', self.client.post(url, payload).context['form'].errors)
        self.assertContains(self.client.get(url, {'action': 'edit', 'neighbor': neighbor.pk}), 'Editar vecino')
        self.assertRedirects(self.client.post(url, {
            **payload, 'action': 'edit', 'neighbor': neighbor.pk, 'organizations': [junta.pk],
            'email': 'vecina@example.com', 'phone': '+56912345678',
        }), url)
        response = self.client.get(url, {'junta': junta.pk, 'q': '12.345.678-5'})
        self.assertContains(response, 'vecina@example.com')
        self.assertContains(response, '+56912345678')
        self.assertContains(self.client.get(url, {'action': 'delete', 'neighbor': neighbor.pk}), 'Eliminar vecino')
        self.assertRedirects(self.client.post(url, {'action': 'delete', 'neighbor': neighbor.pk}), url)
        self.assertFalse(Neighbor.objects.exists())
