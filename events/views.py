import hashlib
import logging
import secrets
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import FunctionaryOrStaffRequiredMixin
from personal.models import Delegation

from .forms import (
    CommunityEventForm,
    DelegationPersonForm,
    PublicEventRegistrationForm,
    RegistrationChildFormSetFactory,
)
from .models import (
    CommunityEvent,
    DelegationPerson,
    EventRegistration,
)

logger = logging.getLogger(__name__)
EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=24)


def _is_global_manager(user):
    functionary = getattr(user, 'functionary', None)
    return user.is_staff or user.is_superuser or (
        functionary is not None and functionary.has_global_scope
    )


def _delegation_scope(user):
    delegations = Delegation.objects.filter(
        deleted_at__isnull=True,
        state='ACTIVO',
    )
    if _is_global_manager(user):
        return delegations
    functionary = getattr(user, 'functionary', None)
    if (
        functionary is None
        or functionary.deleted_at is not None
        or not functionary.is_active
    ):
        return delegations.none()
    return delegations.filter(pk=functionary.delegation_id)


def _event_scope(user):
    return CommunityEvent.objects.filter(
        deleted_at__isnull=True,
        delegation__in=_delegation_scope(user),
    ).select_related('delegation')


def _person_scope(user):
    return DelegationPerson.objects.filter(
        deleted_at__isnull=True,
        delegation__in=_delegation_scope(user),
    ).select_related('delegation')


def _registration_scope(user):
    return EventRegistration.objects.filter(
        deleted_at__isnull=True,
        event__in=_event_scope(user),
    ).select_related('event', 'event__delegation', 'guardian_person').prefetch_related(
        'children',
    )


class PublicEventListView(ListView):
    model = CommunityEvent
    template_name = 'events/public_event_list.html'
    context_object_name = 'events'

    def get_queryset(self):
        now = timezone.now()
        return CommunityEvent.objects.filter(
            status=CommunityEvent.Status.PUBLISHED,
            deleted_at__isnull=True,
            delegation__deleted_at__isnull=True,
            delegation__state='ACTIVO',
            starts_at__gt=now,
        ).filter(
            Q(event_type=CommunityEvent.EventType.INFORMATION)
            | Q(registration_deadline__isnull=True)
            | Q(registration_deadline__gte=now)
        ).select_related('delegation')


