from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count
from django.utils import timezone


def commitment_metrics(functionaries, period):
    """Cohorte de compromisos registrados durante el período; estado actual.

    Intervalos de fecha conscientes de zona horaria, sin depender de las tablas
    de zonas horarias de MySQL. La fecha de vencimiento no cambia la cohorte.
    """
    from agenda.models import Commitment

    start = timezone.make_aware(datetime.combine(period.start_date, time.min))
    # Evitar desbordamientos en períodos antiguos con fecha 31/12/9999.
    end_day = period.end_date
    filters = {'created_at__gte': start}
    if end_day.year < 9999 or end_day.month != 12 or end_day.day != 31:
        filters['created_at__lt'] = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min))
    stats = {fn.pk: {'total': 0, 'done': 0, 'pending': 0, 'in_progress': 0, 'joined': 0} for fn in functionaries}
    keys = {Commitment.State.DONE: 'done', Commitment.State.PENDING: 'pending',
            Commitment.State.IN_PROGRESS: 'in_progress', Commitment.State.JOINED: 'joined'}
    for row in Commitment.objects.filter(
        functionary_id__in=stats, deleted_at__isnull=True, **filters,
    ).order_by().values('functionary_id', 'state').annotate(total=Count('pk')):
        current = stats[row['functionary_id']]
        current['total'] += row['total']
        if row['state'] in keys:
            current[keys[row['state']]] += row['total']
    for current in stats.values():
        add_percentages(current)
    return stats


def add_percentages(current):
    current['has_data'] = current['total'] > 0
    for state in ('done', 'pending', 'in_progress', 'joined'):
        current[f'{state}_percentage'] = Decimal(current[state]) * 100 / current['total'] if current['total'] else None
    return current


def combine_commitment_metrics(metrics):
    total = {key: 0 for key in ('total', 'done', 'pending', 'in_progress', 'joined')}
    for metric in metrics:
        for key in total:
            total[key] += metric[key]
    return add_percentages(total)
