from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from core.mixins import FunctionaryRequiredMixin
from core.lists import search_queryset
from personal.models import Functionary
from .models import Meeting, MeetingAgreement
from .meeting_forms import MeetingForm, AgreementForm, AgreementCommitmentForm


def meeting_scope(user):
    fn = user.functionary
    qs = Meeting.objects.filter(deleted_at__isnull=True, delegation__deleted_at__isnull=True).select_related('delegation', 'created_by')
    if user.is_staff or user.is_superuser or fn.has_global_scope: return qs
    qs = qs.filter(delegation=fn.delegation)
    if fn.is_delegate: return qs
    return qs.filter(Q(created_by=fn) | Q(participants=fn) | Q(agreements__responsible=fn)).distinct()


def can_write(user, meeting=None):
    fn = user.functionary
    if fn.has_role('READONLY') and not (fn.is_admin or user.is_superuser): return False
    return meeting is None or user.is_staff or user.is_superuser or fn.has_global_scope or fn.is_delegate or meeting.created_by_id == fn.pk


class MeetingAccess(LoginRequiredMixin, FunctionaryRequiredMixin, View):
    def meeting(self, pk, lock=False, write=False):
        qs = meeting_scope(self.request.user)
        if lock: qs = Meeting.objects.select_for_update().filter(pk__in=qs.values('pk'))
        meeting = get_object_or_404(qs, pk=pk)
        if write and not can_write(self.request.user, meeting): raise PermissionDenied
        return meeting


class MeetingListView(MeetingAccess):
    def get(self, request):
        qs = search_queryset(meeting_scope(request.user), request.GET.get('q'), 'title', 'location', 'notes')
        status = request.GET.get('status', '')
        if status in Meeting.Status.values: qs = qs.filter(status=status)
        params = request.GET.copy(); params.pop('page', None)
        return render(request, 'agenda/meeting_list.html', {'page_obj': Paginator(qs, 20).get_page(request.GET.get('page')), 'status_choices': Meeting.Status.choices, 'selected_status': status, 'query_params': params.urlencode(), 'can_write': can_write(request.user)})


class MeetingDetailView(MeetingAccess):
    def get(self, request, pk):
        meeting = self.meeting(pk)
        agreements = meeting.agreements.filter(deleted_at__isnull=True).select_related('responsible', 'commitment')
        return render(request, 'agenda/meeting_detail.html', {'meeting': meeting, 'agreements': agreements, 'can_write': can_write(request.user, meeting), 'participants': meeting.participants.all(), 'current_functionary_id': request.user.functionary.pk})


class MeetingFormView(MeetingAccess):
    def get(self, request, pk=None):
        meeting = self.meeting(pk, write=True) if pk else None
        if not can_write(request.user, meeting): raise PermissionDenied
        return render(request, 'agenda/meeting_form.html', {'form': MeetingForm(user=request.user, instance=meeting), 'meeting': meeting})

    def post(self, request, pk=None):
        with transaction.atomic():
            meeting = self.meeting(pk, lock=True, write=True) if pk else None
            if not can_write(request.user, meeting): raise PermissionDenied
            form = MeetingForm(request.POST, user=request.user, instance=meeting)
            if form.is_valid():
                if meeting is None:
                    Functionary.objects.select_for_update().get(pk=request.user.functionary.pk)
                    token = form.cleaned_data['creation_token']
                    existing = Meeting.objects.filter(submission_token=token).first()
                    if existing:
                        if existing.created_by_id == request.user.functionary.pk:
                            return redirect('agenda:meeting_detail', pk=existing.pk)
                        form.add_error(None, 'Este formulario ya fue utilizado. Vuelve a abrir Nueva reunión.')
                    else:
                        meeting = form.save(commit=False)
                        meeting.created_by = request.user.functionary
                        meeting.submission_token = token
                if not form.errors:
                    meeting = form.save(commit=False)
                    meeting.save(); form.save_m2m()
                    messages.success(request, 'Reunión guardada. Puedes registrar sus acuerdos en la ficha.')
                    return redirect('agenda:meeting_detail', pk=meeting.pk)
        return render(request, 'agenda/meeting_form.html', {'form': form, 'meeting': meeting if pk else None})


