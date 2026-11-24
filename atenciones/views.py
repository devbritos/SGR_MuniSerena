from django.contrib import messages
import uuid
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, UpdateView, View

from core.mixins import AdminRequiredMixin, FunctionaryRequiredMixin
from core.exports import excel_response
from core.lists import (
    ListControlsMixin,
    apply_list_sort,
    list_controls_context,
    search_queryset,
)
from core.mixins import _active_functionary

from .forms import AttentionForm, AttentionTypeForm, SubAttentionForm, AttentionFollowUpForm, AttentionCommitmentForm
from .models import Attention, AttentionType, SubAttention, AttentionFollowUp
from agenda.models import Commitment
from organizations.models import Organization


class AttentionTypeListView(ListControlsMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = AttentionType
    template_name = 'atenciones/type_list.html'
    context_object_name = 'object_list'
    paginate_by = 20
    sort_fields = {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('name', 'pk'),
        'za': ('-name', '-pk'),
    }

    def get_queryset(self):
        queryset = AttentionType.objects.filter(deleted_at__isnull=True)
        queryset = search_queryset(
            queryset, self.request.GET.get('q'), 'code', 'name', 'description'
        )
        queryset = queryset.order_by('name')
        return apply_list_sort(queryset, self.request, self.sort_fields)

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'tipos_de_atencion.xlsx',
                ['Código', 'Nombre', 'Descripción', 'Estado'],
                (
                    [item.code, item.name, item.description,
                     'Activo' if item.is_active else 'Inactivo']
                    for item in self.get_queryset()
                ),
            )
        return list_response(self, context, response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['catalog_title'] = 'Tipo de atención'
        return add_list_context(self.request, context)


class AttentionTypeCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = AttentionType
    form_class = AttentionTypeForm
    template_name = 'atenciones/catalog_form.html'
    success_url = reverse_lazy('atenciones:attention_type_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Tipo de atención guardado correctamente.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['catalog_title'] = 'Tipo de atención'
        return context


class AttentionTypeUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = AttentionType
    form_class = AttentionTypeForm
    template_name = 'atenciones/catalog_form.html'
    success_url = reverse_lazy('atenciones:attention_type_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Tipo de atención actualizado correctamente.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['catalog_title'] = 'Tipo de atención'
        return context


class AttentionTypeDeactivateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, pk):
        return render(
            request,
            'atenciones/catalog_confirm_deactivate.html',
            {
                'object': get_object_or_404(AttentionType, pk=pk),
                'catalog_title': 'tipo de atención',
                'cancel_url': reverse_lazy('atenciones:attention_type_list'),
            },
        )

    def post(self, request, pk):
        attention_type = get_object_or_404(AttentionType, pk=pk)
        attention_type.is_active = False
        attention_type.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, 'Tipo de atención desactivado correctamente.')
        return redirect('atenciones:attention_type_list')


class SubAttentionListView(ListControlsMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = SubAttention
    template_name = 'atenciones/subattention_list.html'
    context_object_name = 'object_list'
    paginate_by = 20
    sort_fields = {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('name', 'pk'),
        'za': ('-name', '-pk'),
    }

    def get_queryset(self):
        queryset = SubAttention.objects.filter(
            deleted_at__isnull=True
        ).select_related('attention_type')
        queryset = search_queryset(
            queryset, self.request.GET.get('q'), 'code', 'name',
            'description', 'attention_type__name',
        )
        type_id = self.request.GET.get('type')
        if type_id and type_id.isdigit():
            queryset = queryset.filter(attention_type_id=type_id)
        return apply_list_sort(queryset, self.request, self.sort_fields)

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'subatenciones.xlsx',
                ['Código', 'Nombre', 'Descripción', 'Tipo', 'Estado'],
                (
                    [item.code, item.name, item.description,
                     item.attention_type.name,
                     'Activo' if item.is_active else 'Inactivo']
                    for item in self.get_queryset()
                ),
            )
        return list_response(self, context, response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['catalog_title'] = 'Subatención'
        context['attention_types'] = AttentionType.objects.order_by('name')
        return add_list_context(self.request, context)


class SubAttentionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = SubAttention
    form_class = SubAttentionForm
    template_name = 'atenciones/catalog_form.html'
    success_url = reverse_lazy('atenciones:subattention_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Subatención guardada correctamente.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['catalog_title'] = 'Subatención'
        return context


class SubAttentionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = SubAttention
    form_class = SubAttentionForm
    template_name = 'atenciones/catalog_form.html'
    success_url = reverse_lazy('atenciones:subattention_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Subatención actualizada correctamente.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['catalog_title'] = 'Subatención'
        return context


class SubAttentionDeactivateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, pk):
        return render(
            request,
            'atenciones/catalog_confirm_deactivate.html',
            {
                'object': get_object_or_404(SubAttention, pk=pk),
                'catalog_title': 'subatención',
                'cancel_url': reverse_lazy('atenciones:subattention_list'),
            },
        )

    def post(self, request, pk):
        subattention = get_object_or_404(SubAttention, pk=pk)
        subattention.is_active = False
        subattention.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, 'Subatención desactivada correctamente.')
        return redirect('atenciones:subattention_list')


class AttentionListView(ListControlsMixin, LoginRequiredMixin, FunctionaryRequiredMixin, ListView):
    model = Attention
    template_name = 'atenciones/attention_list.html'
    context_object_name = 'object_list'
    paginate_by = 20
    sort_fields = {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('requester_name', 'pk'),
        'za': ('-requester_name', '-pk'),
    }

    def get_queryset(self):
        queryset = visible_attentions(self.request.user)
        queryset = search_queryset(
            queryset,
            self.request.GET.get('q'),
            'requester_name',
            'requester_contact',
            'description',
            'attention_type__name',
            'sub_attention__name',
            'delegation__name',
            'functionary__names',
            'functionary__lastnames',
            'followup_responsible__names',
            'followup_responsible__lastnames',
            'next_action',
        )
        status = self.request.GET.get('status', '')
        if status in Attention.Status.values:
            queryset = queryset.filter(status=status)
        followup = self.request.GET.get('followup', '')
        if followup == 'overdue':
            queryset = queryset.exclude(status=Attention.Status.CLOSED).filter(next_contact_date__lt=timezone.localdate())
        elif followup == 'today':
            queryset = queryset.exclude(status=Attention.Status.CLOSED).filter(next_contact_date=timezone.localdate())
        elif followup == 'mine':
            queryset = queryset.exclude(status=Attention.Status.CLOSED).filter(followup_responsible=self.request.user.functionary)
        elif followup == 'open':
            queryset = queryset.filter(status__in=[Attention.Status.PENDING, Attention.Status.IN_PROGRESS])
        return apply_list_sort(queryset, self.request, self.sort_fields)

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'atenciones_ciudadanas.xlsx',
                [
                    'Fecha y hora', 'Solicitante', 'Contacto', 'Tipo',
                    'Subatención', 'Descripción', 'Delegación',
                    'Usuario responsable',
                    'Estado', 'Responsable del seguimiento', 'Próxima acción',
                    'Fecha de próxima acción', 'Resultado del cierre', 'Detalle del cierre', 'Fecha de cierre',
                ],
                (
                    [
                        timezone.localtime(attention.created_at).strftime(
                            '%d/%m/%Y %H:%M'
                        ),
                        attention.requester_name,
                        attention.requester_contact,
                        attention.attention_type.name,
                        attention.sub_attention.name,
                        attention.description,
                        attention.delegation.name,
                        attention.functionary.full_name,
                        attention.get_status_display(),
                        attention.followup_responsible.full_name if attention.followup_responsible else '',
                        attention.next_action,
                        attention.next_contact_date.strftime('%d/%m/%Y') if attention.next_contact_date else '',
                        attention.get_closure_outcome_display(),
                        attention.closure_details,
                        timezone.localtime(attention.closed_at).strftime('%d/%m/%Y %H:%M') if attention.closed_at else '',
                    ]
                    for attention in self.get_queryset()
                ),
            )
        return list_response(self, context, response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Attention.Status.choices
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_followup'] = self.request.GET.get('followup', '')
        context['summary'] = visible_attentions(self.request.user).aggregate(
            pending=Count('pk', filter=Q(status__in=[Attention.Status.PENDING, Attention.Status.IN_PROGRESS])),
            overdue=Count('pk', filter=~Q(status=Attention.Status.CLOSED) & Q(next_contact_date__lt=timezone.localdate())),
            today=Count('pk', filter=~Q(status=Attention.Status.CLOSED) & Q(next_contact_date=timezone.localdate())),
            unclassified=Count('pk', filter=Q(status=Attention.Status.UNCLASSIFIED)),
        )
        return add_list_context(self.request, context)


class AttentionFormContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        functionary = _active_functionary(self.request.user)
        has_active_attention_types = AttentionType.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ).exists()
        context['has_active_attention_types'] = (
            has_active_attention_types
            or getattr(self, 'object', None) is not None
        )
        context['can_manage_attention_types'] = (
            self.request.user.is_superuser
            or (functionary is not None and functionary.is_admin)
        )
        return context


class AttentionCreateView(
    LoginRequiredMixin,
    FunctionaryRequiredMixin,
    AttentionFormContextMixin,
    CreateView,
):
    model = Attention
    form_class = AttentionForm
    template_name = 'atenciones/attention_form.html'
    success_url = reverse_lazy('atenciones:attention_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        organization_id = self.request.GET.get('organization')
        if organization_id and organization_id.isdigit():
            functionary = _active_functionary(self.request.user)
            organization = Organization.objects.filter(
                pk=organization_id,
                delegation_id=functionary.delegation_id,
                deleted_at__isnull=True,
            ).first()
            if organization:
                initial['organization'] = organization.pk
        return initial

    def form_valid(self, form):
        functionary = self.request.user.functionary
        form.instance.functionary = functionary
        form.instance.delegation = functionary.delegation
        form.instance.followup_responsible = functionary
        response = super().form_valid(form)
        messages.success(self.request, 'Atención ciudadana registrada correctamente.')
        return response


class AttentionUpdateView(
    LoginRequiredMixin,
    FunctionaryRequiredMixin,
    AttentionFormContextMixin,
    UpdateView,
):
    model = Attention
    form_class = AttentionForm
    template_name = 'atenciones/attention_form.html'
    success_url = reverse_lazy('atenciones:attention_list')

    def get_queryset(self):
        return visible_attentions(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Atención ciudadana actualizada correctamente.')
        return response


class AttentionDeleteView(
    LoginRequiredMixin,
    FunctionaryRequiredMixin,
    View,
):
    def get_queryset(self):
        return visible_attentions(self.request.user)

    def get(self, request, pk):
        attention = get_object_or_404(self.get_queryset(), pk=pk)
        return render(
            request,
            'atenciones/attention_confirm_delete.html',
            {'object': attention},
        )

    def post(self, request, pk):
        attention = get_object_or_404(self.get_queryset(), pk=pk)
        attention.deleted_at = timezone.now()
        attention.save(update_fields=['deleted_at', 'updated_at'])
        messages.success(request, 'Atención ciudadana eliminada correctamente.')
        return redirect('atenciones:attention_list')


def visible_attentions(user):
    functionary = user.functionary
    queryset = Attention.objects.select_related(
        'attention_type',
        'sub_attention',
        'delegation',
        'functionary',
        'followup_responsible',
        'organization',
    ).filter(deleted_at__isnull=True)
    if not user.is_staff and not user.is_superuser:
        if functionary.is_admin or functionary.has_global_scope:
            pass
        elif functionary.is_delegate:
            queryset = queryset.filter(delegation=functionary.delegation)
        else:
            queryset = queryset.filter(
                Q(functionary=functionary) | Q(followup_responsible=functionary)
                | Q(commitments__functionary=functionary, commitments__deleted_at__isnull=True)
                | Q(office_letters__responsible=functionary, office_letters__deleted_at__isnull=True)
            ).distinct()
    return queryset


class AttentionDetailView(LoginRequiredMixin, FunctionaryRequiredMixin, View):
    template_name = 'atenciones/attention_detail.html'

    def render_detail(self, request, attention, form=None):
        from correspondence.views import get_office_letter_scope
        followups = attention.followups.select_related('author', 'responsible')
        return render(request, self.template_name, {
            'attention': attention,
            'form': form if form is not None else AttentionFollowUpForm(attention=attention),
            'history_page': Paginator(followups, 15).get_page(request.GET.get('page')),
            'linked_commitments': attention.commitments.filter(deleted_at__isnull=True).select_related('functionary'),
            'linked_letters': get_office_letter_scope(request.user).filter(attention=attention),
        })

    def get(self, request, pk):
        return self.render_detail(request, get_object_or_404(visible_attentions(request.user), pk=pk))

    def post(self, request, pk):
        with transaction.atomic():
            attention = get_object_or_404(
                Attention.objects.select_for_update().filter(pk__in=visible_attentions(request.user).values('pk')), pk=pk,
            )
            form = AttentionFollowUpForm(request.POST, attention=attention)
            valid = form.is_valid()
            if attention.status == Attention.Status.CLOSED:
                form.add_error(None, 'Esta atención ya está cerrada. Su historial se conserva para consulta.')
                valid = False
            elif form.cleaned_data.get('version') != attention.updated_at.isoformat():
                form.add_error(None, 'Otra persona actualizó esta atención. Revisa los datos actuales y el historial de esta página. Conservamos lo que escribiste para que puedas ajustarlo y volver a guardar.')
                form.data = form.data.copy()
                form.data['version'] = attention.updated_at.isoformat()
                valid = False
            if valid:
                data = form.cleaned_data
                for field in ('status', 'followup_responsible', 'next_action', 'next_contact_date', 'closure_outcome', 'closure_details'):
                    setattr(attention, field, data[field])
                attention.closed_at = timezone.now() if attention.status == Attention.Status.CLOSED else None
                attention.full_clean()
                attention.save()
                AttentionFollowUp.objects.create(
                    attention=attention, author=request.user.functionary, note=data['note'],
                    status=attention.status, responsible=attention.followup_responsible,
                    next_action=attention.next_action, next_contact_date=attention.next_contact_date,
                    closure_outcome=attention.closure_outcome, closure_details=attention.closure_details,
                )
                messages.success(request, 'Atención cerrada y resultado guardado.' if attention.status == Attention.Status.CLOSED else 'Seguimiento guardado. La próxima acción quedó registrada.')
                return redirect('atenciones:attention_detail', pk=pk)
        return self.render_detail(request, attention, form)


class AttentionCommitmentCreateView(LoginRequiredMixin, FunctionaryRequiredMixin, View):
    template_name = 'atenciones/attention_commitment_form.html'

    def get_attention(self, request, pk, lock=False):
        queryset = visible_attentions(request.user)
        if lock:
            queryset = Attention.objects.select_for_update().filter(pk__in=queryset.values('pk'))
        return get_object_or_404(queryset, pk=pk)

    def make_form(self, attention, data=None):
        responsible = attention.followup_responsible or attention.functionary
        return AttentionCommitmentForm(data, delegation=attention.delegation, initial={
            'creation_token': uuid.uuid4(),
            'applic_name': attention.requester_name,
            'functionary': responsible.pk if responsible.is_active and responsible.deleted_at is None else None,
            'observation': attention.description,
        })

    def render_form(self, request, attention, form):
        return render(request, self.template_name, {'attention': attention, 'form': form})

    def get(self, request, pk):
        attention = self.get_attention(request, pk)
        if attention.status == Attention.Status.CLOSED:
            messages.info(request, 'La atención está cerrada. Puedes consultar sus compromisos desde la ficha.')
            return redirect('atenciones:attention_detail', pk=pk)
        return self.render_form(request, attention, self.make_form(attention))

    def post(self, request, pk):
        try:
            with transaction.atomic():
                attention = self.get_attention(request, pk, lock=True)
                form = self.make_form(attention, request.POST)
                valid = form.is_valid()
                token = form.cleaned_data.get('creation_token')
                existing = Commitment.objects.filter(submission_token=token).first() if token else None
                if existing and existing.source_attention_id == attention.pk:
                    messages.info(request, 'Este compromiso ya estaba guardado; no se creó un duplicado.')
                    return redirect('atenciones:attention_detail', pk=pk)
                if existing:
                    form.add_error(None, 'Este formulario ya fue utilizado. Vuelve a abrir Crear compromiso desde la ficha.')
                    valid = False
                if attention.status == Attention.Status.CLOSED:
                    form.add_error(None, 'La atención se cerró mientras completabas el formulario. No se creó el compromiso.')
                    valid = False
                if valid:
                    commitment = form.save(commit=False)
                    commitment.source_attention = attention
                    commitment.submission_token = token
                    commitment.origin = f'Atención ciudadana #{attention.pk}'
                    commitment.support = attention.requester_contact
                    commitment.full_clean()
                    commitment.save()
                    AttentionFollowUp.objects.create(
                        attention=attention, author=request.user.functionary,
                        note=f'Se creó el compromiso #{commitment.pk}: {commitment.observation}\nResponsable: {commitment.functionary.full_name}. Fecha de cumplimiento: {commitment.commitment_date:%d/%m/%Y}.',
                        status=attention.status, responsible=attention.followup_responsible,
                        next_action=attention.next_action, next_contact_date=attention.next_contact_date,
                    )
                    # Invalidate any older follow-up form so a parallel save cannot hide this new history entry.
                    attention.save(update_fields=['updated_at'])
                    messages.success(request, 'Compromiso creado y vinculado. La atención conserva su estado; ciérrala cuando corresponda.')
                    return redirect('atenciones:attention_detail', pk=pk)
        except IntegrityError:
            form.add_error(None, 'No se pudo guardar. Revisa la ficha por si el compromiso ya fue registrado y vuelve a intentarlo.')
        return self.render_form(request, attention, form)


def subattention_options(request, type_id):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Autenticación requerida.'}, status=401)
    if not (request.user.is_staff or request.user.is_superuser or
            _active_functionary(request.user)):
        return JsonResponse({'detail': 'No tienes permiso para consultar el catálogo.'}, status=403)
    options = SubAttention.objects.filter(
        attention_type_id=type_id,
        attention_type__is_active=True,
        is_active=True,
        deleted_at__isnull=True,
    ).values('id', 'name')
    return JsonResponse({'results': list(options)})


def add_list_context(request, context):
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_params.pop('export', None)
    context['query_params'] = query_params.urlencode()
    context['search_query'] = request.GET.get('q', '')
    context.update(list_controls_context(request))
    return context


def list_response(view, context, response_kwargs):
    add_list_context(view.request, context)
    return ListView.render_to_response(view, context, **response_kwargs)
