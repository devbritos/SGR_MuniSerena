from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from correspondence.models import OfficeLetter
from personal.models import Functionary, Role
from .community_access import MEMBER_ROLE, PORTAL_GROUP, require_member
from .community_forms import BoardForm, CommunityLetterForm, MemberForm, MemberProfileForm
from .models import NeighborhoodMember, Organization, OrganizationLeader


def portal_render(request, template, member, **context):
    return render(request, f'community/{template}.html', {'member': member, 'organization': member.organization, **context})


def own_letters(member):
    return OfficeLetter.objects.filter(organization=member.organization, deleted_at__isnull=True).order_by('-created_at', '-pk')


def sync_profile(member):
    if member.user_id:
        User.objects.filter(pk=member.user_id).update(first_name=member.names[:150], last_name=member.lastnames, email=member.email)
    OrganizationLeader.objects.filter(member=member, deleted_at__isnull=True).update(name=member.full_name[:150], phone=member.phone, email=member.email)


@login_required
def home(request):
    member = require_member(request.user)
    letters = own_letters(member)
    leaders = {leader.board_position: leader for leader in member.organization.leaders.filter(
        board_position__isnull=False, is_active=True, deleted_at__isnull=True,
        member__is_active=True, member__deleted_at__isnull=True,
    ).filter(Q(starts_on__isnull=True) | Q(starts_on__lte=timezone.localdate())).filter(
        Q(ends_on__isnull=True) | Q(ends_on__gte=timezone.localdate()),
    ).select_related('member')}
    return portal_render(request, 'home', member, recent_letters=letters[:5], letter_count=letters.count(),
                         board=[{'title': title, 'leader': leaders.get(code)} for code, title in OrganizationLeader.BoardPosition.choices])


@login_required
def letters(request):
    member = require_member(request.user)
    return portal_render(request, 'letters', member, page_obj=Paginator(own_letters(member), 15).get_page(request.GET.get('page')))


@login_required
def letter_detail(request, pk):
    member = require_member(request.user)
    letter = get_object_or_404(own_letters(member), pk=pk)
    return portal_render(request, 'letter_detail', member, letter=letter)


def municipal_responsible(organization):
    author = organization.created_by
    if author.is_active and not author.deleted_at and author.delegation_id == organization.delegation_id:
        return author
    people = list(Functionary.objects.filter(delegation=organization.delegation, is_active=True, deleted_at__isnull=True).order_by('pk'))
    return next((person for person in people if person.is_delegate or person.is_admin), people[0] if people else None)


@login_required
def letter_create(request):
    member = require_member(request.user)
    if not member.can_send_letters:
        raise PermissionDenied('Solo presidente, secretario o tesorero en funciones pueden enviar cartas.')
    form = CommunityLetterForm(request.POST or None, initial={'contact_phone': member.phone or member.organization.phone})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=member.organization_id)
            # Releer el cargo bajo el mismo bloqueo que usa la asignación de directiva.
            current = NeighborhoodMember.objects.select_related('organization__delegation', 'role', 'leadership').get(pk=member.pk)
            if not current.can_send_letters:
                raise PermissionDenied('Tu cargo cambió. Ya no tienes permiso para enviar cartas.')
            token = form.cleaned_data['submission_token']
            existing = OfficeLetter.objects.filter(submission_token=token).first()
            if existing:
                if existing.organization_id != member.organization_id or existing.submitted_by_id != request.user.pk:
                    raise PermissionDenied
                return redirect('community:letter_detail', pk=existing.pk)
            responsible = municipal_responsible(member.organization)
            if responsible is None:
                form.add_error(None, 'La delegación aún no tiene un responsable habilitado para recibir cartas. Contacta a la municipalidad.')
            else:
                letter = OfficeLetter.objects.create(
                    organization=member.organization, submitted_by=request.user, submission_token=token,
                    delegation=member.organization.delegation, received_at=timezone.localdate(),
                    recipient=member.organization.delegation.name, sender=member.organization.name,
                    subject=form.cleaned_data['subject'], contact_phone=form.cleaned_data['contact_phone'],
                    activity_date=form.cleaned_data['activity_date'], responsible=responsible,
                    state=OfficeLetter.State.IN_PROGRESS,
                )
                messages.success(request, 'Carta enviada. Puedes consultar su estado desde aquí.')
                return redirect('community:letter_detail', pk=letter.pk)
    return portal_render(request, 'form', member, form=form, title='Enviar carta',
                         description=f'Se enviará en nombre de {member.organization.name} a {member.organization.delegation.name}.', action='Enviar carta', back='community:letters')


@login_required
def members(request):
    member = require_member(request.user)
    neighbors = member.organization.neighbors.filter(deleted_at__isnull=True).select_related('role', 'user', 'leadership')
    if not member.is_manager:
        neighbors = neighbors.filter(is_active=True)
    return portal_render(request, 'members', member, page_obj=Paginator(neighbors, 20).get_page(request.GET.get('page')))


