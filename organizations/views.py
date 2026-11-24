from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from core.mixins import FunctionaryRequiredMixin
from core.lists import ListControlsMixin, search_queryset
from .models import Organization, OrganizationLeader
from .forms import OrganizationForm, LeaderForm

def can_manage(user):
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
        qs = search_queryset(super().get_queryset(), self.request.GET.get('q'), 'name', 'rut', 'registry_number', 'territory', 'organization_type')
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
        context['attentions'] = self.object.attentions.filter(deleted_at__isnull=True).select_related(
            'attention_type', 'sub_attention', 'functionary'
        ).order_by('-created_at')[:10]
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
    pass

class LeaderUpdateView(WriteMixin, LeaderFormMixin, UpdateView):
    def get_queryset(self):
        return OrganizationLeader.objects.filter(organization__in=visible_organizations(self.request.user), organization_id=self.kwargs['organization_pk'], deleted_at__isnull=True)
