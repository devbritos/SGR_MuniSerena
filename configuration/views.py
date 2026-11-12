import uuid

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, UpdateView, View
from django.db import transaction
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.utils import timezone

from .models import Goal, Measuring, Period
from .forms import GoalForm, MeasuringForm, PeriodForm
from core.mixins import AdminRequiredMixin
from core.exports import excel_response
from core.lists import (
    ListControlsMixin,
    apply_list_sort,
    get_page_size,
    search_queryset,
)


def _save_goal_for_positions(form):
    positions = list(form.cleaned_data['positions'])
    goal = form.save(commit=False)
    if goal.pk:
        existing_goals = (
            Goal.objects.filter(group_id=goal.group_id)
            if goal.group_id
            else Goal.objects.filter(pk=goal.pk)
        )
    else:
        existing_goals = Goal.objects.none()

    goals_by_position = {
        grouped_goal.position_id: grouped_goal
        for grouped_goal in existing_goals
    }
    group_id = goal.group_id or uuid.uuid4()
    updated_goals = []

    for position in positions:
        grouped_goal = goals_by_position.pop(position.pk, None)
        if grouped_goal is None:
            grouped_goal = Goal.objects.filter(
                position=position,
                measuring=goal.measuring,
                period=goal.period,
                deleted_at__isnull=False,
            ).first() or Goal()
        grouped_goal.position = position
        grouped_goal.measuring = goal.measuring
        grouped_goal.period = goal.period
        grouped_goal.weight = goal.weight
        grouped_goal.validity = goal.validity
        grouped_goal.target_value = goal.target_value
        grouped_goal.unity = goal.unity
        grouped_goal.deleted_at = None
        grouped_goal.group_id = group_id
        grouped_goal.save()
        updated_goals.append(grouped_goal)

    for removed_goal in goals_by_position.values():
        removed_goal.validity = False
        removed_goal.group_id = None
        removed_goal.deleted_at = timezone.now()
        removed_goal.save(
            update_fields=['validity', 'group_id', 'deleted_at', 'updated_at']
        )

    return updated_goals[0], len(positions)


class GoalListView(ListControlsMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Goal
    template_name = 'configuration/goal_list.html'
    context_object_name = 'goals'
    paginate_by = None
    sort_fields = {
        'recent': ('-period__start_date', '-pk'),
        'oldest': ('period__start_date', 'pk'),
        'az': ('measuring__service', 'period__start_date', 'pk'),
        'za': ('-measuring__service', '-period__start_date', '-pk'),
    }

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
        queryset = queryset.order_by('period', 'position__name', 'measuring__service')
        return apply_list_sort(queryset, self.request, self.sort_fields)

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

        goals = list(self.get_queryset())
        group_ids = {goal.group_id for goal in goals if goal.group_id}
        if group_ids:
            grouped_goals = Goal.objects.select_related(
                'position', 'measuring', 'period'
            ).filter(
                group_id__in=group_ids,
                deleted_at__isnull=True,
            )
            if not self.request.GET.get('all'):
                grouped_goals = grouped_goals.filter(validity=True)
            period_id = self.request.GET.get('period')
            if period_id and period_id.isdigit():
                grouped_goals = grouped_goals.filter(period_id=period_id)
            goals_by_id = {goal.pk: goal for goal in goals}
            for goal in grouped_goals:
                goals_by_id.setdefault(goal.pk, goal)
            goals = list(goals_by_id.values())

        position_ids = {goal.position_id for goal in goals}
        period_ids = {goal.period_id for goal in goals}
        period_goals = Goal.objects.filter(
            position_id__in=position_ids,
            period_id__in=period_ids,
            deleted_at__isnull=True,
        )
        if not self.request.GET.get('all'):
            period_goals = period_goals.filter(validity=True)
        group_totals = {}
        for position_id, period_id, weight in period_goals.values_list(
            'position_id', 'period_id', 'weight'
        ):
            key = (position_id, period_id)
            group_totals[key] = group_totals.get(key, 0) + weight

        cards_by_group = {}
        for goal in goals:
            key = ('group', goal.group_id) if goal.group_id else ('goal', goal.pk)
            card = cards_by_group.setdefault(
                key,
                {
                    'goal': goal,
                    'measuring': goal.measuring,
                    'period': goal.period,
                    'target_value': goal.target_value,
                    'unity': goal.unity,
                    'weight': goal.weight,
                    'validity': goal.validity,
                    'positions_by_id': {},
                },
            )
            card['positions_by_id'][goal.position_id] = goal.position

        cards = []
        for card in cards_by_group.values():
            card['positions'] = [
                {
                    'position': position,
                    'total_weight': group_totals.get(
                        (position.pk, card['period'].pk),
                        0,
                    ),
                }
                for position in sorted(
                    card.pop('positions_by_id').values(),
                    key=lambda position: position.name.casefold(),
                )
            ]
            cards.append(card)

        page = Paginator(
            cards,
            get_page_size(self.request, default=20),
        ).get_page(
            self.request.GET.get('page')
        )

        context['resumen'] = page.object_list
        context['goals'] = page.object_list
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
        related_goals = (
            Goal.objects.filter(group_id=goal.group_id)
            if goal.group_id
            else Goal.objects.filter(pk=goal.pk)
        )
        related_goals.update(validity=False, updated_at=timezone.now())
        messages.success(request, 'Meta desactivada para todos los cargos vinculados.')
        return redirect('configuration:goal_list')


class MeasuringListView(ListControlsMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Measuring
    template_name = 'configuration/measuring_list.html'
    context_object_name = 'items'
    paginate_by = 20
    sort_fields = {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('service', 'pk'),
        'za': ('-service', '-pk'),
    }

    def get_queryset(self):
        queryset = Measuring.objects.filter(deleted_at__isnull=True)
        if not self.request.GET.get('all'):
            queryset = queryset.filter(validity=True)
        queryset = search_queryset(
            queryset,
            self.request.GET.get('q'),
            'code',
            'service',
            'measurable_item',
        ).order_by('service')
        return apply_list_sort(queryset, self.request, self.sort_fields)

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
        if self.request.GET.get('modal') == '1':
            return JsonResponse(
                {
                    'id': self.object.pk,
                    'label': str(self.object),
                },
                status=201,
            )
        messages.success(self.request, 'Ítem creado correctamente.')
        return response

    def form_invalid(self, form):
        if self.request.GET.get('modal') == '1':
            return JsonResponse(
                {'errors': form.errors.get_json_data()},
                status=400,
            )
        return super().form_invalid(form)


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
