from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from personal.models import Functionary, Delegation
from agenda.models import Commitment
from activities.models import Activity
from atenciones.models import Attention
from django.utils import timezone
from .calculations import obtener_indicador_funcionario
from configuration.models import Period


def _month_start():
    return timezone.localdate().replace(day=1)


@login_required
@user_passes_test(
    lambda user: user.is_staff
    or user.is_superuser
    or (
        hasattr(user, 'functionary')
        and user.functionary.is_admin
    )
)
def admin_dashboard(request):
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
        functionary and functionary.is_admin
    ):
        return redirect('admin_dashboard')
    return redirect('user_dashboard')