from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum


def calcular_avance(functionary, measuring, period):
    """Suma la cantidad registrada en actividades validadas para el período."""
    from activities.models import Activity, approved_activity_queryset

    result = approved_activity_queryset(Activity.objects.filter(
        functionary=functionary,
        measuring=measuring,
        date__gte=period.start_date,
        date__lte=period.end_date,
        deleted_at__isnull=True,
    )).aggregate(total=Sum('quantity'))
    return result['total'] or 0


def calcular_porcentaje_cumplimiento(avance, meta):
    """RN-004: % cumplimiento = avance / meta × 100"""
    if not meta or meta == 0:
        return Decimal('0')
    return (Decimal(avance) / Decimal(meta)) * 100


def calcular_cumplimiento_ponderado(porcentaje_cumplimiento, ponderador, maximo=150):
    """RN-005: cumplimiento ponderado = ponderador × % cumplimiento / 100, con tope configurable."""
    resultado = (Decimal(ponderador) * Decimal(porcentaje_cumplimiento)) / 100
    return min(resultado, Decimal(maximo))


def calcular_meta_esperada_al_dia(period):
    """RN-007: días transcurridos / días totales × 100"""
    hoy = timezone.localdate()
    if hoy < period.start_date:
        return Decimal('0')
    if hoy > period.end_date:
        return Decimal('100')

    dias_transcurridos = (hoy - period.start_date).days
    dias_totales = period.computable_days or (period.end_date - period.start_date).days

    if dias_totales == 0:
        return Decimal('0')

    return (Decimal(dias_transcurridos) / Decimal(dias_totales)) * 100


def calcular_semaforo(avance_porcentaje, meta_esperada):
    """RN-008: verde/ámbar/rojo según el avance real vs. el esperado al día."""
    if meta_esperada == 0:
        return 'verde'

    ratio = Decimal(avance_porcentaje) / Decimal(meta_esperada) if meta_esperada else Decimal('0')

    if avance_porcentaje >= meta_esperada:
        return 'verde'
    elif avance_porcentaje >= Decimal('0.6') * meta_esperada:
        return 'ambar'
    else:
        return 'rojo'


def obtener_indicador_funcionario(functionary, period):
    """
    Junta todo: para cada meta del cargo del funcionario en ese período,
    calcula avance, % cumplimiento, cumplimiento ponderado y semáforo.
    Devuelve una lista de diccionarios, uno por ítem medible.
    """
    from configuration.models import Goal

    metas = Goal.objects.filter(
        position=functionary.position,
        period=period,
        validity=True,
        deleted_at__isnull=True,
        measuring__validity=True,
        measuring__deleted_at__isnull=True,
    ).select_related('measuring')
    resultados = []
    total_ponderado = Decimal('0')

    for goal in metas:
        avance = calcular_avance(functionary, goal.measuring, period)
        pct_cumplimiento = calcular_porcentaje_cumplimiento(avance, goal.target_value)
        cumplimiento_ponderado = calcular_cumplimiento_ponderado(pct_cumplimiento, goal.weight)
        meta_esperada = calcular_meta_esperada_al_dia(period)
        semaforo = calcular_semaforo(pct_cumplimiento, meta_esperada)

        total_ponderado += cumplimiento_ponderado

        resultados.append({
            'measuring': goal.measuring,
            'meta': goal.target_value,
            'avance': avance,
            'porcentaje_cumplimiento': round(pct_cumplimiento, 2),
            'ponderador': goal.weight,
            'cumplimiento_ponderado': round(cumplimiento_ponderado, 2),
            'meta_esperada_al_dia': round(meta_esperada, 2),
            'semaforo': semaforo,
        })

    return {
        'items': resultados,
        'total_ponderado': round(total_ponderado, 2),
    }