@login_required
def profile(request):
    member = require_member(request.user)
    form = MemberProfileForm(request.POST or None, instance=member)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=member.organization_id)
            member = NeighborhoodMember.objects.select_related('organization__delegation', 'role', 'leadership').get(pk=member.pk)
            if not member.portal_active:
                raise PermissionDenied
            for field in ('names', 'lastnames', 'email', 'phone'):
                setattr(member, field, form.cleaned_data[field])
            member.save(update_fields=['names', 'lastnames', 'email', 'phone', 'updated_at'])
            sync_profile(member)
        messages.success(request, 'Tu perfil fue actualizado. Tus permisos y cargo se conservan.')
        return redirect('community:profile')
    return portal_render(request, 'form', member, form=form, title='Mi perfil',
                         description='Actualiza tus datos de contacto. El administrador de la junta asigna los cargos de la directiva.', action='Guardar perfil', back='community:home')


@login_required
def member_form(request, pk=None):
    actor = require_member(request.user, manage=True)
    instance = get_object_or_404(NeighborhoodMember.objects.filter(organization=actor.organization, deleted_at__isnull=True), pk=pk) if pk else None
    form = MemberForm(request.POST or None, instance=instance, actor=actor)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                Organization.objects.select_for_update().get(pk=actor.organization_id)
                if not pk:
                    existing = NeighborhoodMember.objects.filter(organization=actor.organization, submission_token=form.cleaned_data['submission_token']).first()
                    if existing:
                        return redirect('community:members')
                neighbor = form.save(commit=False)
                neighbor.organization = actor.organization
                if not pk:
                    neighbor.role = Role.objects.get(role_name=MEMBER_ROLE, is_active=True, deleted_at__isnull=True)
                    neighbor.submission_token = form.cleaned_data['submission_token']
                if form.cleaned_data.get('create_access'):
                    user = User.objects.create_user(username=form.cleaned_data['username'], password=form.cleaned_data['password'],
                        first_name=neighbor.names, last_name=neighbor.lastnames, email=neighbor.email)
                    user.groups.add(Group.objects.get_or_create(name=PORTAL_GROUP)[0])
                    neighbor.user = user
                neighbor.save(update_fields=['names', 'lastnames', 'email', 'phone', 'is_active', 'user', 'updated_at'] if pk else None)
                sync_profile(neighbor)
            messages.success(request, 'Integrante guardado. Puedes asignarle un cargo desde Directiva.')
            return redirect('community:members')
        except IntegrityError:
            form.add_error(None, 'No se guardó el integrante: el usuario o registro ya existe. Revisa los datos e inténtalo nuevamente.')
    return portal_render(request, 'form', actor, form=form, title='Editar integrante' if pk else 'Agregar integrante',
                         description='Registra a un vecino de tu propia junta. El acceso al portal es opcional.', action='Guardar integrante', back='community:members')


@login_required
def board(request):
    actor = require_member(request.user, manage=True)
    form = BoardForm(request.POST or None, organization=actor.organization)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=actor.organization_id)
            active_ids = set(actor.organization.neighbors.filter(is_active=True, deleted_at__isnull=True).values_list('pk', flat=True))
            if any(member and member.pk not in active_ids for member in form.cleaned_data.values()):
                raise PermissionDenied('La lista de integrantes cambió. Vuelve a revisar la asignación.')
            current = {leader.board_position: leader for leader in actor.organization.leaders.filter(board_position__isnull=False)}
            changes = []
            for field, position in BoardForm.POSITIONS.items():
                target = form.cleaned_data[field]
                old = current.get(position)
                if (old and target and old.member_id == target.pk and old.is_active and not old.deleted_at
                        and (not old.starts_on or old.starts_on <= timezone.localdate())
                        and (not old.ends_on or old.ends_on >= timezone.localdate())):
                    continue
                if old:
                    old.board_position = None
                    old.member = None
                    old.is_active = False
                    if not old.ends_on and (not old.starts_on or old.starts_on <= timezone.localdate()):
                        old.ends_on = timezone.localdate()
                    old.save()
                changes.append((position, target))
            for position, target in changes:
                if target:
                    OrganizationLeader.objects.create(organization=actor.organization, member=target, board_position=position,
                        name=target.full_name[:150], position=OrganizationLeader.BoardPosition(position).label,
                        phone=target.phone, email=target.email, starts_on=timezone.localdate())
        messages.success(request, 'Directiva actualizada. Los cargos anteriores se conservan en el historial municipal.')
        return redirect('community:home')
    return portal_render(request, 'form', actor, form=form, title='Asignar directiva',
                         description='Cada cargo corresponde a un vecino distinto de esta junta. Solo estos tres cargos pueden enviar cartas.', action='Guardar directiva', back='community:home')
