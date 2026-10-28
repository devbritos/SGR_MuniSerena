import mimetypes

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.utils import timezone
from configuration.models import Goal, Period
from .models import Activity, Evidence, approved_activity_queryset
from .forms import (
    ActivityForm,
    EvidenceForm,
    EvidenceValidationForm,
)
from django.views.generic import TemplateView
from django.db.models import Exists, OuterRef, Sum
from core.exports import excel_response
from core.lists import search_queryset
from personal.models import Functionary
from core.mixins import (
    FunctionaryRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    VerifierRequiredMixin,
)


def get_activity_scope(user):
    activities = Activity.objects.all()
    functionary = getattr(user, 'functionary', None)
    if user.is_staff or user.is_superuser or (
        functionary is not None and functionary.has_global_scope
    ):
        return activities
    if functionary is None:
        return activities.none()
    if functionary.is_delegate or functionary.is_verifier:
        return activities.filter(functionary__delegation=functionary.delegation)
    return activities.filter(functionary=functionary)


# ---------- Activity ----------

class ActivityListView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, ListView):
    model = Activity
    template_name = 'activities/activity_list.html'
    context_object_name = 'activities'
    ordering = ['-date']
    paginate_by = 20

    def get_queryset(self):
        queryset = get_activity_scope(self.request.user).select_related(
            'functionary',
            'functionary__delegation',
            'measuring',
        )
        queryset = search_queryset(
            queryset,
            self.request.GET.get('q'),
            'application',
            'taken_action',
            'name_contact',
            'telephone_contact',
            'measuring__service',
            'measuring__measurable_item',
            'functionary__names',
            'functionary__lastnames',
        )
        return queryset.order_by(*self.ordering)

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'actividades.xlsx',
                ['Fecha', 'Solicitud', 'Acción realizada', 'Contacto',
                 'Teléfono', 'Ítem', 'Cantidad', 'Delegación', 'Responsable',
                 'Estado'],
                (
                    [
                        item.date,
                        item.application,
                        item.taken_action,
                        item.name_contact,
                        item.telephone_contact,
                        item.measuring.service,
                        item.quantity,
                        item.functionary.delegation.name,
                        item.functionary.full_name,
                        item.get_state_validity_display(),
                    ]
                    for item in self.get_queryset()
                ),
            )
        add_pagination_context(self.request, context)
        return super().render_to_response(context, **response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        functionary = getattr(self.request.user, 'functionary', None)
        context['current_functionary_id'] = (
            functionary.pk if functionary is not None else None
        )
        return context


class ActivityCreateView(LoginRequiredMixin, FunctionaryRequiredMixin, CreateView):
    model = Activity
    form_class = ActivityForm
    template_name = 'activities/activity_form.html'
    success_url = reverse_lazy('activities:activity_list')

    def form_valid(self, form):
        # 1. Asigna el funcionario si existe en el usuario logueado
        if hasattr(self.request.user, 'functionary'):
            form.instance.functionary = self.request.user.functionary
        else:
            messages.error(
                self.request,
                'Tu usuario no tiene un perfil de Funcionario asociado.',
            )
            return self.form_invalid(form)

        # 2. Guarda la actividad en la BD y genera self.object
        submission_key = form.cleaned_data['submission_key']
        form.instance.submission_token = submission_key
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except IntegrityError:
            if not Activity.objects.filter(
                submission_token=submission_key
            ).exists():
                raise
            messages.info(
                self.request,
                'Esta actividad ya se registró; se evitó duplicar el envío.',
            )
            return redirect(self.success_url)
        messages.success(self.request, 'Actividad registrada correctamente.')

        if form.cleaned_data.get('upload_evidence'):
            evidence_url = reverse('activities:evidence_create')
            query = f'?activity_id={self.object.pk}'
            if self.object.enters_pipe:
                query += '&continue_commitment=1'
            return redirect(f'{evidence_url}{query}')

        if getattr(self.object, 'enters_pipe', False):
            url_compromiso = reverse('agenda:commitment_create')
            return redirect(f'{url_compromiso}?activity_id={self.object.id}')

        return response

class ActivityUpdateView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, UpdateView):
    model = Activity
    form_class = ActivityForm
    template_name = 'activities/activity_form.html'
    success_url = reverse_lazy('activities:activity_list')

    def get_queryset(self):
        return get_activity_scope(self.request.user)

    @transaction.atomic
    def form_valid(self, form):
        latest_evidence = self.object.evidences.order_by(
            '-created_at',
            '-pk',
        ).first()
        if (
            latest_evidence is not None
            and latest_evidence.validity_state == Evidence.Validity.APPROVED
        ):
            latest_evidence.validity_state = Evidence.Validity.PENDING
            latest_evidence.date_validity = None
            latest_evidence.verificator = None
            latest_evidence.observations_validity = ''
            latest_evidence.save(update_fields=[
                'validity_state',
                'date_validity',
                'verificator',
                'observations_validity',
                'updated_at',
            ])
            form.instance.state_validity = 'PENDING'
        response = super().form_valid(form)
        messages.success(self.request, 'Actividad actualizada correctamente.')
        return response


