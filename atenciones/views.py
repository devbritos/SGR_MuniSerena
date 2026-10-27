from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, UpdateView, View

from core.mixins import AdminRequiredMixin, FunctionaryRequiredMixin
from core.exports import excel_response
from core.lists import search_queryset
from core.mixins import _active_functionary

from .forms import AttentionForm, AttentionTypeForm, SubAttentionForm
from .models import Attention, AttentionType, SubAttention


class AttentionTypeListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = AttentionType
    template_name = 'atenciones/type_list.html'
    context_object_name = 'object_list'
    paginate_by = 20

    def get_queryset(self):
        queryset = AttentionType.objects.filter(deleted_at__isnull=True)
        queryset = search_queryset(
            queryset, self.request.GET.get('q'), 'code', 'name', 'description'
        )
        if self.request.GET.get('export') == 'xlsx':
            return queryset
        return queryset.order_by('name')

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


class SubAttentionListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = SubAttention
    template_name = 'atenciones/subattention_list.html'
    context_object_name = 'object_list'
    paginate_by = 20

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
        if self.request.GET.get('export') == 'xlsx':
            return queryset
        return queryset

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


class AttentionListView(LoginRequiredMixin, FunctionaryRequiredMixin, ListView):
    model = Attention
    template_name = 'atenciones/attention_list.html'
    context_object_name = 'object_list'
    paginate_by = 20

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
        )
        if self.request.GET.get('export') == 'xlsx':
            return queryset
        return queryset

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'atenciones_ciudadanas.xlsx',
                [
                    'Fecha y hora', 'Solicitante', 'Contacto', 'Tipo',
                    'Subatención', 'Descripción', 'Delegación',
                    'Usuario responsable',
                ],
                (
                    [
                        attention.created_at.strftime('%d/%m/%Y %H:%M'),
                        attention.requester_name,
                        attention.requester_contact,
                        attention.attention_type.name,
                        attention.sub_attention.name,
                        attention.description,
                        attention.delegation.name,
                        attention.functionary.full_name,
                    ]
                    for attention in self.get_queryset()
                ),
            )
        return list_response(self, context, response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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

    def form_valid(self, form):
        functionary = self.request.user.functionary
        form.instance.functionary = functionary
        form.instance.delegation = functionary.delegation
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
    ).filter(deleted_at__isnull=True)
    if not user.is_staff and not user.is_superuser:
        if functionary.is_admin or functionary.has_global_scope:
            pass
        elif functionary.is_delegate:
            queryset = queryset.filter(delegation=functionary.delegation)
        else:
            queryset = queryset.filter(functionary=functionary)
    return queryset


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
    return context


def list_response(view, context, response_kwargs):
    add_list_context(view.request, context)
    return ListView.render_to_response(view, context, **response_kwargs)
