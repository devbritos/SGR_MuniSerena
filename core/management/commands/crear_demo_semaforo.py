"""Datos ficticios identificables para recorrer el semáforo sin alterar metas reales."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from uuid import NAMESPACE_URL, uuid5

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from activities.models import Activity, Evidence
from agenda.models import Commitment
from analytics.calculations import calcular_porcentaje_esperado, obtener_semaforo_funcionarios
from configuration.models import Goal, Measuring, Period
from personal.models import Delegation, Functionary, Position


def demo_pdf():
    """PDF real de una página; el contenido advierte que no acredita trabajo municipal."""
    stream = (b'BT /F1 16 Tf 50 770 Td (DEMOSTRACION - DATOS FICTICIOS) Tj '
              b'0 -32 Td /F1 11 Tf (Respaldo de prueba para visualizar el semaforo.) Tj '
              b'0 -22 Td (No acredita actividades ni atenciones municipales reales.) Tj ET')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
    ]
    content = b'%PDF-1.4\n'
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(content)
    content += b'xref\n0 6\n0000000000 65535 f \n'
    content += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    content += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return content


class Command(BaseCommand):
    help = 'Crea un escenario DEMO del trimestre actual: verde, amarillo, rojo y sin metas.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--with-commitments', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        quarter = (today.month - 1) // 3 + 1
        start_month = 3 * (quarter - 1) + 1
        end_month = start_month + 2
        start = date(today.year, start_month, 1)
        end = date(today.year, end_month, monthrange(today.year, end_month)[1])
        marker = f'DEMO{today.year % 100:02}Q{quarter}'
        period, created = Period.objects.get_or_create(version_parameter=marker, defaults={
            'start_date': start, 'end_date': end, 'computable_days': (end - start).days + 1,
            'status': False, 'minimum_threshold': 0,
            'maximum_computable_days': (end - start).days + 1, 'semaphore': 'DEMO',
        })
        if not created and (period.start_date != start or period.end_date != end or period.semaphore != 'DEMO'):
            raise CommandError('El identificador del período DEMO ya está ocupado. No se modifica.')
        if period.deleted_at:
            raise CommandError('El período de demostración está archivado. No se restaura automáticamente.')
        expected = calcular_porcentaje_esperado(period, today)
        position, _ = Position.objects.get_or_create(name='DEMO · Gestor de atenciones')
        reviewer_position, _ = Position.objects.get_or_create(name='DEMO · Revisor sin metas')
        with_commitments = options['with_commitments'] or Goal.objects.filter(
            position=position, period=period, measuring__code='DEMO-SEM-CUMPLIDOS',
        ).exists()
        measures = []
        for suffix, name, weight, unit in (
            ('AT', 'Atenciones realizadas', 50, 'atenciones'),
            ('VI', 'Visitas a terreno', 30, 'visitas'),
            ('IN', 'Informes entregados', 20, 'informes'),
        ):
            configured_weight = {'AT': 40, 'VI': 20, 'IN': 15}[suffix] if with_commitments else weight
            measuring, _ = Measuring.objects.get_or_create(code=f'DEMO-SEM-{suffix}', defaults={
                'service': f'DEMO · {name}',
                'measurable_item': 'Indicador ficticio de demostración. No representa trabajo municipal real.',
            })
            if not measuring.service.startswith('DEMO · ') or not measuring.validity or measuring.deleted_at:
                raise CommandError('El catálogo DEMO fue modificado o desactivado. No se sobrescribe.')
            goal, _ = Goal.objects.get_or_create(position=position, period=period, measuring=measuring, defaults={
                'target_value': 100, 'weight': configured_weight, 'unity': unit,
            })
            if goal.target_value != 100 or goal.weight not in (weight, configured_weight) or not goal.validity or goal.deleted_at:
                raise CommandError('Las metas DEMO fueron modificadas. No se sobrescriben.')
            if goal.weight != configured_weight:
                goal.weight = configured_weight
                goal.save(update_fields=['weight', 'updated_at'])
            measures.append(measuring)

        people = []
        for color, name in (('VERDE', 'Ana'), ('AMARILLO', 'Bruno'), ('ROJO', 'Carla')):
            delegation, created = Delegation.objects.get_or_create(code=f'DEMO-SEM-{color}', defaults={
                'name': f'DEMO · Semáforo {color.lower()}', 'field': 'URBANO',
                'address': 'Delegación ficticia para pruebas del sistema',
            })
            if delegation.name != f'DEMO · Semáforo {color.lower()}' or delegation.deleted_at:
                raise CommandError('El código de delegación DEMO ya está ocupado o archivado.')
            fn, _ = Functionary.objects.get_or_create(
                delegation=delegation, position=position, names=name, lastnames=f'Demostracion {color.title()}',
            )
            people.append((color, fn))
        reviewer, _ = Functionary.objects.get_or_create(
            delegation=people[0][1].delegation, position=reviewer_position,
            names='Daniel', lastnames='Demostracion Revisor',
        )
        path = 'evidences/demo_semaforo/respaldo_ficticio.pdf'
        for color, fn in people:
            quantity = 100 if color == 'VERDE' else int((expected * (
                Decimal('0.8') if color == 'AMARILLO' else Decimal('0.2')
            )).to_integral_value(rounding=ROUND_CEILING if color == 'AMARILLO' else ROUND_FLOOR))
            for measuring in measures:
                label = f'DEMO {marker} · {measuring.code}'
                activity, created = Activity.objects.get_or_create(functionary=fn, measuring=measuring, application=label, defaults={
                    'date': today, 'taken_action': 'Registro ficticio para visualizar colores del semáforo.',
                    'name_contact': 'Persona ficticia', 'telephone_contact': '',
                    'quantity': quantity, 'state_validity': 'VALIDATED',
                })
                if not created and activity.deleted_at:
                    raise CommandError('Una actividad DEMO fue archivada. No se restaura automáticamente.')
                # Repetir el comando actualiza solo estas cantidades de prueba,
                # para conservar los colores con el avance de los días.
                if not created:
                    activity.quantity, activity.date = quantity, today
                    activity.save(update_fields=['quantity', 'date', 'updated_at'])
                Evidence.objects.get_or_create(activity=activity, name='DEMO · Respaldo ficticio aprobado', defaults={
                    'author': 'Demostración del sistema', 'date_evidence': today,
                    'metadata': 'DATOS FICTICIOS. Este documento no acredita trabajo municipal real.',
                    'validity_state': 'APPROVED', 'date_validity': today,
                    'file': path, 'functionary': fn, 'verificator': reviewer,
                })
        if with_commitments:
            for code, title, method, target, weight in (
                ('CUMPLIDOS', 'Porcentaje de compromisos cumplidos', Measuring.Calculation.COMMITMENTS_DONE, 80, 20),
                ('PENDIENTES', 'Porcentaje de compromisos pendientes', Measuring.Calculation.COMMITMENTS_PENDING, 10, 5),
            ):
                measuring, _ = Measuring.objects.get_or_create(code=f'DEMO-SEM-{code}', defaults={
                    'service': f'DEMO · {title}', 'calculation_method': method,
                    'measurable_item': 'Indicador ficticio basado en los compromisos de la agenda.',
                })
                if measuring.calculation_method != method or not measuring.service.startswith('DEMO · '):
                    raise CommandError('El indicador de compromisos DEMO fue modificado.')
                Goal.objects.get_or_create(position=position, period=period, measuring=measuring, defaults={
                    'target_value': target, 'weight': weight, 'unity': '%',
                })
            pending = []
            for color, fn in people:
                done, waiting = {'VERDE': (18, 1), 'AMARILLO': (10, 5), 'ROJO': (2, 12)}[color]
                for index in range(20):
                    token = uuid5(NAMESPACE_URL, f'sgr-demo-commitment/{marker}/{fn.pk}/{index}')
                    pending.append(Commitment(
                        submission_token=token, functionary=fn, commitment_date=today,
                        origin='DEMO · Evaluación trimestral', applic_name=f'DEMO {marker} compromiso {index + 1:02}',
                        territory=fn.delegation.name, observation='Datos ficticios para evaluar porcentajes de compromisos.',
                        state=Commitment.State.DONE if index < done else Commitment.State.PENDING if index < done + waiting else Commitment.State.IN_PROGRESS,
                    ))
            existing = set(Commitment.objects.filter(submission_token__in=[obj.submission_token for obj in pending]).values_list('submission_token', flat=True))
            Commitment.objects.bulk_create([obj for obj in pending if obj.submission_token not in existing])
        data, unmatched = obtener_semaforo_funcionarios([fn for _, fn in people], period, expected)
        for (color, fn), result in zip(people, data):
            expected_color = {'VERDE': 'green', 'AMARILLO': 'yellow', 'ROJO': 'red'}[color]
            if (not with_commitments and result['status'] != expected_color) or unmatched:
                raise CommandError('Los datos DEMO tienen cambios adicionales: no se guardó el escenario.')
            self.stdout.write(f'{color}: {fn.full_name} | avance {result["achieved_percentage"]}% | esperado {expected:.2f}%')
            if with_commitments:
                self.stdout.write(f'  Compromisos: {result["commitments"]["done_percentage"]:.1f}% cumplidos / {result["commitments"]["pending_percentage"]:.1f}% pendientes')
        self.stdout.write(f'PERIODO {period.pk}: {start} al {end} (no altera el período vigente)')
        self.stdout.write(f'ABRIR http://127.0.0.1:8000/dashboard/semaforo/?period={period.pk}&q=DEMO')
        if options['dry_run']:
            transaction.set_rollback(True)
            self.stdout.write('Simulación: no se guardan registros ni archivos.')
        elif not default_storage.exists(path):
            default_storage.save(path, ContentFile(demo_pdf()))
