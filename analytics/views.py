from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from personal.models import Delegation, Functionary
from agenda.models import Commitment
from activities.models import Activity
from atenciones.models import Attention
from django.utils import timezone
from .calculations import (
    calcular_porcentaje_esperado,
    obtener_indicador_funcionario,
    obtener_semaforo_funcionarios,
)
from configuration.models import Period


def _active_functionary_admin(user):
    functionary = getattr(user, 'functionary', None)
    return bool(
        functionary
        and functionary.is_admin
        and functionary.is_active
        and functionary.deleted_at is None
    )


def _month_start():
    return timezone.localdate().replace(day=1)


@login_required
def admin_dashboard(request):
    if not (
        request.user.is_staff
        or request.user.is_superuser
        or _active_functionary_admin(request.user)
    ):
        raise PermissionDenied

    today = timezone.localdate()
    month_start = _month_start()
    active_functionaries = Functionary.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
    )
    active_delegations = Delegation.objects.filter(
        state='ACTIVO',
        deleted_at__isnull=True,
    )
    active_commitments = Commitment.objects.filter(deleted_at__isnull=True)
    open_commitments = active_commitments.exclude(state=Commitment.State.DONE)
    active_activities = Activity.objects.filter(deleted_at__isnull=True)
    active_attentions = Attention.objects.filter(deleted_at__isnull=True)

    context = {
        'can_manage_catalogs': (
            request.user.is_superuser or _active_functionary_admin(request.user)
        ),
        'can_view_attentions': (
            _active_functionary(request.user) is not None
        ),
        'total_funcionarios': active_functionaries.count(),
        'total_delegaciones': active_delegations.count(),
        'compromisos_pendientes': open_commitments.count(),
        'compromisos_vencidos': open_commitments.filter(
            commitment_date__lt=today
        ).count(),
        'actividades_mes': active_activities.filter(
            date__gte=month_start,
            date__lte=today,
        ).count(),
        'actividades_por_validar': active_activities.filter(
            state_validity='PENDING',
        ).count(),
        'atenciones_mes': active_attentions.filter(
            created_at__date__gte=month_start,
            created_at__date__lte=today,
        ).count(),
        'actividades_recientes': active_activities.select_related(
            'functionary',
            'measuring',
        ).order_by('-created_at')[:6],
        'atenciones_recientes': active_attentions.select_related(
            'delegation',
            'attention_type',
        ).order_by('-created_at')[:5],
        'compromisos_vencidos_lista': open_commitments.filter(
            commitment_date__lt=today,
        ).select_related('functionary').order_by('commitment_date')[:5],
        'today': today,
    }
    return render(request, 'analytics/admin_dashboard.html', context)


