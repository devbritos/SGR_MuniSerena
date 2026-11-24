from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
)
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction
from django.core.paginator import Paginator
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, DetailView, View

from core.exports import excel_response
from core.lists import ListControlsMixin, apply_list_sort, search_queryset
from core.mixins import (
    AdminRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
    FunctionaryRequiredMixin,
    _active_functionary,
)

from .forms import OfficeLetterFilterForm, OfficeLetterForm, LetterAttentionCreateForm, LetterAttentionLinkForm
from .models import OfficeLetter
from atenciones.models import Attention, AttentionType, AttentionFollowUp
from atenciones.views import visible_attentions


def get_office_letter_scope(user):
    queryset = OfficeLetter.objects.filter(
        deleted_at__isnull=True,
        delegation__deleted_at__isnull=True,
    ).select_related(
        'delegation',
        'responsible',
        'responsible__position',
        'registered_by',
        'attention',
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
                    'Atención vinculada',
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
                        letter.attention_id or '',
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

    def get_success_url(self):
        return reverse_lazy('correspondence:letter_detail', kwargs={'pk': self.object.pk})

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

    def get_success_url(self):
        return reverse_lazy('correspondence:letter_detail', kwargs={'pk': self.object.pk})

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


class OfficeLetterDetailView(LoginRequiredMixin, FunctionaryOrStaffRequiredMixin, DetailView):
    template_name = 'correspondence/letter_detail.html'
    context_object_name = 'letter'

    def get_queryset(self):
        return get_office_letter_scope(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_link_attention'] = _active_functionary(self.request.user) is not None
        return context


def record_letter_attention_link(letter, attention, author, *, created):
    letter.attention = attention
    letter.full_clean()
    letter.save(update_fields=['attention', 'updated_at'])
    reference = f'carta #{letter.pk}'
    if letter.registry_number:
        reference += f' (registro {letter.registry_number})'
    AttentionFollowUp.objects.create(
        attention=attention, author=author,
        note=f'Atención creada desde {reference}.' if created else f'Se vinculó la {reference} a esta atención.',
        status=attention.status, responsible=attention.followup_responsible,
        next_action=attention.next_action, next_contact_date=attention.next_contact_date,
        closure_outcome=attention.closure_outcome, closure_details=attention.closure_details,
    )
    attention.save(update_fields=['updated_at'])


class LetterAttentionActionView(LoginRequiredMixin, FunctionaryRequiredMixin, View):
    def get_letter(self, pk, *, lock=False):
        queryset = get_office_letter_scope(self.request.user)
        if lock:
            queryset = OfficeLetter.objects.select_for_update().filter(pk__in=queryset.values('pk'))
        return get_object_or_404(queryset, pk=pk)

    def already_linked(self, letter):
        messages.info(self.request, 'Esta carta ya tiene una atención vinculada. No se creó un duplicado.')
        return redirect('correspondence:letter_detail', pk=letter.pk)


class OfficeLetterAttentionCreateView(LetterAttentionActionView):
    def make_form(self, letter, data=None):
        responsible = letter.responsible
        return LetterAttentionCreateForm(data, delegation=letter.delegation, initial={
            'requester_name': letter.sender, 'requester_contact': letter.contact_phone,
            'description': letter.subject,
            'followup_responsible': responsible.pk if responsible.is_active and responsible.deleted_at is None else None,
        })

    def render_form(self, letter, form):
        return render(self.request, 'atenciones/attention_form.html', {
            'form': form, 'source_letter': letter,
            'has_active_attention_types': AttentionType.objects.filter(is_active=True, deleted_at__isnull=True).exists(),
            'can_manage_attention_types': self.request.user.is_superuser or self.request.user.functionary.is_admin,
        })

    def get(self, request, pk):
        letter = self.get_letter(pk)
        if letter.attention_id:
            return self.already_linked(letter)
        return self.render_form(letter, self.make_form(letter))

    def post(self, request, pk):
        with transaction.atomic():
            letter = self.get_letter(pk, lock=True)
            if letter.attention_id:
                return self.already_linked(letter)
            form = self.make_form(letter, request.POST)
            if form.is_valid():
                attention = form.save(commit=False)
                attention.functionary = request.user.functionary
                attention.delegation = letter.delegation
                attention.full_clean()
                attention.save()
                record_letter_attention_link(letter, attention, request.user.functionary, created=True)
                messages.success(request, 'Atención creada y vinculada a la carta. El estado de la carta se conserva.')
                return redirect('atenciones:attention_detail', pk=attention.pk)
        return self.render_form(letter, form)


class OfficeLetterAttentionLinkView(LetterAttentionActionView):
    def candidates(self, letter):
        return search_queryset(
            visible_attentions(self.request.user).filter(delegation=letter.delegation),
            self.request.GET.get('q'), 'requester_name', 'requester_contact', 'description',
        ).order_by('-created_at', '-pk')

    def render_form(self, letter, form, candidates):
        selected = self.request.POST.get('attention', '')
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        return render(self.request, 'correspondence/letter_attention_link.html', {
            'letter': letter, 'form': form, 'search_query': self.request.GET.get('q', ''),
            'page_obj': Paginator(candidates, 10).get_page(self.request.GET.get('page')),
            'query_params': query_params.urlencode(),
            'selected_attention': int(selected) if selected.isdecimal() else None,
        })

    def get(self, request, pk):
        letter = self.get_letter(pk)
        if letter.attention_id:
            return self.already_linked(letter)
        candidates = self.candidates(letter)
        return self.render_form(letter, LetterAttentionLinkForm(queryset=candidates), candidates)

    def post(self, request, pk):
        with transaction.atomic():
            letter = self.get_letter(pk, lock=True)
            if letter.attention_id:
                return self.already_linked(letter)
            candidates = self.candidates(letter)
            form = LetterAttentionLinkForm(request.POST, queryset=candidates)
            if form.is_valid():
                attention = get_object_or_404(
                    Attention.objects.select_for_update().filter(pk__in=candidates.values('pk')),
                    pk=form.cleaned_data['attention'].pk,
                )
                record_letter_attention_link(letter, attention, request.user.functionary, created=False)
                messages.success(request, 'Carta vinculada a la atención existente. Sus estados se mantienen separados.')
                return redirect('correspondence:letter_detail', pk=letter.pk)
        return self.render_form(letter, form, candidates)


def _can_delete_letters(user):
    functionary = _active_functionary(user)
    return user.is_superuser or (
        functionary is not None and functionary.is_admin
    )
