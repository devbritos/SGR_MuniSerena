import re

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.core.paginator import Paginator
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from core.mixins import FunctionaryRequiredMixin
from core.lists import ListControlsMixin, search_queryset
from .models import Organization, OrganizationLeader
from .forms import OrganizationForm, LeaderForm, ExistingAttentionForm, AttentionSearchForm

def can_manage(user):
    from core.role_access import can_access
    if not can_access(user, 'organizations:update'):
        return False
    fn = user.functionary
    return user.is_superuser or fn.is_admin or not fn.has_role('READONLY')

def visible_organizations(user):
    qs = Organization.objects.filter(deleted_at__isnull=True, delegation__deleted_at__isnull=True).select_related('delegation', 'created_by')
    return qs if user.is_staff or user.is_superuser or user.functionary.has_global_scope else qs.filter(delegation=user.functionary.delegation)

class AccessMixin(LoginRequiredMixin, FunctionaryRequiredMixin):
    def get_queryset(self):
        return visible_organizations(self.request.user)
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_manage'] = can_manage(self.request.user)
        return context

class WriteMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        # Authentication and active-profile checks run before accessing the profile.
        if request.user.is_authenticated:
            fn = getattr(request.user, 'functionary', None)
            if fn and fn.is_active and fn.deleted_at is None and not can_manage(request.user):
                raise PermissionDenied('Tu rol permite consultar las organizaciones.')
        return super().dispatch(request, *args, **kwargs)

class OrganizationListView(AccessMixin, ListControlsMixin, ListView):
    model = Organization
    template_name = 'organizations/list.html'
    paginate_by = 20
    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.GET.get('q', '').strip()
        if query:
            search = (
                Q(name__icontains=query)
                | Q(rut__icontains=query)
                | Q(registry_number__icontains=query)
                | Q(territory__icontains=query)
                | Q(organization_type__icontains=query)
            )
            compact_rut = re.sub(r'[.\s-]', '', query).upper()
            if (
                re.fullmatch(r'\d{6,8}[0-9K]', compact_rut)
                and (len(compact_rut) == 9 or '-' in query)
            ):
                normalized_rut = (
                    f'{int(compact_rut[:-1])}-{compact_rut[-1]}'
                )
                search |= Q(rut__iexact=normalized_rut)
            elif re.fullmatch(r'\d{6,8}', compact_rut):
                search |= Q(rut__startswith=f'{int(compact_rut)}-')
            qs = qs.filter(search)
        status = self.request.GET.get('status')
        return qs.filter(status=status) if status in Organization.Status.values else qs
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Organization.Status.choices
        context['selected_status'] = self.request.GET.get('status', '')
        query = self.request.GET.copy()
        query.pop('page', None)
        context['query_params'] = query.urlencode()
        return context

class OrganizationDetailView(AccessMixin, DetailView):
    model = Organization
    template_name = 'organizations/detail.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['leaders'] = self.object.leaders.filter(deleted_at__isnull=True)
        from atenciones.views import visible_attentions
        context['attention_page'] = Paginator(
            visible_attentions(self.request.user).filter(organization=self.object).order_by('-created_at', '-pk'), 10,
        ).get_page(self.request.GET.get('attention_page'))
        context['attentions'] = context['attention_page']
        from events.views import _event_scope
        context['event_page'] = Paginator(
            self.object.event_invitations.filter(event__in=_event_scope(self.request.user)).select_related('event').order_by('-event__starts_at', '-pk'), 10,
        ).get_page(self.request.GET.get('event_page'))
        return context

class OrganizationFormMixin:
    model = Organization
    form_class = OrganizationForm
    template_name = 'organizations/form.html'
    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'user': self.request.user}
    def get_success_url(self):
        return reverse('organizations:detail', args=[self.object.pk])

class OrganizationCreateView(WriteMixin, OrganizationFormMixin, CreateView):
    def form_valid(self, form):
        form.instance.created_by = self.request.user.functionary
        response = super().form_valid(form)
        messages.success(self.request, 'Organización registrada. Ahora puedes agregar sus dirigentes.')
        return response

class OrganizationUpdateView(WriteMixin, OrganizationFormMixin, UpdateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Organización actualizada.')
        return response

class LeaderFormMixin:
    model = OrganizationLeader
    form_class = LeaderForm
    template_name = 'organizations/leader_form.html'
    def get_organization(self):
        return get_object_or_404(visible_organizations(self.request.user), pk=self.kwargs['organization_pk'])
    def get_form_kwargs(self):
        self.organization = self.get_organization()
        return super().get_form_kwargs()
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'organization': self.organization}
    def form_valid(self, form):
        form.instance.organization = self.organization
        response = super().form_valid(form)
        messages.success(self.request, 'Dirigente guardado. Los períodos anteriores se conservan en la ficha.')
        return response
    def get_success_url(self):
        return reverse('organizations:detail', args=[self.organization.pk])