class ActivityDeleteView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, DeleteView):
    model = Activity
    template_name = 'activities/activity_confirm_delete.html'
    success_url = reverse_lazy('activities:activity_list')

    def get_queryset(self):
        return get_activity_scope(self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Actividad eliminada correctamente.')
        return response


# ---------- Evidence ----------

class EvidenceListView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, ListView):
    model = Evidence
    template_name = 'activities/evidence_list.html'
    context_object_name = 'evidences'
    ordering = ['-created_at']
    paginate_by = 20

    def get_queryset(self):
        latest_evidence = Evidence.objects.filter(
            activity_id=OuterRef('activity_id'),
        ).order_by('-created_at', '-pk')
        queryset = get_evidence_scope(self.request.user).annotate(
            is_latest=Exists(latest_evidence.filter(pk=OuterRef('pk'))),
        ).select_related(
            'activity',
            'functionary',
            'functionary__delegation',
        )
        queryset = search_queryset(
            queryset,
            self.request.GET.get('q'),
            'name',
            'author',
            'metadata',
            'activity__application',
            'functionary__names',
            'functionary__lastnames',
        )
        return queryset.order_by(*self.ordering)

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'evidencias.xlsx',
                ['Nombre', 'Actividad', 'Autor', 'Fecha', 'Estado',
                 'Funcionario', 'Delegación'],
                (
                    [
                        evidence.name,
                        evidence.activity.application,
                        evidence.author,
                        evidence.date_evidence,
                        evidence.get_validity_state_display(),
                        evidence.functionary.full_name,
                        evidence.functionary.delegation.name,
                    ]
                    for evidence in self.get_queryset()
                ),
            )
        add_pagination_context(self.request, context)
        return super().render_to_response(context, **response_kwargs)


