import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView

from .models import Neighbor
from .neighbor_forms import NeighborForm
from .views import AccessMixin, can_manage, visible_organizations


class NeighborListView(AccessMixin, ListView):
    template_name = 'organizations/neighbors.html'
    paginate_by = 20

    def visible_neighbors(self):
        user = self.request.user
        neighbors = Neighbor.objects.filter(deleted_at__isnull=True, delegation__deleted_at__isnull=True)
        if user.is_staff or user.is_superuser or user.functionary.has_global_scope:
            return neighbors
        return neighbors.filter(delegation=user.functionary.delegation)

    def load_organization(self):
        pk = self.request.GET.get('junta')
        self.organization = (
            get_object_or_404(visible_organizations(self.request.user), pk=self.parse_pk(pk)) if pk else None
        )

    def get_queryset(self):
        neighbors = self.visible_neighbors()
        if self.organization:
            neighbors = neighbors.filter(organizations=self.organization, delegation=self.organization.delegation)
        query = self.request.GET.get('q', '').strip()
        if not query:
            return neighbors
        match = Q(name__icontains=query) | Q(rut__icontains=query)
        compact = re.sub(r'[.\s-]', '', query).upper()
        if re.fullmatch(r'\d{6,8}[0-9K]', compact):
            match |= Q(rut=f'{int(compact[:-1])}-{compact[-1]}')
        return neighbors.filter(match)

    def get(self, request, *args, **kwargs):
        self.load_organization()
        action = request.GET.get('action')
        context = {}
        if action in ('create', 'edit', 'delete'):
            self.require_manage()
            context['modal_action'] = action
            if action != 'create':
                context['selected_neighbor'] = self.get_neighbor(request.GET.get('neighbor'))
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(**context))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        for name in ('action', 'neighbor', 'page'):
            params.pop(name, None)
        context.update(organization=self.organization, query=params.urlencode())
        if context['can_manage'] and 'form' not in context and context.get('modal_action') != 'delete':
            context['form'] = self.neighbor_form(context.get('selected_neighbor'))
        return context

    def require_manage(self):
        if not can_manage(self.request.user):
            raise PermissionDenied('Tu rol permite consultar los vecinos.')

    @staticmethod
    def parse_pk(pk):
        if not pk or not re.fullmatch(r'[0-9]{1,18}', pk):
            raise Http404
        return int(pk)

    def get_neighbor(self, pk, *, lock=False):
        neighbors = self.visible_neighbors()
        if lock:
            neighbors = neighbors.select_for_update()
        return get_object_or_404(neighbors, pk=self.parse_pk(pk))

    def neighbor_form(self, instance=None, data=None):
        user = self.request.user
        delegation = user.functionary.delegation
        initial = {}
        if instance:
            delegation = instance.delegation
        elif self.organization:
            delegation = self.organization.delegation
            initial['organizations'] = [self.organization.pk]
        return NeighborForm(
            data, instance=instance, delegation=delegation, initial=initial,
            organizations=visible_organizations(user),
        )

    def post(self, request):
        self.require_manage()
        self.load_organization()
        action = request.POST.get('action')
        if action not in ('create', 'edit', 'delete'):
            return HttpResponseBadRequest()
        destination = request.path
        if self.organization:
            destination += f'?junta={self.organization.pk}'
        with transaction.atomic():
            neighbor = self.get_neighbor(request.POST.get('neighbor'), lock=True) if action != 'create' else None
            if action == 'delete':
                neighbor.delete()
                messages.success(request, 'Vecino eliminado.')
                return redirect(destination)
            form = self.neighbor_form(neighbor, request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                except IntegrityError:
                    duplicate = Neighbor.objects.filter(
                        delegation=form.instance.delegation, rut=form.cleaned_data['rut'],
                    ).exclude(pk=form.instance.pk).exists()
                    if not duplicate:
                        raise
                    form.add_error('rut', 'Ya existe un vecino con este RUT en la delegación.')
                else:
                    messages.success(request, 'Vecino guardado.')
                    return redirect(destination)
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(
            form=form, selected_neighbor=neighbor, modal_action=action,
        ))