class LeaderCreateView(WriteMixin, LeaderFormMixin, CreateView):
    @transaction.atomic
    def form_valid(self, form):
        # Serialize creations for this organization, including requests from different tabs.
        organization = get_object_or_404(
            Organization.objects.select_for_update().filter(pk__in=visible_organizations(self.request.user).values('pk')),
            pk=self.organization.pk,
        )
        values = {name: form.cleaned_data[name] for name in form.Meta.fields}
        existing = OrganizationLeader.objects.filter(
            organization=organization, deleted_at__isnull=True, **values,
        ).order_by('created_at', 'pk').first()
        if existing:
            messages.info(self.request, 'Este dirigente ya estaba registrado con estos datos. No se creó un duplicado.')
            return redirect(self.get_success_url())
        return super().form_valid(form)

class LeaderUpdateView(WriteMixin, LeaderFormMixin, UpdateView):
    def get_queryset(self):
        return OrganizationLeader.objects.filter(organization__in=visible_organizations(self.request.user), organization_id=self.kwargs['organization_pk'], deleted_at__isnull=True)


class OrganizationAttentionLinkView(WriteMixin, View):
    template_name = 'organizations/attention_link.html'

    def get_organization(self, pk, lock=False):
        queryset = visible_organizations(self.request.user)
        if lock:
            queryset = Organization.objects.select_for_update().filter(pk__in=queryset.values('pk'))
        return get_object_or_404(queryset, pk=pk)

    def eligible_attentions(self, organization):
        from atenciones.views import visible_attentions
        return visible_attentions(self.request.user).filter(delegation_id=organization.delegation_id)

    def render_form(self, organization, form):
        candidates = self.eligible_attentions(organization).filter(organization__isnull=True)
        query = self.request.GET.get('q', '').strip()
        candidates = search_queryset(candidates, query, 'requester_name', 'requester_contact', 'description')
        if query.isdecimal():
            candidates = self.eligible_attentions(organization).filter(organization__isnull=True, pk=int(query))
        search_form = AttentionSearchForm(self.request.GET)
        if search_form.is_valid():
            for name, lookup in [('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte')]:
                if search_form.cleaned_data[name]:
                    candidates = candidates.filter(**{lookup: search_form.cleaned_data[name]})
        else:
            candidates = candidates.none()
        selected = self.request.POST.get('attention', '')
        params = self.request.GET.copy()
        params.pop('page', None)
        return render(self.request, self.template_name, {
            'organization': organization, 'form': form, 'search_query': query,
            'search_form': search_form,
            'page_obj': Paginator(candidates.order_by('-created_at', '-pk'), 10).get_page(self.request.GET.get('page')),
            'query_params': params.urlencode(),
            'selected_attention': int(selected) if selected.isdecimal() else None,
        })

    def get(self, request, pk):
        organization = self.get_organization(pk)
        return self.render_form(organization, ExistingAttentionForm(queryset=self.eligible_attentions(organization)))

    def post(self, request, pk):
        from atenciones.models import Attention, AttentionFollowUp
        with transaction.atomic():
            organization = self.get_organization(pk, lock=True)
            eligible = self.eligible_attentions(organization)
            form = ExistingAttentionForm(request.POST, queryset=eligible)
            if form.is_valid():
                attention = get_object_or_404(
                    Attention.objects.select_for_update().filter(pk__in=eligible.values('pk')),
                    pk=form.cleaned_data['attention'].pk,
                )
                if attention.organization_id == organization.pk:
                    messages.info(request, 'La atención ya estaba vinculada. No se duplicó el registro.')
                    return redirect('organizations:detail', pk=organization.pk)
                if attention.organization_id:
                    form.add_error('attention', 'Esta atención ya está vinculada a otra organización. No se modificó el vínculo.')
                else:
                    attention.organization = organization
                    attention.full_clean()
                    attention.save(update_fields=['organization', 'updated_at'])
                    AttentionFollowUp.objects.create(
                        attention=attention, author=request.user.functionary,
                        note=f'Se vinculó la atención a la organización #{organization.pk}: {organization.name}.',
                        status=attention.status, responsible=attention.followup_responsible,
                        next_action=attention.next_action, next_contact_date=attention.next_contact_date,
                        closure_outcome=attention.closure_outcome, closure_details=attention.closure_details,
                    )
                    messages.success(request, 'Atención vinculada. Su estado y sus compromisos se mantienen.')
                    return redirect('organizations:detail', pk=organization.pk)
        return self.render_form(organization, form)