class EvidenceCreateView(LoginRequiredMixin, FunctionaryRequiredMixin, CreateView):
    model = Evidence
    form_class = EvidenceForm
    template_name = 'activities/evidence_form.html'
    success_url = reverse_lazy('activities:evidence_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        user = self.request.user
        functionary = user.functionary
        kwargs['activities'] = get_activity_scope(user).filter(
            functionary=functionary,
        )
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        activity_id = self.request.GET.get('activity_id')
        functionary = getattr(self.request.user, 'functionary', None)
        if (
            functionary is not None
            and activity_id
            and str(activity_id).isdigit()
            and get_activity_scope(self.request.user).filter(
                pk=activity_id,
                functionary=functionary,
            ).exists()
        ):
            initial['activity'] = activity_id
        return initial

    @transaction.atomic
    def form_valid(self, form):
        form.instance.functionary = self.request.user.functionary
        evidence = form.save(commit=False)
        self.object = evidence
        activity = evidence.activity
        evidence.save()
        activity.state_validity = 'PENDING'
        activity.save(update_fields=['state_validity', 'updated_at'])
        messages.success(self.request, 'Evidencia subida correctamente.')
        if (
            self.request.GET.get('continue_commitment') == '1'
            and activity.enters_pipe
        ):
            commitment_url = reverse('agenda:commitment_create')
            return redirect(f'{commitment_url}?activity_id={activity.pk}')
        return redirect(self.get_success_url())


class EvidenceValidateView(
    LoginRequiredMixin,
    VerifierRequiredMixin,
    UpdateView,
):
    model = Evidence
    form_class = EvidenceValidationForm
    template_name = 'activities/evidence_validate.html'
    success_url = reverse_lazy('activities:evidence_list')

    def get_queryset(self):
        latest_evidence = Evidence.objects.filter(
            activity_id=OuterRef('activity_id'),
        ).order_by('-created_at', '-pk')
        queryset = get_evidence_scope(self.request.user)
        functionary = getattr(self.request.user, 'functionary', None)
        is_admin = (
            self.request.user.is_staff
            or self.request.user.is_superuser
            or (functionary is not None and functionary.is_admin)
        )
        if functionary is not None and not is_admin:
            queryset = queryset.exclude(functionary=functionary)
        return queryset.annotate(
            is_latest=Exists(latest_evidence.filter(pk=OuterRef('pk'))),
        ).filter(
            is_latest=True,
            validity_state=Evidence.Validity.PENDING,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['verificator'] = getattr(self.request.user, 'functionary', None)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        evidence = form.save(commit=False)
        evidence.date_validity = timezone.localdate()
        evidence.save()
        activity = evidence.activity
        activity.state_validity = (
            'VALIDATED'
            if evidence.validity_state == Evidence.Validity.APPROVED
            else 'REJECTED'
        )
        activity.save(update_fields=['state_validity', 'updated_at'])
        if evidence.validity_state == Evidence.Validity.APPROVED:
            messages.success(
                self.request,
                'Evidencia aprobada; la actividad ahora suma a su avance.',
            )
        else:
            messages.warning(
                self.request,
                'Evidencia rechazada; la actividad queda en pausa hasta que se cargue una corrección aprobada.',
            )
        return redirect(self.get_success_url())


class EvidenceFileView(LoginRequiredMixin, View):
    def get(self, request, pk):
        evidence = get_object_or_404(
            get_evidence_scope(request.user).filter(deleted_at__isnull=True),
            pk=pk,
        )
        if not evidence.file or not evidence.file.storage.exists(evidence.file.name):
            raise Http404('El archivo de evidencia no existe.')

        content_type = mimetypes.guess_type(evidence.file.name)[0]
        inline_types = {
            'application/pdf',
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
        }
        can_display_inline = content_type in inline_types
        response = FileResponse(
            evidence.file.open('rb'),
            as_attachment=not can_display_inline,
            filename=evidence.file.name.rsplit('/', 1)[-1],
            content_type=content_type if can_display_inline else 'application/octet-stream',
        )
        response['X-Content-Type-Options'] = 'nosniff'
        return response


# Create your views here.


class TrafficLightView(
    LoginRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    TemplateView,
):
    template_name = 'activities/traffic_light.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        period = Period.objects.filter(status=True).order_by('-start_date').first()
        
        if not period:
            context['error'] = "No hay un período de medición activo configurado."
            return context

        # 2. Cálculos del Período (Avance Esperado al Día)
        total_days = (period.end_date - period.start_date).days + 1
        
        if today < period.start_date:
            elapsed_days = 0
        elif today > period.end_date:
            elapsed_days = total_days
        else:
            elapsed_days = (today - period.start_date).days + 1

        expected_percentage = (elapsed_days / total_days * 100) if total_days > 0 else 0

        # 3. Métrica por Funcionario
        functionaries = Functionary.objects.filter(
            deleted_at__isnull=True
        ).select_related('position', 'delegation')
        user = self.request.user
        if not user.is_superuser and not user.is_staff:
            functionary = user.functionary
            if not functionary.has_global_scope:
                if functionary.is_delegate:
                    functionaries = functionaries.filter(
                        delegation=functionary.delegation
                    )
                else:
                    functionaries = functionaries.filter(pk=functionary.pk)
        traffic_light_data = []
        active_goals = Goal.objects.filter(
            period=period,
            validity=True,
            deleted_at__isnull=True,
            measuring__validity=True,
            measuring__deleted_at__isnull=True,
        )
        validated_activities = approved_activity_queryset(Activity.objects.filter(
            date__range=[period.start_date, period.end_date],
            deleted_at__isnull=True,
            functionary__in=functionaries,
        ))
        context['unmatched_validated_activity_count'] = (
            validated_activities.annotate(
                has_active_goal=Exists(
                    active_goals.filter(
                        position=OuterRef('functionary__position'),
                        measuring=OuterRef('measuring'),
                    )
                )
            )
            .filter(has_active_goal=False)
            .count()
        )

        for func in functionaries:
            # Obtener las metas configuradas para el cargo del funcionario en este período
            goals = active_goals.filter(
                position=func.position,
            ).select_related('measuring')
            has_active_goals = goals.exists()

            total_weighted_compliance = 0.0
            matched_activity_count = 0

            for goal in goals:
                # Sumar actividades realizadas y validadas por el funcionario para esta meta/ítem
                # Usas la suma acumulada de la cantidad:
                achieved_query = approved_activity_queryset(Activity.objects.filter(
                    functionary=func,
                    measuring=goal.measuring,
                    date__range=[period.start_date, period.end_date],
                    deleted_at__isnull=True,
                )).aggregate(total=Sum('quantity'))

                achieved = achieved_query['total'] or 0
                if achieved:
                    matched_activity_count += 1

                # Porcentaje de cumplimiento del ítem (Avance / Meta)
                target_value = float(goal.target_value)
                item_compliance = (achieved / target_value) if target_value > 0 else 0
                # Cap de 100% por ítem antes de ponderar (opcional según reglas)
                item_compliance = min(item_compliance, 1.0)

                # Sumar al cumplimiento ponderado
                total_weighted_compliance += item_compliance * float(goal.weight)

            # 4. Determinar Estado del Semáforo (Verde, Amarillo, Rojo)
            # Diferencia entre lo logrado y lo esperado
            diff = total_weighted_compliance - expected_percentage

            if not has_active_goals:
                status = 'no_goal'
                label = 'Sin meta activa para este cargo'
            elif diff >= -5:
                status = 'green'    # En línea o superior
                label = 'En línea con lo esperado'
            elif -15 <= diff < -5:
                status = 'yellow'   # Atención
                label = 'Atención'
            else:
                status = 'red'      # Bajo lo esperado
                label = 'Bajo lo esperado'

            traffic_light_data.append({
                'functionary': func,
                'achieved_percentage': (
                    round(total_weighted_compliance, 1)
                    if has_active_goals
                    else None
                ),
                'expected_percentage': round(expected_percentage, 1),
                'has_active_goals': has_active_goals,
                'has_matched_activities': matched_activity_count > 0,
                'status': status,
                'label': label,
            })

        # Contexto final para el template
        context['period'] = period
        context['today'] = today
        context['total_days'] = total_days
        context['elapsed_days'] = elapsed_days
        context['expected_percentage'] = round(expected_percentage, 1)
        context['traffic_light_data'] = traffic_light_data

        return context


def get_evidence_scope(user):
    evidences = Evidence.objects.all()
    functionary = getattr(user, 'functionary', None)
    if user.is_staff or user.is_superuser or (
        functionary is not None and functionary.has_global_scope
    ):
        return evidences
    if functionary is None:
        return evidences.none()
    if functionary.is_delegate or functionary.is_verifier:
        return evidences.filter(functionary__delegation=functionary.delegation)
    return evidences.filter(functionary=functionary)


def add_pagination_context(request, context):
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_params.pop('export', None)
    context['query_params'] = query_params.urlencode()
    context['search_query'] = request.GET.get('q', '')