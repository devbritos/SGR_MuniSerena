from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.views import View

from core.lists import search_queryset
from organizations.models import Organization
from .models import CommunityEvent, EventOrganization
from .views import EventManagementRequiredMixin, _event_scope


def can_manage_invitations(user):
    from core.role_access import can_access
    if not can_access(user, 'events:organization_invitations', 'POST'):
        return False
    fn = getattr(user, 'functionary', None)
    return user.is_superuser or user.is_staff or (fn and (fn.is_admin or not fn.has_role('READONLY')))


class InviteOrganizationsForm(forms.Form):
    organizations = forms.ModelMultipleChoiceField(queryset=Organization.objects.none(), label='Organizaciones')

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organizations'].queryset = Organization.objects.filter(
            delegation_id=event.delegation_id, deleted_at__isnull=True,
            status__in=[Organization.Status.ACTIVE, Organization.Status.FORMING],
        )


class ParticipationForm(forms.ModelForm):
    class Meta:
        model = EventOrganization
        fields = ['status', 'observations']
        widgets = {'status': forms.Select(attrs={'class': 'form-select'}),
                   'observations': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})}


class EventOrganizationsView(EventManagementRequiredMixin, View):
    def render_page(self, request, event, form=None):
        partial = request.headers.get('X-Organization-Search') == '1'
        if partial and (not can_manage_invitations(request.user) or event.status == CommunityEvent.Status.CANCELLED):
            raise PermissionDenied
        candidates = InviteOrganizationsForm(event=event).fields['organizations'].queryset.exclude(
            event_invitations__event=event,
        )
        candidates = search_queryset(candidates, request.GET.get('q'), 'name', 'rut', 'territory')
        params = request.GET.copy()
        params.pop('candidate_page', None)
        return render(request, 'events/_organization_candidates.html' if partial else 'events/organization_invitations.html', {
            'event': event, 'form': form,
            'invitations': None if partial else Paginator(event.organization_invitations.select_related('organization', 'updated_by').order_by('organization__name', 'pk'), 10).get_page(request.GET.get('page')),
            'candidates': Paginator(candidates.order_by('name', 'pk'), 20).get_page(request.GET.get('candidate_page')),
            'can_manage': can_manage_invitations(request.user) and event.status != CommunityEvent.Status.CANCELLED,
            'query_params': params.urlencode(), 'search_query': request.GET.get('q', ''),
            'selected_organizations': request.POST.getlist('organizations'),
            'can_open_organization': bool(getattr(request.user, 'functionary', None)),
        })

    def get(self, request, pk):
        return self.render_page(request, get_object_or_404(_event_scope(request.user), pk=pk))

    def post(self, request, pk):
        if not can_manage_invitations(request.user):
            raise PermissionDenied
        with transaction.atomic():
            event = get_object_or_404(CommunityEvent.objects.select_for_update().filter(pk__in=_event_scope(request.user).values('pk')), pk=pk)
            if event.status == CommunityEvent.Status.CANCELLED:
                raise PermissionDenied('El evento está cancelado; sus convocatorias quedan disponibles para consulta.')
            form = InviteOrganizationsForm(request.POST, event=event)
            if form.is_valid():
                created = 0
                for organization in form.cleaned_data['organizations']:
                    _, added = EventOrganization.objects.get_or_create(
                        event=event, organization=organization,
                        defaults={'invited_by': request.user, 'updated_by': request.user},
                    )
                    created += int(added)
                messages.success(request, f'Convocatorias nuevas: {created}. Las existentes se conservaron sin duplicarse.')
                return redirect('events:organization_invitations', pk=pk)
        return self.render_page(request, event, form)


class ParticipationUpdateView(EventManagementRequiredMixin, View):
    def get_invitation(self, request, pk, invitation_pk, lock=False):
        event = get_object_or_404(_event_scope(request.user), pk=pk)
        queryset = EventOrganization.objects.filter(event=event)
        if lock:
            queryset = queryset.select_for_update()
        return get_object_or_404(queryset, pk=invitation_pk)

    def check_write(self, request, invitation):
        if not can_manage_invitations(request.user) or invitation.event.status == CommunityEvent.Status.CANCELLED:
            raise PermissionDenied

    def get(self, request, pk, invitation_pk):
        invitation = self.get_invitation(request, pk, invitation_pk)
        self.check_write(request, invitation)
        return render(request, 'events/organization_participation_form.html', {'invitation': invitation, 'form': ParticipationForm(instance=invitation)})

    def post(self, request, pk, invitation_pk):
        with transaction.atomic():
            # Lock the event first, consistently with invitation creation and cancellation.
            get_object_or_404(CommunityEvent.objects.select_for_update().filter(pk__in=_event_scope(request.user).values('pk')), pk=pk)
            invitation = self.get_invitation(request, pk, invitation_pk, lock=True)
            self.check_write(request, invitation)
            form = ParticipationForm(request.POST, instance=invitation)
            if form.is_valid():
                form.instance.updated_by = request.user
                form.save()
                messages.success(request, 'Participación actualizada.')
                return redirect('events:organization_invitations', pk=pk)
        return render(request, 'events/organization_participation_form.html', {'invitation': invitation, 'form': form})