class PublicEventRegistrationView(View):
    template_name = 'events/public_registration_form.html'

    def get_event(self, pk):
        return get_object_or_404(
            CommunityEvent.objects.select_related('delegation').filter(
                status=CommunityEvent.Status.PUBLISHED,
                deleted_at__isnull=True,
                delegation__deleted_at__isnull=True,
                delegation__state='ACTIVO',
                event_type=CommunityEvent.EventType.REGISTRATION,
            ),
            pk=pk,
        )

    def get(self, request, pk):
        event = self.get_event(pk)
        if not event.is_open_for_registration:
            return render(
                request,
                'events/public_event_closed.html',
                {'event': event},
                status=200,
            )
        registration = EventRegistration(event=event)
        return self._render_form(
            request,
            event,
            PublicEventRegistrationForm(),
            RegistrationChildFormSetFactory(
                instance=registration,
                prefix='children',
            ),
        )

    def post(self, request, pk):
        event = self.get_event(pk)
        if not event.is_open_for_registration:
            return render(
                request,
                'events/public_event_closed.html',
                {'event': event},
                status=200,
            )

        form = PublicEventRegistrationForm(request.POST)
        form_is_valid = form.is_valid()
        registration = (
            form.save(commit=False)
            if form_is_valid
            else EventRegistration(event=event)
        )
        registration.event = event
        formset = RegistrationChildFormSetFactory(
            request.POST,
            instance=registration,
            prefix='children',
        )
        formset_is_valid = formset.is_valid()
        if not form_is_valid or not formset_is_valid:
            return self._render_form(request, event, form, formset)

        token = secrets.token_urlsafe(32)
        registration.status = EventRegistration.Status.PENDING_EMAIL
        registration.email_verification_token_hash = hashlib.sha256(
            token.encode('utf-8')
        ).hexdigest()
        registration.email_verification_sent_at = timezone.now()
        registration.consented_at = timezone.now()
        attendee_count = int(registration.adult_attends) + sum(
            1
            for child_form in formset.forms
            if child_form.cleaned_data
            and not child_form.cleaned_data.get('DELETE', False)
            and child_form.cleaned_data.get('full_name')
        )

        try:
            with transaction.atomic():
                locked_event = CommunityEvent.objects.select_for_update().get(
                    pk=event.pk,
                    deleted_at__isnull=True,
                )
                if not locked_event.is_open_for_registration:
                    return render(
                        request,
                        'events/public_event_closed.html',
                        {'event': locked_event},
                        status=200,
                    )

                existing = EventRegistration.objects.select_for_update().filter(
                    event=locked_event,
                    rut=registration.rut,
                ).first()
                if existing is not None:
                    if (
                        existing.status != EventRegistration.Status.PENDING_EMAIL
                        or existing.email_verified_at is not None
                        or not existing.verification_expired
                    ):
                        return render(
                            request,
                            'events/registration_submitted.html',
                            {'event': event},
                            status=200,
                        )
                    existing.children.all().delete()
                    existing.full_name = registration.full_name
                    existing.email = registration.email
                    existing.phone = registration.phone
                    existing.adult_attends = registration.adult_attends
                    existing.consented_at = registration.consented_at
                    existing.email_verification_token_hash = (
                        registration.email_verification_token_hash
                    )
                    existing.email_verification_sent_at = (
                        registration.email_verification_sent_at
                    )
                    registration = existing

                if locked_event.capacity is not None:
                    reserved = self._reserved_attendees(locked_event)
                    if reserved + attendee_count > locked_event.capacity:
                        form.add_error(
                            None,
                            'No hay suficientes cupos disponibles para esa inscripción.',
                        )
                        return self._render_form(request, event, form, formset)

                registration.event = locked_event
                registration.save()
                formset.instance = registration
                formset.save()

                verification_url = request.build_absolute_uri(
                    reverse('events:verify_email', args=[token])
                )
                send_mail(
                    subject=f'Confirma tu inscripción: {event.title}',
                    message=(
                        f'Hola {registration.full_name},\n\n'
                        'Para verificar tu correo y continuar con la inscripción '
                        'al evento, abre este enlace dentro de las próximas 24 horas:\n'
                        f'{verification_url}\n\n'
                        'Si no solicitaste esta inscripción, puedes ignorar este correo.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[registration.email],
                    fail_silently=False,
                )
        except IntegrityError:
            if not EventRegistration.objects.filter(
                event=event,
                rut=registration.rut,
            ).exists():
                raise
            return render(
                request,
                'events/registration_submitted.html',
                {'event': event},
                status=200,
            )
        except (SMTPException, OSError):
            logger.exception('Could not send an event registration verification email.')
            return render(
                request,
                'events/public_registration_form.html',
                {
                    'event': event,
                    'form': form,
                    'child_formset': formset,
                    'email_error': (
                        'No se pudo enviar el correo de verificación. '
                        'La inscripción no se guardó; inténtalo nuevamente más tarde.'
                    ),
                },
                status=503,
            )

        return render(
            request,
            'events/registration_submitted.html',
            {'event': event},
            status=200,
        )

    @staticmethod
    def _reserved_attendees(event):
        now = timezone.now()
        registrations = event.registrations.filter(
            deleted_at__isnull=True,
        ).filter(
            Q(
                status__in=(
                    EventRegistration.Status.PENDING_REVIEW,
                    EventRegistration.Status.CONFIRMED,
                )
            )
            | Q(
                status=EventRegistration.Status.PENDING_EMAIL,
                email_verification_sent_at__gte=(
                    now - EMAIL_VERIFICATION_TIMEOUT
                ),
            )
        ).annotate(child_count=Count('children'))
        total = 0
        for registration in registrations:
            total += int(registration.adult_attends) + registration.child_count
        return total

    def _render_form(self, request, event, form, child_formset, status=200):
        return render(
            request,
            self.template_name,
            {
                'event': event,
                'form': form,
                'child_formset': child_formset,
            },
            status=status,
        )

class VerifyRegistrationEmailView(View):
    template_name = 'events/verify_email.html'

    def _get_registration(self, token):
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        return EventRegistration.objects.filter(
            email_verification_token_hash=token_hash,
            deleted_at__isnull=True,
        ).select_related('event').first()

    def get(self, request, token):
        registration = self._get_registration(token)
        is_expired = (
            registration is not None
            and registration.email_verified_at is None
            and registration.verification_expired
        )
        return render(
            request,
            self.template_name,
            {
                'registration': registration,
                'token': token,
                'is_expired': is_expired,
            },
            status=200 if registration and not is_expired else 400,
        )

    def post(self, request, token):
        registration = self._get_registration(token)
        if (
            registration is None
            or registration.verification_expired
            and registration.email_verified_at is None
        ):
            return render(
                request,
                self.template_name,
                {
                    'registration': registration,
                    'token': token,
                    'is_expired': True,
                },
                status=400,
            )

        if (
            registration.email_verified_at is None
            and registration.status != EventRegistration.Status.PENDING_EMAIL
        ):
            return render(
                request,
                self.template_name,
                {
                    'registration': registration,
                    'token': token,
                    'is_expired': True,
                },
                status=400,
            )

        if registration.email_verified_at is None:
            now = timezone.now()
            registration.email_verified_at = now
            if registration.children.exists():
                person = DelegationPerson.objects.filter(
                    delegation=registration.event.delegation,
                    rut=registration.rut,
                    is_active=True,
                    deleted_at__isnull=True,
                ).first()
                if person is None:
                    registration.status = (
                        EventRegistration.Status.PENDING_REVIEW
                    )
                else:
                    registration.guardian_person = person
                    registration.status = EventRegistration.Status.CONFIRMED
            else:
                registration.status = EventRegistration.Status.CONFIRMED
            registration.save(update_fields=[
                'email_verified_at',
                'guardian_person',
                'status',
                'updated_at',
            ])

        return render(
            request,
            'events/registration_verified.html',
            {
                'registration': registration,
                'pending_review': (
                    registration.status
                    == EventRegistration.Status.PENDING_REVIEW
                ),
            },
            status=200,
        )


class EventManagementRequiredMixin(
    LoginRequiredMixin,
    FunctionaryOrStaffRequiredMixin,
):
    pass


class EventManagementListView(EventManagementRequiredMixin, ListView):
    model = CommunityEvent
    template_name = 'events/management_event_list.html'
    context_object_name = 'events'

    def get_queryset(self):
        return _event_scope(self.request.user).order_by('-starts_at')


class EventCreateView(EventManagementRequiredMixin, CreateView):
    model = CommunityEvent
    form_class = CommunityEventForm
    template_name = 'events/management_event_form.html'
    success_url = reverse_lazy('events:management_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Evento guardado correctamente.')
        return super().form_valid(form)


class EventUpdateView(EventManagementRequiredMixin, UpdateView):
    model = CommunityEvent
    form_class = CommunityEventForm
    template_name = 'events/management_event_form.html'
    success_url = reverse_lazy('events:management_list')

    def get_queryset(self):
        return _event_scope(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Evento actualizado correctamente.')
        return super().form_valid(form)


class EventCancelView(EventManagementRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(_event_scope(request.user), pk=pk)
        event.status = CommunityEvent.Status.CANCELLED
        event.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Evento cancelado; se conservaron sus registros.')
        return redirect('events:management_list')


class PersonListView(EventManagementRequiredMixin, ListView):
    model = DelegationPerson
    template_name = 'events/management_person_list.html'
    context_object_name = 'people'

    def get_queryset(self):
        return _person_scope(self.request.user).order_by('full_name')


class PersonCreateView(EventManagementRequiredMixin, CreateView):
    model = DelegationPerson
    form_class = DelegationPersonForm
    template_name = 'events/management_person_form.html'
    success_url = reverse_lazy('events:person_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        registration_id = self.request.GET.get('registration', '')
        if registration_id.isdecimal():
            registration = _registration_scope(self.request.user).filter(
                pk=int(registration_id),
                status=EventRegistration.Status.PENDING_REVIEW,
            ).first()
            if registration is not None:
                initial.update({
                    'delegation': registration.event.delegation_id,
                    'full_name': registration.full_name,
                    'rut': registration.rut,
                    'email': registration.email,
                    'phone': registration.phone,
                })
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Persona agregada al padrón.')
        response = super().form_valid(form)
        registration_id = self.request.GET.get('registration', '')
        if registration_id.isdecimal():
            registration = _registration_scope(self.request.user).filter(
                pk=int(registration_id),
                status=EventRegistration.Status.PENDING_REVIEW,
            ).first()
            if registration is not None:
                if (
                    registration.rut == self.object.rut
                    and registration.event.delegation_id
                    == self.object.delegation_id
                    and self.object.is_active
                ):
                    registration.guardian_person = self.object
                    registration.status = EventRegistration.Status.CONFIRMED
                    registration.save(update_fields=[
                        'guardian_person',
                        'status',
                        'updated_at',
                    ])
                    messages.success(
                        self.request,
                        'Se agregó el tutor al padrón y se confirmó la inscripción.',
                    )
                else:
                    messages.warning(
                        self.request,
                        'La persona se agregó al padrón, pero la inscripción sigue '
                        'pendiente porque el tutor no coincide o está inactivo.',
                    )
                return redirect('events:registration_list')
        return response


class PersonUpdateView(EventManagementRequiredMixin, UpdateView):
    model = DelegationPerson
    form_class = DelegationPersonForm
    template_name = 'events/management_person_form.html'
    success_url = reverse_lazy('events:person_list')

    def get_queryset(self):
        return _person_scope(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Persona actualizada correctamente.')
        return super().form_valid(form)


class RegistrationListView(EventManagementRequiredMixin, ListView):
    model = EventRegistration
    template_name = 'events/management_registration_list.html'
    context_object_name = 'registrations'

    def get_queryset(self):
        queryset = _registration_scope(self.request.user).order_by(
            '-created_at',
            '-pk',
        )
        status = self.request.GET.get('status', '').strip()
        if status in EventRegistration.Status.values:
            queryset = queryset.filter(status=status)
        event_id = self.request.GET.get('event', '').strip()
        if event_id.isdecimal():
            queryset = queryset.filter(event_id=int(event_id))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = EventRegistration.Status.choices
        context['selected_status'] = self.request.GET.get('status', '')
        context['events'] = _event_scope(self.request.user).order_by(
            '-starts_at',
        )
        context['selected_event'] = self.request.GET.get('event', '')
        return context


class RegistrationReviewView(EventManagementRequiredMixin, View):
    def post(self, request, pk):
        registration = get_object_or_404(
            _registration_scope(request.user),
            pk=pk,
            status=EventRegistration.Status.PENDING_REVIEW,
        )
        decision = request.POST.get('decision')
        if decision == 'confirm':
            person = DelegationPerson.objects.filter(
                delegation=registration.event.delegation,
                rut=registration.rut,
                deleted_at__isnull=True,
            ).first()
            if person is None:
                messages.error(
                    request,
                    'Agrega primero al tutor al padrón de esa delegación.',
                )
                return redirect(
                    f"{reverse('events:person_create')}?registration={registration.pk}"
                )
            if not person.is_active:
                messages.error(
                    request,
                    'Activa el registro del tutor en el padrón antes de confirmar.',
                )
                return redirect(
                    reverse('events:person_update', args=[person.pk])
                )
            registration.guardian_person = person
            registration.status = EventRegistration.Status.CONFIRMED
            messages.success(request, 'Inscripción confirmada.')
        elif decision == 'reject':
            registration.status = EventRegistration.Status.REJECTED
            messages.success(request, 'Inscripción rechazada.')
        else:
            return HttpResponse(status=400)
        registration.save(update_fields=[
            'guardian_person',
            'status',
            'updated_at',
        ])
        return redirect('events:registration_list')