class AgreementFormView(MeetingAccess):
    def get_agreement(self, meeting, agreement_pk):
        agreement = get_object_or_404(MeetingAgreement, meeting=meeting, pk=agreement_pk, deleted_at__isnull=True) if agreement_pk else None
        if meeting.status == Meeting.Status.CANCELLED or (agreement and agreement.commitment_id):
            raise PermissionDenied('La reunión está cancelada o el acuerdo ya se gestiona desde su compromiso.')
        return agreement

    def get(self, request, pk, agreement_pk=None):
        meeting = self.meeting(pk, write=True)
        agreement = self.get_agreement(meeting, agreement_pk)
        return render(request, 'agenda/agreement_form.html', {'meeting': meeting, 'agreement': agreement, 'form': AgreementForm(instance=agreement, meeting=meeting)})

    def post(self, request, pk, agreement_pk=None):
        with transaction.atomic():
            meeting = self.meeting(pk, lock=True, write=True)
            agreement = self.get_agreement(meeting, agreement_pk)
            form = AgreementForm(request.POST, instance=agreement, meeting=meeting)
            if form.is_valid():
                values = form.cleaned_data
                duplicate = meeting.agreements.filter(deleted_at__isnull=True, **values).first() if not agreement else None
                if not duplicate:
                    agreement = form.save(commit=False); agreement.meeting = meeting; agreement.full_clean(); agreement.save()
                messages.success(request, 'Acuerdo guardado sin duplicados.')
                return redirect('agenda:meeting_detail', pk=pk)
        return render(request, 'agenda/agreement_form.html', {'meeting': meeting, 'agreement': agreement, 'form': form})


class AgreementConvertView(MeetingAccess):
    def form(self, meeting, agreement, data=None):
        return AgreementCommitmentForm(data, delegation=meeting.delegation, initial={
            'applic_name': f'Reunión #{meeting.pk}', 'functionary': agreement.responsible_id,
            'commitment_date': agreement.due_date, 'observation': agreement.description,
        })

    def get(self, request, pk, agreement_pk):
        meeting = self.meeting(pk, write=True)
        agreement = get_object_or_404(MeetingAgreement, meeting=meeting, pk=agreement_pk, deleted_at__isnull=True)
        if agreement.commitment_id: return redirect('agenda:meeting_detail', pk=pk)
        if meeting.status == Meeting.Status.CANCELLED: raise PermissionDenied
        return render(request, 'agenda/agreement_convert.html', {'meeting': meeting, 'agreement': agreement, 'form': self.form(meeting, agreement)})

    def post(self, request, pk, agreement_pk):
        with transaction.atomic():
            meeting = self.meeting(pk, lock=True, write=True)
            agreement = get_object_or_404(MeetingAgreement.objects.select_for_update(), meeting=meeting, pk=agreement_pk, deleted_at__isnull=True)
            if agreement.commitment_id: return redirect('agenda:meeting_detail', pk=pk)
            if meeting.status == Meeting.Status.CANCELLED: raise PermissionDenied
            form = self.form(meeting, agreement, request.POST)
            if form.is_valid():
                commitment = form.save(commit=False)
                commitment.origin = f'Reunión #{meeting.pk}'
                commitment.full_clean(); commitment.save()
                agreement.commitment = commitment
                agreement.save(update_fields=['commitment', 'updated_at'])
                messages.success(request, 'Compromiso creado y vinculado. El acuerdo original se conserva.')
                return redirect('agenda:meeting_detail', pk=pk)
        return render(request, 'agenda/agreement_convert.html', {'meeting': meeting, 'agreement': agreement, 'form': form})
