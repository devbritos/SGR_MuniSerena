from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone


# Se conserva el límite del resumen actual hasta confirmar el alcance del 150%.
# Esta única constante gobierna el aporte por indicador y el resultado total.
MAXIMO_CUMPLIMIENTO = Decimal('100')


def _decimal(value):
    return Decimal(str(value))


def calcular_porcentaje_esperado(period, today=None):
    """Avance calendario inclusivo, limitado al intervalo 0–100%."""
    today = today or timezone.localdate()
    total_days = (period.end_date - period.start_date).days + 1
    if total_days <= 0 or today < period.start_date:
        return Decimal('0')
    elapsed_days = min((today - period.start_date).days + 1, total_days)
    return Decimal(elapsed_days) / Decimal(total_days) * 100


def calcular_meta_esperada_al_dia(period, today=None):
    """Entrada compatible para el cálculo común del objetivo esperado."""
    return calcular_porcentaje_esperado(period, today)


def calcular_porcentaje_cumplimiento(avance, meta):
    """Cumplimiento real, antes de limitar su aporte a la evaluación."""
    if not meta or _decimal(meta) <= 0:
        return Decimal('0')
    return max(_decimal(avance), Decimal('0')) / _decimal(meta) * 100


def calcular_cumplimiento_ponderado(porcentaje_cumplimiento, ponderador, maximo=None):
    """El límite se aplica al cumplimiento ANTES de multiplicar por el peso."""
    limit = MAXIMO_CUMPLIMIENTO if maximo is None else _decimal(maximo)
    applied = min(max(_decimal(porcentaje_cumplimiento), Decimal('0')), limit)
    return applied * _decimal(ponderador) / 100


def calcular_semaforo(avance_porcentaje, meta_esperada):
    """Regla del Excel: verde >= esperado; ámbar >= 60% de esperado."""
    achieved, expected = _decimal(avance_porcentaje), _decimal(meta_esperada)
    if expected <= 0 or achieved >= expected:
        return 'verde'
    if achieved >= Decimal('0.6') * expected:
        return 'ambar'
    return 'rojo'


def estado_semaforo(avance_porcentaje, meta_esperada):
    """Presentación común para indicadores, funcionarios y delegaciones."""
    return {
        'verde': ('green', 'En línea con lo esperado'),
        'ambar': ('yellow', 'Atención'),
        'rojo': ('red', 'Bajo lo esperado'),
    }[calcular_semaforo(avance_porcentaje, meta_esperada)]


def calcular_avance(functionary, measuring, period):
    from activities.models import Activity, approved_activity_queryset

    result = approved_activity_queryset(Activity.objects.filter(
        functionary=functionary, measuring=measuring,
        date__range=(period.start_date, period.end_date), deleted_at__isnull=True,
    )).aggregate(total=Sum('quantity'))
    return result['total'] or 0


