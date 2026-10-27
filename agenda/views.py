from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import Commitment
from .forms import CommitmentForm
from personal.models import Functionary
from core.mixins import (
    AdminRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    FunctionaryRequiredMixin,
)
from core.exports import excel_response
from core.lists import search_queryset
from activities.models import Activity


def get_commitment_scope(user):
    commitments = Commitment.objects.select_related(
        'functionary',
        'functionary__delegation',
    )
    if user.is_staff or user.is_superuser:
        return commitments

    functionary = getattr(user, 'functionary', None)
    if functionary is None:
        return commitments.none()
    if functionary.has_global_scope:
        return commitments
    if functionary.is_delegate:
        return commitments.filter(functionary__delegation=functionary.delegation)
    return commitments.filter(functionary=functionary)


class CommitmentListView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, ListView):
    model = Commitment
    template_name = 'agenda/commitment_list.html'
    context_object_name = 'commitments'
    ordering = ['commitment_date']
    paginate_by = 20

    def get_queryset(self):
        queryset = get_commitment_scope(self.request.user)
        
        state = self.request.GET.get('state')
        functionary_id = self.request.GET.get('functionary')
        territory = self.request.GET.get('territory')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if state:
            queryset = queryset.filter(state=state)
        if functionary_id:
            queryset = queryset.filter(functionary_id=functionary_id)
        if territory:
            queryset = queryset.filter(territory__icontains=territory)
        if date_from:
            queryset = queryset.filter(commitment_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(commitment_date__lte=date_to)
        queryset = search_queryset(
            queryset,
            self.request.GET.get('q'),
            'origin',
            'applic_name',
            'territory',
            'observation',
            'functionary__names',
            'functionary__lastnames',
        )

        return queryset

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'compromisos.xlsx',
                ['Origen', 'Solicitante', 'Territorio', 'Fecha compromiso',
                 'Estado', 'Responsable', 'Delegación', 'Observación'],
                (
                    [
                        commitment.origin,
                        commitment.applic_name,
                        commitment.territory,
                        commitment.commitment_date,
                        commitment.get_state_display(),
                        commitment.functionary.full_name,
                        commitment.functionary.delegation.name,
                        commitment.observation,
                    ]
                    for commitment in self.get_queryset()
                ),
            )
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('export', None)
        context['query_params'] = query_params.urlencode()
        context['search_query'] = self.request.GET.get('q', '')
        return super().render_to_response(context, **response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context['states'] = Commitment.State.choices
        commitments = get_commitment_scope(self.request.user)
        functionary = getattr(self.request.user, 'functionary', None)
        context['can_delete_commitments'] = (
            self.request.user.is_superuser
            or (functionary is not None and functionary.is_admin)
        )
        if (
            self.request.user.is_staff
            or self.request.user.is_superuser
            or (functionary is not None and functionary.has_global_scope)
        ):
            context['functionaries'] = Functionary.objects.filter(
                is_active=True,
                deleted_at__isnull=True,
            )
        elif functionary is not None and functionary.is_delegate:
            context['functionaries'] = Functionary.objects.filter(
                delegation=functionary.delegation,
                is_active=True,
            )
        else:
            context['functionaries'] = Functionary.objects.filter(
                pk=functionary.pk,
                is_active=True,
            )
        context['selected_state'] = self.request.GET.get('state', '')
        context['selected_functionary'] = self.request.GET.get('functionary', '')
        context['selected_territory'] = self.request.GET.get('territory', '')
        context['today'] = today
        total_count = commitments.count()
        realized_count = commitments.filter(state=Commitment.State.DONE).count()
        context['completion_percentage'] = round((realized_count / total_count * 100), 1) if total_count > 0 else 0
        context['pending_count'] = commitments.exclude(state=Commitment.State.DONE).count()
        context['expired_count'] = commitments.filter(
            commitment_date__lt=today
        ).exclude(state=Commitment.State.DONE).count()
        return context


class CommitmentCreateView(LoginRequiredMixin, FunctionaryRequiredMixin, CreateView):
    model = Commitment
    form_class = CommitmentForm
    template_name = 'agenda/commitment_form.html'
    success_url = reverse_lazy('agenda:commitment_list')

    def get_initial(self):
        initial = super().get_initial()
        functionary = getattr(self.request.user, 'functionary', None)
        if functionary is not None:
            initial['functionary'] = functionary.pk
        activity_id = self.request.GET.get('activity_id')
        if activity_id:
            initial['activity_id'] = activity_id
            activity = self._get_linkable_activity(activity_id)
            if activity is not None:
                initial['measuring'] = activity.measuring_id
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        functionary = getattr(self.request.user, 'functionary', None)
        if functionary is not None:
            kwargs['delegation'] = functionary.delegation
        return kwargs

    def _get_linkable_activity(self, activity_id):
        functionary = getattr(self.request.user, 'functionary', None)
        if functionary is None or not str(activity_id).isdigit():
            return None
        return Activity.objects.filter(
            pk=activity_id,
            functionary=functionary,
            enters_pipe=True,
            commitment__isnull=True,
        ).select_related('measuring').first()

    @transaction.atomic
    def form_valid(self, form):
        functionary = getattr(self.request.user, 'functionary', None)
        if functionary is None:
            form.add_error(
                None,
                'Tu usuario no tiene un perfil de funcionario asociado.',
            )
            return self.form_invalid(form)

        activity_id = form.cleaned_data.get('activity_id')
        activity = None
        if activity_id:
            activity = self._get_linkable_activity(activity_id)
            if activity is None:
                form.add_error(
                    None,
                    'La actividad no está disponible para vincular a este compromiso.',
                )
                return self.form_invalid(form)
            form.instance.measuring = activity.measuring

        response = super().form_valid(form)
        if activity is not None:
            activity.commitment = self.object
            activity.save(update_fields=['commitment', 'updated_at'])
        messages.success(self.request, 'Compromiso registrado correctamente.')
        return response


class CommitmentUpdateView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, UpdateView):
    model = Commitment
    form_class = CommitmentForm
    template_name = 'agenda/commitment_form.html'
    success_url = reverse_lazy('agenda:commitment_list')

    def get_queryset(self):
        return get_commitment_scope(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['delegation'] = self.object.functionary.delegation
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Compromiso actualizado.')
        return response


class CommitmentDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Commitment
    template_name = 'agenda/commitment_confirm_delete.html'
    success_url = reverse_lazy('agenda:commitment_list')

    def get_queryset(self):
        return get_commitment_scope(self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Compromiso eliminado correctamente.')
        return response