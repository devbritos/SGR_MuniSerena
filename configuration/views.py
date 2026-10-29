from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, View
from django.db import transaction
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator

from .models import Goal, Measuring, Period
from .forms import GoalForm, MeasuringForm, PeriodForm
from core.mixins import AdminRequiredMixin
from core.exports import excel_response
from core.lists import search_queryset


def _save_goal_for_positions(form):
    positions = list(form.cleaned_data['positions'])
    goal = form.save(commit=False)
    goal.position = positions[0]
    goal.save()
    for position in positions[1:]:
        Goal.objects.create(
            position=position,
            measuring=goal.measuring,
            period=goal.period,
            weight=goal.weight,
            validity=goal.validity,
            target_value=goal.target_value,
            unity=goal.unity,
        )
    return goal, len(positions)


class GoalListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Goal
    template_name = 'configuration/goal_list.html'
    context_object_name = 'goals'
    paginate_by = None

    def get_queryset(self):
        queryset = Goal.objects.select_related(
            'position', 'measuring', 'period'
        ).filter(deleted_at__isnull=True)
        if not self.request.GET.get('all'):
            queryset = queryset.filter(validity=True)
        period_id = self.request.GET.get('period')
        if period_id and period_id.isdigit():
            queryset = queryset.filter(period_id=period_id)
        queryset = search_queryset(
            queryset,
            self.request.GET.get('q'),
            'position__name',
            'measuring__code',
            'measuring__service',
            'measuring__measurable_item',
            'unity',
        )
        if self.request.GET.get('export') == 'xlsx':
            return queryset
        return queryset.order_by('period', 'position__name', 'measuring__service')

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'metas.xlsx',
                ['Cargo', 'Ítem', 'Meta', 'Unidad', 'Ponderación', 'Período', 'Estado'],
                (
                    [
                        goal.position.name,
                        goal.measuring.service,
                        goal.target_value,
                        goal.unity,
                        goal.weight,
                        str(goal.period),
                        'Activa' if goal.validity else 'Inactiva',
                    ]
                    for goal in self.get_queryset()
                ),
            )
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('export', None)
        context['query_params'] = query_params.urlencode()
        context['search_query'] = self.request.GET.get('q', '')
        context['showing_all'] = bool(self.request.GET.get('all'))
        return super().render_to_response(context, **response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['periods'] = Period.objects.all().order_by('-start_date')
        context['selected_period'] = self.request.GET.get('period', '')

        resumen = {}

        for goal in self.get_queryset():
            key = (goal.position_id, goal.period_id)
            if key not in resumen:
                resumen[key] = {
                    'position': goal.position,
                    'period': goal.period,
                    'total_weight': 0,
                    'items': [],
                }
            resumen[key]['total_weight'] += goal.weight
            resumen[key]['items'].append(goal)

        page = Paginator(list(resumen.values()), 10).get_page(
            self.request.GET.get('page')
        )
        context['resumen'] = page.object_list
        context['page_obj'] = page
        context['paginator'] = page.paginator
        context['is_paginated'] = page.has_other_pages()
        return context


class GoalCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Goal
    form_class = GoalForm
    template_name = 'configuration/goal_form.html'
    success_url = reverse_lazy('configuration:goal_list')

    @transaction.atomic
    def form_valid(self, form):
        goal, position_count = _save_goal_for_positions(form)
        self.object = goal
        messages.success(
            self.request,
            f'Meta registrada para {position_count} cargo(s).',
        )
        return redirect(self.success_url)


class GoalUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Goal
    form_class = GoalForm
    template_name = 'configuration/goal_form.html'
    success_url = reverse_lazy('configuration:goal_list')

    @transaction.atomic
    def form_valid(self, form):
        goal, position_count = _save_goal_for_positions(form)
        self.object = goal
        messages.success(
            self.request,
            f'Meta actualizada para {position_count} cargo(s).',
        )
        return redirect(self.success_url)


class GoalDeactivateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, pk):
        goal = get_object_or_404(Goal, pk=pk)
        return render(request, 'configuration/goal_confirm_delete.html', {
            'object': goal,
        })

    def post(self, request, pk):
        goal = get_object_or_404(Goal, pk=pk)
        goal.validity = False
        goal.save(update_fields=['validity', 'updated_at'])
        messages.success(request, 'Meta desactivada correctamente.')
        return redirect('configuration:goal_list')


class MeasuringListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Measuring
    template_name = 'configuration/measuring_list.html'
    context_object_name = 'items'
    paginate_by = 20

    def get_queryset(self):
        queryset = Measuring.objects.filter(deleted_at__isnull=True)
        if not self.request.GET.get('all'):
            queryset = queryset.filter(validity=True)
        return search_queryset(
            queryset,
            self.request.GET.get('q'),
            'code',
            'service',
            'measurable_item',
        ).order_by('service')

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'xlsx':
            return excel_response(
                'items_y_metas.xlsx',
                ['Código', 'Nombre', 'Descripción', 'Estado'],
                (
                    [
                        item.code or '',
                        item.service,
                        item.measurable_item,
                        'Activo' if item.validity else 'Inactivo',
                    ]
                    for item in self.get_queryset()
                ),
            )
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('export', None)
        context['query_params'] = query_params.urlencode()
        context['search_query'] = self.request.GET.get('q', '')
        context['showing_all'] = bool(self.request.GET.get('all'))
        return super().render_to_response(context, **response_kwargs)


class MeasuringCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Measuring
    form_class = MeasuringForm
    template_name = 'configuration/measuring_form.html'
    success_url = reverse_lazy('configuration:measuring_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Ítem creado correctamente.')
        return response


class MeasuringUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Measuring
    form_class = MeasuringForm
    template_name = 'configuration/measuring_form.html'
    success_url = reverse_lazy('configuration:measuring_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Ítem actualizado correctamente.')
        return response


class MeasuringDeactivateView(LoginRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, pk):
        item = get_object_or_404(Measuring, pk=pk)
        return render(request, 'configuration/measuring_confirm_delete.html', {
            'object': item,
        })

    def post(self, request, pk):
        item = get_object_or_404(Measuring, pk=pk)
        item.validity = False
        item.save(update_fields=['validity', 'updated_at'])
        messages.success(request, 'Ítem desactivado correctamente.')
        return redirect('configuration:measuring_list')

class PeriodCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Period
    form_class = PeriodForm
    template_name = 'configuration/period_form.html'
    success_url = reverse_lazy('configuration:goal_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Período registrado correctamente.')
        return response