def _indicadores_funcionarios(functionaries, period, expected_percentage):
    """Un solo motor y consultas agrupadas para resumen y detalle.

    Solo suman actividades validadas cuya última evidencia esté aprobada,
    dentro del período y asociadas a una meta activa del cargo e ítem.
    Los valores se redondean al presentarlos, después de determinar el color.
    """
    from activities.models import Activity, approved_activity_queryset
    from configuration.models import Goal, Measuring
    from .commitment_metrics import commitment_metrics

    functionaries = list(functionaries)
    goals_by_position = defaultdict(list)
    goal_keys = set()
    for goal in Goal.objects.filter(
        period=period, validity=True, deleted_at__isnull=True,
        measuring__validity=True, measuring__deleted_at__isnull=True,
        position_id__in={fn.position_id for fn in functionaries},
    ).select_related('measuring').order_by('pk'):
        goals_by_position[goal.position_id].append(goal)
        if goal.measuring.calculation_method == Measuring.Calculation.ACTIVITIES:
            goal_keys.add((goal.position_id, goal.measuring_id))

    positions = {fn.pk: fn.position_id for fn in functionaries}
    totals = {}
    unmatched_count = 0
    activities = approved_activity_queryset(Activity.objects.filter(
        functionary_id__in=positions, date__range=(period.start_date, period.end_date),
        deleted_at__isnull=True,
    )).order_by().values('functionary_id', 'measuring_id').annotate(
        total=Sum('quantity'), record_count=Count('pk'),
    )
    for row in activities:
        totals[(row['functionary_id'], row['measuring_id'])] = row['total'] or 0
        if (positions[row['functionary_id']], row['measuring_id']) not in goal_keys:
            unmatched_count += row['record_count']

    commitments = commitment_metrics(functionaries, period)
    results = []
    for fn in functionaries:
        goals = goals_by_position[fn.position_id]
        items = []
        total_weighted = Decimal('0')
        has_activity = False
        for goal in goals:
            method = goal.measuring.calculation_method
            is_percentage = goal.measuring.is_commitment_percentage
            has_data = True
            if is_percentage:
                current = commitments[fn.pk]
                has_data = current['has_data']
                achieved = current['done_percentage'] if method == Measuring.Calculation.COMMITMENTS_DONE else current['pending_percentage']
                if not has_data:
                    percentage = Decimal('0')
                elif method == Measuring.Calculation.COMMITMENTS_PENDING:
                    # SALON!G23: <= límite → 100%; hasta 50% → 50%; sobre 50% → 0%.
                    percentage = Decimal('100') if achieved <= goal.target_value else Decimal('50') if achieved <= 50 else Decimal('0')
                else:
                    percentage = calcular_porcentaje_cumplimiento(achieved, goal.target_value)
            else:
                achieved = totals.get((fn.pk, goal.measuring_id), 0)
                has_activity = has_activity or achieved > 0
                percentage = calcular_porcentaje_cumplimiento(achieved, goal.target_value)
            weighted = calcular_cumplimiento_ponderado(percentage, goal.weight)
            total_weighted += weighted
            items.append({
                'measuring': goal.measuring, 'meta': goal.target_value, 'avance': achieved,
                'is_percentage': is_percentage, 'has_data': has_data,
                'unit': '%' if is_percentage else goal.unity,
                'porcentaje_cumplimiento': round(percentage, 2),
                'cumplimiento_aplicado': round(min(percentage, MAXIMO_CUMPLIMIENTO), 2),
                'ponderador': goal.weight, 'cumplimiento_ponderado': round(weighted, 2),
                'meta_esperada_al_dia': round(expected_percentage, 2),
                'semaforo': calcular_semaforo(min(percentage, MAXIMO_CUMPLIMIENTO), expected_percentage) if has_data else 'sin_datos',
            })
        total_weighted = min(total_weighted, MAXIMO_CUMPLIMIENTO)
        status, label = (
            estado_semaforo(total_weighted, expected_percentage)
            if goals else ('no_goal', 'Sin meta activa para este cargo')
        )
        results.append({
            'functionary': fn, 'items': items,
            'commitments': commitments[fn.pk],
            'has_commitment_goals': any(goal.measuring.is_commitment_percentage for goal in goals),
            'total_ponderado': round(total_weighted, 2),
            'achieved_percentage': round(total_weighted, 1) if goals else None,
            'unrounded_percentage': total_weighted if goals else None,
            'expected_percentage': round(expected_percentage, 1),
            'has_active_goals': bool(goals), 'has_matched_activities': has_activity,
            'has_matched_data': has_activity or any(item['is_percentage'] and item['has_data'] for item in items),
            'status': status, 'label': label,
        })
    return results, unmatched_count


def obtener_semaforo_funcionarios(functionaries, period, expected_percentage):
    return _indicadores_funcionarios(functionaries, period, _decimal(expected_percentage))


def obtener_indicador_funcionario(functionary, period):
    expected = calcular_porcentaje_esperado(period)
    results, _ = _indicadores_funcionarios([functionary], period, expected)
    return results[0]
