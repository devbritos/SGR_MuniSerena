from io import StringIO
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from activities.models import Activity, Evidence
from analytics.calculations import calcular_porcentaje_esperado, obtener_semaforo_funcionarios
from configuration.models import Goal, Period
from personal.models import Delegation, Functionary


class SemaphoreDemoTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        media = override_settings(MEDIA_ROOT=folder.name)
        media.enable()
        self.addCleanup(media.disable)

    def seed(self, **options):
        call_command('crear_demo_semaforo', stdout=StringIO(), **options)

    def test_demo_creates_real_calculated_colors_and_downloadable_fictitious_evidence(self):
        self.seed()
        period = Period.objects.get(semaphore='DEMO')
        results, unmatched = obtener_semaforo_funcionarios(
            Functionary.objects.select_related('delegation'), period, calcular_porcentaje_esperado(period),
        )
        self.assertEqual({row['status'] for row in results}, {'green', 'yellow', 'red', 'no_goal'})
        self.assertEqual(unmatched, 0)
        self.assertEqual(Delegation.objects.count(), 3)
        self.assertEqual(Goal.objects.count(), 3)
        self.assertEqual(Activity.objects.count(), 9)
        self.assertEqual(Evidence.objects.count(), 9)
        self.assertFalse(period.status)
        self.assertFalse(User.objects.exists())
        evidence = Evidence.objects.first()
        with evidence.file.open('rb') as file:
            self.assertTrue(file.read().startswith(b'%PDF-1.4'))
        staff = User.objects.create_user(username='demo_admin', is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse('delegation_dashboard'), {'period': period.pk, 'q': 'DEMO'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Datos ficticios de demostración')
        self.assertContains(response, 'delegation-card--green')
        self.assertContains(response, 'delegation-card--yellow')
        self.assertContains(response, 'delegation-card--red')
        response = self.client.get(reverse('activities:evidence_file', args=[evidence.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_repeating_command_does_not_duplicate_demo_records(self):
        self.seed()
        self.seed()
        self.assertEqual(Period.objects.count(), 1)
        self.assertEqual(Delegation.objects.count(), 3)
        self.assertEqual(Functionary.objects.count(), 4)
        self.assertEqual(Activity.objects.count(), 9)
        self.assertEqual(Evidence.objects.count(), 9)

    def test_commitment_demo_adds_automatic_indicators_and_preserves_total_weight(self):
        from agenda.models import Commitment
        from django.db.models import Sum
        self.seed()
        self.seed(with_commitments=True)
        self.seed(with_commitments=True)
        self.assertEqual(Commitment.objects.count(), 60)
        self.assertEqual(Goal.objects.count(), 5)
        self.assertEqual(Goal.objects.aggregate(total=Sum('weight'))['total'], 100)
        period = Period.objects.get(semaphore='DEMO')
        metrics, _ = obtener_semaforo_funcionarios(Functionary.objects.all(), period, calcular_porcentaje_esperado(period))
        with_goals = [metric for metric in metrics if metric['has_active_goals']]
        self.assertEqual({metric['commitments']['done_percentage'] for metric in with_goals}, {Decimal('90'), Decimal('50'), Decimal('10')})

    def test_dry_run_writes_neither_records_nor_files(self):
        self.seed(dry_run=True)
        self.assertFalse(Period.objects.exists())
        self.assertFalse(Delegation.objects.exists())
        self.assertFalse(Activity.objects.exists())
        from django.core.files.storage import default_storage
        self.assertFalse(default_storage.exists('evidences/demo_semaforo/respaldo_ficticio.pdf'))