@login_required
def delegation_dashboard(request):
    if not (
        request.user.is_staff
        or request.user.is_superuser
        or _active_functionary_admin(request.user)
    ):
        raise PermissionDenied

    period = Period.objects.filter(status=True).order_by('-start_date').first()
    delegations = Delegation.objects.filter(
        deleted_at__isnull=True,
    ).annotate(
        functionary_count=Count(
            'functionary',
            filter=Q(functionary__deleted_at__isnull=True),
        ),
    )
    search_query = request.GET.get('q', '').strip()
    if search_query:
        delegations = delegations.filter(
            Q(name__icontains=search_query)
            | Q(code__icontains=search_query)
        )

    functionary_filter = request.GET.get('funcionarios', '')
    if functionary_filter == 'con':
        delegations = delegations.filter(functionary_count__gt=0)
    elif functionary_filter == 'sin':
        delegations = delegations.filter(functionary_count=0)

    delegations = delegations.order_by(
        '-functionary_count',
        'name',
    )

    try:
        page_size = int(request.GET.get('per_page', '3'))
    except (TypeError, ValueError):
        page_size = 3
    if page_size not in (1, 3):
        page_size = 3
    page_obj = Paginator(delegations, page_size).get_page(
        request.GET.get('page')
    )
    delegation_summaries = []

    if period:
        expected_percentage = calcular_porcentaje_esperado(period)
        for delegation in page_obj.object_list:
            functionaries = list(
                Functionary.objects.filter(
                    delegation=delegation,
                    deleted_at__isnull=True,
                )
                .select_related('position', 'delegation')
                .order_by('lastnames', 'names')
            )
            metrics, _ = obtener_semaforo_funcionarios(
                functionaries,
                period,
                expected_percentage,
            )
            measured_percentages = [
                item['achieved_percentage']
                for item in metrics
                if item['achieved_percentage'] is not None
            ]
            average_percentage = (
                round(
                    sum(measured_percentages) / len(measured_percentages),
                    1,
                )
                if measured_percentages
                else None
            )
            delegation_summaries.append({
                'delegation': delegation,
                'average_percentage': average_percentage,
                'functionary_count': delegation.functionary_count,
                'measured_functionary_count': len(measured_percentages),
            })
    else:
        delegation_summaries = [
            {
                'delegation': delegation,
                'average_percentage': None,
                'functionary_count': delegation.functionary_count,
                'measured_functionary_count': 0,
            }
            for delegation in page_obj.object_list
        ]

    query_params = request.GET.copy()
    query_params.pop('page', None)

    return render(
        request,
        'analytics/delegation_dashboard.html',
        {
            'delegation_summaries': delegation_summaries,
            'period': period,
            'page_obj': page_obj,
            'page_size_options': (1, 3),
            'selected_page_size': page_size,
            'query_params': query_params.urlencode(),
            'search_query': search_query,
            'functionary_filter': functionary_filter,
        },
    )
# Create your views here.

@login_required
def user_dashboard(request):
    funcionario = getattr(request.user, 'functionary', None)
    if funcionario is None:
        return render(request, 'analytics/no_functionary.html')

    today = timezone.localdate()
    month_start = _month_start()
    period = Period.objects.filter(
        status=True,
        deleted_at__isnull=True,
    ).order_by('-start_date').first()
    indicador = obtener_indicador_funcionario(funcionario, period) if period else None
    my_commitments = funcionario.commitments.filter(deleted_at__isnull=True)
    open_commitments = my_commitments.exclude(state=Commitment.State.DONE)
    my_activities = Activity.objects.filter(
        functionary=funcionario,
        deleted_at__isnull=True,
    )
    my_attentions = Attention.objects.filter(
        functionary=funcionario,
        deleted_at__isnull=True,
    )

    context = {
        'funcionario': funcionario,
        'mis_compromisos': my_commitments.select_related(
            'measuring'
        ).order_by('commitment_date')[:6],
        'compromisos_abiertos': open_commitments.count(),
        'compromisos_vencidos': open_commitments.filter(
            commitment_date__lt=today
        ).count(),
        'actividades_mes': my_activities.filter(
            date__gte=month_start,
            date__lte=today,
        ).count(),
        'actividades_por_validar': my_activities.filter(
            state_validity='PENDING'
        ).count(),
        'atenciones_mes': my_attentions.filter(
            created_at__date__gte=month_start,
            created_at__date__lte=today,
        ).count(),
        'actividades_recientes': my_activities.select_related(
            'measuring'
        ).order_by('-created_at')[:5],
        'period': period,
        'indicador': indicador,
        'today': today,
    }
    return render(request, 'analytics/user_dashboard.html', context)


@login_required
def dashboard_redirect(request):
    functionary = getattr(request.user, 'functionary', None)
    if request.user.is_staff or request.user.is_superuser or (
        functionary
        and functionary.is_admin
        and functionary.is_active
        and functionary.deleted_at is None
    ):
        return delegation_dashboard(request)
    return redirect('user_dashboard')


def _active_functionary(user):
    functionary = getattr(user, 'functionary', None)
    if (
        functionary is None
        or not functionary.is_active
        or functionary.deleted_at is not None
    ):
        return None
    return functionary