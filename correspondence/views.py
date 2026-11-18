from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
)
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.exports import excel_response
from core.lists import ListControlsMixin, apply_list_sort, search_queryset
from core.mixins import (
    AdminRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    _active_functionary,
)

from .forms import OfficeLetterFilterForm, OfficeLetterForm
from .models import OfficeLetter


def get_office_letter_scope(user):
    queryset = OfficeLetter.objects.filter(
        deleted_at__isnull=True,
        delegation__deleted_at__isnull=True,
    ).select_related(
        'delegation',
        'responsible',
        'responsible__position',
        'registered_by',
    )
    functionary = _active_functionary(user)
    if user.is_staff or user.is_superuser or (
        functionary is not None and functionary.has_global_scope
    ):
        return queryset
    if functionary is None:
        return queryset.none()
    if functionary.is_delegate:
        return queryset.filter(delegation=functionary.delegation)
    return queryset.filter(responsible=functionary)


class OfficeLetterListView(
    ListControlsMixin,
    LoginRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    ListView,
):
    model = OfficeLetter
    template_name = 'correspondence/letter_list.html'
    context_object_name = 'letters'
    paginate_by = 20
    sort_fields = {
        'recent': ('-received_at', '-pk'),
        'oldest': ('received_at', 'pk'),
        'az': ('sender', 'pk'),
        'za': ('-sender', '-pk'),
    }

    def get_filter_form(self):
        return OfficeLetterFilterForm(self.request.GET)

    def get_queryset(self):
        queryset = get_office_letter_scope(self.request.user)
        form = self.get_filter_form()
        if form.is_valid():
            filters = form.cleaned_data
            queryset = search_queryset(
                queryset,
                filters['search'],
                'registry_number',
                'recipient',
                'sender',
                'contact_phone',
                'subject',
                'activity_date',
                'pronouncement',
                'referred_to',
                'observation',
                'delegation__name',
                'responsible__names',
                'responsible__lastnames',
            )
            if filters['state']:
                queryset = queryset.filter(state=filters['state'])
            if filters['received_from']:
                queryset = queryset.filter(
                    received_at__gte=filters['received_from'],
                )
            if filters['received_to']:
                queryset = queryset.filter(
                    received_at__lte=filters['received_to'],
                )
        return apply_list_sort(queryset, self.request, self.sort_fields)

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            if not self.get_filter_form().is_valid():
                return super().render_to_response(context, **response_kwargs)
            return excel_response(
                'seguimiento_cartas.xlsx',
                [
                    'Fecha de ingreso',
                    'N.º de registro',
                    'Para',
                    'Remite',
                    'Teléfono',
                    'Actividad o tema',
                    'Fecha de actividad',
                    'Encargado del seguimiento',
                    'Estado',
                    'Pronunciamiento',
                    'Derivada a',
                    'Observación',
                    'Delegación',
                ],
                (
                    [
                        letter.received_at,
                        letter.registry_number,
                        letter.recipient,
                        letter.sender,
                        letter.contact_phone,
                        letter.subject,
                        letter.activity_date,
                        letter.responsible.full_name,
                        letter.get_state_display(),
                        letter.pronouncement,
                        letter.referred_to,
                        letter.observation,
                        letter.delegation.name,
                    ]
                    for letter in self.get_queryset()
                ),
            )
        return super().render_to_response(context, **response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = get_office_letter_scope(self.request.user)
        context['filter_form'] = self.get_filter_form()
        context['in_progress_count'] = queryset.filter(
            state=OfficeLetter.State.IN_PROGRESS,
        ).count()
        context['finalized_count'] = queryset.filter(
            state__in=(
                OfficeLetter.State.APPROVED,
                OfficeLetter.State.FINALIZED,
                OfficeLetter.State.NOT_APPLICABLE,
            ),
        ).count()
        context['can_delete_letters'] = _can_delete_letters(self.request.user)
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('export', None)
        context['query_params'] = query_params.urlencode()
        return context


class OfficeLetterCreateView(
    LoginRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    CreateView,
):
    model = OfficeLetter
    form_class = OfficeLetterForm
    template_name = 'correspondence/letter_form.html'
    success_url = reverse_lazy('correspondence:letter_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        functionary = getattr(self.request.user, 'functionary', None)
        if functionary is not None:
            form.instance.registered_by = functionary
        response = super().form_valid(form)
        messages.success(self.request, 'Carta registrada correctamente.')
        return response


class OfficeLetterUpdateView(
    LoginRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    UpdateView,
):
    model = OfficeLetter
    form_class = OfficeLetterForm
    template_name = 'correspondence/letter_form.html'
    success_url = reverse_lazy('correspondence:letter_list')

    def get_queryset(self):
        return get_office_letter_scope(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Seguimiento de carta actualizado.')
        return response


class OfficeLetterDeleteView(
    LoginRequiredMixin,
    AdminRequiredMixin,
    DeleteView,
):
    model = OfficeLetter
    template_name = 'correspondence/letter_confirm_delete.html'
    success_url = reverse_lazy('correspondence:letter_list')

    def get_queryset(self):
        return get_office_letter_scope(self.request.user)

    def form_valid(self, _form):
        if not _form.is_valid():
            return self.form_invalid(_form)
        self.object.deleted_at = timezone.now()
        self.object.save(update_fields=['deleted_at', 'updated_at'])
        messages.success(self.request, 'Carta archivada correctamente.')
        return redirect(self.success_url)


def _can_delete_letters(user):
    functionary = _active_functionary(user)
    return user.is_superuser or (
        functionary is not None and functionary.is_admin
    )
