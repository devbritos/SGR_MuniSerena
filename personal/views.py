from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.http import QueryDict
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.decorators import require
from core.exports import excel_response
from core.lists import (
    apply_list_sort,
    list_controls_context,
    paginate,
    search_queryset,
)

from .forms import (
    DelegationForm,
    FunctionaryCustomForm,
    FunctionaryRoleForm,
    FunctionaryUpdateForm,
    ProfilePhotoForm,
    PositionForm,
    RoleForm,
)
from .models import (
    Delegation,
    DelegationChatMessage,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
    UserProfile,
)

CRUD_PAGE_SIZES = (5, 15, 30)
CRUD_DEFAULT_PAGE_SIZE = 15
FUNCTIONARY_SORT_OPTIONS = (
    ('recent', 'Más recientes'),
    ('oldest', 'Más antiguos'),
    ('name_az', 'Funcionario: A–Z'),
    ('name_za', 'Funcionario: Z–A'),
    ('delegation_az', 'Delegación: A–Z'),
    ('delegation_za', 'Delegación: Z–A'),
)
DELEGATION_SORT_OPTIONS = (
    ('recent', 'Más recientes'),
    ('oldest', 'Más antiguos'),
    ('code_az', 'Código: A–Z'),
    ('code_za', 'Código: Z–A'),
    ('name_az', 'Nombre: A–Z'),
    ('name_za', 'Nombre: Z–A'),
)


def _global_scope(user):
    functionary = getattr(user, 'functionary', None)
    return user.is_staff or user.is_superuser or (
        functionary is not None and functionary.has_global_scope
    )


def _delegation_scope(queryset, user):
    if _global_scope(user):
        return queryset
    functionary = getattr(user, 'functionary', None)
    if functionary is None:
        return queryset.none()
    return queryset.filter(pk=functionary.delegation_id)


def _functionary_scope(queryset, user):
    if _global_scope(user):
        return queryset

    functionary = getattr(user, 'functionary', None)
    if functionary is None:
        return queryset.none()
    if functionary.is_delegate:
        return queryset.filter(delegation_id=functionary.delegation_id)
    return queryset.filter(pk=functionary.pk)


def _authorized_delegations(user, current=None):
    queryset = _delegation_scope(
        Delegation.objects.filter(deleted_at__isnull=True),
        user,
    )
    if current is None:
        return queryset.filter(state='ACTIVO')
    return queryset.filter(Q(state='ACTIVO') | Q(pk=current.pk))


@login_required
def delegation_chat(request):
    functionary = getattr(request.user, 'functionary', None)
    if (
        functionary is None
        or not functionary.is_active
        or functionary.deleted_at is not None
        or not request.user.is_active
        or functionary.delegation.deleted_at is not None
    ):
        raise PermissionDenied

    messages = list(
        DelegationChatMessage.objects.filter(
            delegation_id=functionary.delegation_id,
            sender__is_active=True,
            sender__deleted_at__isnull=True,
        )
        .select_related('sender')
        .order_by('-created_at', '-pk')[:50]
    )
    messages.reverse()
    participants = (
        Functionary.objects.filter(
            delegation_id=functionary.delegation_id,
            is_active=True,
            deleted_at__isnull=True,
            user__is_active=True,
        )
        .select_related('user')
        .order_by('names', 'lastnames')
    )

    return render(request, 'personal/delegation_chat.html', {
        'chat_messages': messages,
        'participants': participants,
        'current_user_id': request.user.pk,
        'delegation': functionary.delegation,
    })


def _list_state_key(module):
    return f'personal.list_state.{module}'


def _list_filter_values(params):
    navigation_keys = {'page', 'per_page', 'sort', 'export', 'clear'}
    return {
        key: values
        for key, values in params.lists()
        if key not in navigation_keys
    }


def _sanitize_list_params(params, module, sort_options):
    allowed_filters = {
        'delegations': {'q', 'all', 'state', 'field'},
        'functionaries': {
            'q',
            'all',
            'status',
            'delegation',
            'position',
        },
    }[module]
    allowed_keys = allowed_filters | {'page', 'per_page', 'sort'}
    for key in set(params.keys()) - allowed_keys:
        params.pop(key, None)

    if params.get('all') != '1':
        params.pop('all', None)
    if module == 'delegations':
        if params.get('state') not in {'ACTIVO', 'INACTIVO'}:
            params.pop('state', None)
        if params.get('field') not in {'RURAL', 'URBANO'}:
            params.pop('field', None)
    else:
        if params.get('status') not in {'active', 'inactive'}:
            params.pop('status', None)
        for key in ('delegation', 'position'):
            if params.get(key) and not params[key].isdigit():
                params.pop(key, None)

    if params.get('sort') not in dict(sort_options):
        params['sort'] = 'recent'
    try:
        page_size = int(params.get('per_page', ''))
    except (TypeError, ValueError):
        page_size = CRUD_DEFAULT_PAGE_SIZE
    if page_size not in CRUD_PAGE_SIZES:
        page_size = CRUD_DEFAULT_PAGE_SIZE
    params['per_page'] = str(page_size)
    return params


def _restore_list_state(request, module, sort_options):
    state_key = _list_state_key(module)
    stored = _sanitize_list_params(
        QueryDict(request.session.get(state_key, '')).copy(),
        module,
        sort_options,
    )
    if request.GET.get('clear') == '1':
        params = QueryDict('', mutable=True)
        params['sort'] = 'recent'
        params['per_page'] = str(CRUD_DEFAULT_PAGE_SIZE)
    elif request.GET:
        incoming = request.GET.copy()
        incoming.pop('clear', None)
        incoming.pop('export', None)
        if not _list_filter_values(incoming):
            params = stored.copy()
            for key in ('page', 'per_page', 'sort'):
                if key in incoming:
                    params.setlist(key, incoming.getlist(key))
        else:
            params = incoming
            if _list_filter_values(params) != _list_filter_values(stored):
                params['page'] = '1'
    else:
        params = stored.copy()

    params = _sanitize_list_params(params, module, sort_options)
    request.GET = params
    request.session[state_key] = params.urlencode()
    return state_key


def _render_list(
    request,
    template,
    queryset,
    context=None,
    *,
    state_key=None,
    sort_options=None,
):
    page = paginate(
        request,
        queryset,
        per_page=CRUD_DEFAULT_PAGE_SIZE if state_key else 20,
        page_size_options=CRUD_PAGE_SIZES if state_key else None,
    )
    if state_key:
        params = request.GET.copy()
        params['page'] = str(page.number)
        request.GET = params
        request.session[state_key] = params.urlencode()
    data = context or {}
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_params.pop('export', None)
    if 'showing_all' in data:
        toggle_params = query_params.copy()
        if data['showing_all']:
            toggle_params.pop('all', None)
        else:
            toggle_params['all'] = '1'
        data['toggle_all_query'] = toggle_params.urlencode()
    data.update({
        'object_list': page.object_list,
        'page_obj': page,
        'paginator': page.paginator,
        'is_paginated': page.has_other_pages(),
        'query_params': query_params.urlencode(),
        **list_controls_context(
            request,
            default_page_size=CRUD_DEFAULT_PAGE_SIZE if state_key else 20,
            page_size_options=CRUD_PAGE_SIZES if state_key else None,
            sort_options=sort_options,
        ),
    })
    return render(request, template, data)


@login_required
@require_http_methods(['GET', 'POST'])
def profile_update(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    form = ProfilePhotoForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
    )
    if request.method == 'POST' and form.is_valid():
        if form.cleaned_data.get('cropped_image'):
            form.save()
            messages.success(request, 'Foto de perfil actualizada correctamente.')
        else:
            messages.info(request, 'No se realizaron cambios en la foto de perfil.')
        return redirect('personal:profile_update')
    return render(request, 'personal/profile_form.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def profile_photo(request):
    profile = get_object_or_404(UserProfile, user=request.user)
    if not profile.photo:
        raise Http404('Este usuario todavía no tiene foto de perfil.')
    return FileResponse(profile.photo.open('rb'), content_type='image/jpeg')


@require("personal.view_functionary")
def functionary_photo(request, pk):
    functionary = get_object_or_404(
        _functionary_scope(
            Functionary.objects.select_related('user__profile'),
            request.user,
        ),
        pk=pk,
        user__isnull=False,
    )
    profile = getattr(functionary.user, 'profile', None)
    if profile is None or not profile.photo:
        raise Http404('Este funcionario todavía no tiene foto de perfil.')
    return FileResponse(profile.photo.open('rb'), content_type='image/jpeg')


# ---------- Delegation ----------
@require("personal.view_delegation")
def delegation_list(request):
    state_key = _restore_list_state(
        request,
        'delegations',
        DELEGATION_SORT_OPTIONS,
    )
    qs = _delegation_scope(Delegation.objects.all(), request.user)
    if request.GET.get('all') != '1':
        qs = qs.filter(deleted_at__isnull=True)
        if request.GET.get('state') in {'ACTIVO', 'INACTIVO'}:
            qs = qs.filter(state=request.GET['state'])
        else:
            qs = qs.filter(state='ACTIVO')
    elif request.GET.get('state') in {'ACTIVO', 'INACTIVO'}:
        qs = qs.filter(state=request.GET['state'])
    if request.GET.get('field') in {'RURAL', 'URBANO'}:
        qs = qs.filter(field=request.GET['field'])
    qs = search_queryset(
        qs,
        request.GET.get('q'),
        'code',
        'name',
        'address',
        'commune',
    )
    qs = apply_list_sort(qs, request, {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'code_az': ('code', 'pk'),
        'code_za': ('-code', '-pk'),
        'name_az': ('name', 'pk'),
        'name_za': ('-name', '-pk'),
        'az': ('name', 'pk'),
        'za': ('-name', '-pk'),
    })
    if request.GET.get('export') == 'xlsx':
        return excel_response(
            'delegaciones.xlsx',
            ['Código', 'Nombre', 'Dirección', 'Comuna', 'Estado', 'Ámbito'],
            (
                [
                    row.code or '',
                    row.name,
                    row.address,
                    row.commune,
                    row.get_state_display(),
                    row.get_field_display(),
                ]
                for row in qs.filter(deleted_at__isnull=True)
            ),
        )
    return _render_list(
        request,
        "personal/delegation_list.html",
        qs,
        {
            "showing_all": request.GET.get("all") == '1',
            "selected_state": request.GET.get('state', ''),
            "selected_field": request.GET.get('field', ''),
        },
        state_key=state_key,
        sort_options=DELEGATION_SORT_OPTIONS,
    )


@require("personal.view_delegation")
def delegation_detail(request, pk):
    delegation = get_object_or_404(
        _delegation_scope(Delegation.objects.all(), request.user),
        pk=pk,
    )
    return render(request, 'personal/delegation_detail.html', {
        'object': delegation,
    })


@require("personal.add_delegation")
@require_http_methods(['GET', 'POST'])
def delegation_create(request):
    if not _global_scope(request.user):
        raise PermissionDenied
    form = DelegationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        delegation = form.save()
        messages.success(
            request,
            f'La delegación “{delegation.name}” se creó correctamente.',
        )
        return redirect("personal:delegation_list")
    return render(request, "personal/delegation_form.html", {"form": form})


@require("personal.change_delegation")
@require_http_methods(['GET', 'POST'])
def delegation_update(request, pk):
    obj = get_object_or_404(
        _delegation_scope(Delegation.objects.all(), request.user),
        pk=pk,
    )
    form = DelegationForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        delegation = form.save()
        messages.success(
            request,
            f'La delegación “{delegation.name}” se actualizó correctamente.',
        )
        return redirect("personal:delegation_list")
    return render(
        request,
        "personal/delegation_form.html",
        {"form": form, "object": obj},
    )


@require("personal.change_delegation")
@require_http_methods(['GET', 'POST'])
def delegation_delete(request, pk):
    obj = get_object_or_404(
        _delegation_scope(Delegation.objects.all(), request.user),
        pk=pk,
    )
    if request.method == "POST":
        assigned_functionaries = Functionary.objects.filter(
            delegation=obj,
            deleted_at__isnull=True,
        )
        if assigned_functionaries.exists():
            messages.error(
                request,
                'No se puede archivar esta delegación porque aún tiene '
                'funcionarios asociados. Archívalos o asígnalos a otra '
                'delegación y vuelve a intentarlo.',
            )
            return redirect('personal:delegation_list')
        if obj.deleted_at is None:
            obj.state = 'INACTIVO'
            obj.deleted_at = timezone.now()
            obj.save(update_fields=['state', 'deleted_at', 'updated_at'])
            messages.success(
                request,
                f'La delegación “{obj.name}” se archivó correctamente.',
            )
        else:
            messages.info(request, 'La delegación ya estaba archivada.')
        return redirect("personal:delegation_list")
    return render(
        request,
        "personal/delegation_confirm_delete.html",
        {"object": obj},
    )


# ---------- Position ----------
@require("personal.view_position")
def position_list(request):
    qs = Position.objects.all()
    if not request.GET.get("all"):
        qs = qs.filter(validity=True)
    qs = search_queryset(qs, request.GET.get('q'), 'name')
    qs = apply_list_sort(qs, request, {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('name', 'pk'),
        'za': ('-name', '-pk'),
    })
    if request.GET.get('export') == 'xlsx':
        return excel_response(
            'cargos.xlsx',
            ['Cargo', 'Estado', 'Rol por defecto'],
            (
                [row.name, 'Activo' if row.validity else 'Inactivo',
                 str(row.default_role or '')]
                for row in qs
            ),
        )
    return _render_list(request, "personal/position_list.html", qs, {
        "showing_all": bool(request.GET.get("all")),
    })


@require("personal.add_position")
def position_create(request):
    form = PositionForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro creado correctamente.")
        return redirect("personal:position_list")
    return render(request, "personal/position_form.html", {"form": form})


@require("personal.change_position")
def position_update(request, pk):
    obj = get_object_or_404(Position, pk=pk)
    form = PositionForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro actualizado correctamente.")
        return redirect("personal:position_list")
    return render(request, "personal/position_form.html", {"form": form, "object": obj})


@require("personal.change_position")
def position_delete(request, pk):
    """No borra: marca el registro como inactivo."""
    obj = get_object_or_404(Position, pk=pk)
    if request.method == "POST":
        obj.validity = False
        obj.save(update_fields=["validity"])
        messages.success(request, "Registro desactivado.")
        return redirect("personal:position_list")
    return render(request, "personal/position_confirm_delete.html", {"object": obj})

# ---------- Functionary ----------
# ---------- Functionary ----------

@require("personal.view_functionary")
def functionary_list(request):
    state_key = _restore_list_state(
        request,
        'functionaries',
        FUNCTIONARY_SORT_OPTIONS,
    )
    qs = Functionary.objects.select_related(
        "delegation", "position", "user", "user__profile"
    ).prefetch_related('functionaryrole_set__role')
    qs = _functionary_scope(qs, request.user)
    if request.GET.get('all') != '1':
        qs = qs.filter(deleted_at__isnull=True)
        if request.GET.get('status') in {'active', 'inactive'}:
            qs = qs.filter(is_active=request.GET['status'] == 'active')
        else:
            qs = qs.filter(is_active=True)
    elif request.GET.get('status') in {'active', 'inactive'}:
        qs = qs.filter(is_active=request.GET['status'] == 'active')
    qs = search_queryset(
        qs,
        request.GET.get('q'),
        'names',
        'lastnames',
        'user__username',
        'user__email',
        'delegation__name',
        'position__name',
        'functionaryrole__role__role_name',
    ).distinct()
    if delegation := request.GET.get("delegation"):
        if delegation.isdigit():
            qs = qs.filter(delegation_id=delegation)
        else:
            qs = qs.none()
    if position := request.GET.get("position"):
        if position.isdigit():
            qs = qs.filter(position_id=position)
        else:
            qs = qs.none()
    qs = apply_list_sort(qs, request, {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'name_az': ('names', 'lastnames', 'pk'),
        'name_za': ('-names', '-lastnames', '-pk'),
        'delegation_az': ('delegation__name', 'names', 'lastnames', 'pk'),
        'delegation_za': ('-delegation__name', '-names', '-lastnames', '-pk'),
        'az': ('names', 'lastnames', 'pk'),
        'za': ('-names', '-lastnames', '-pk'),
    })
    if request.GET.get('export') == 'xlsx':
        return excel_response(
            'funcionarios.xlsx',
            ['Funcionario', 'Correo', 'Delegación', 'Cargo', 'Roles', 'Estado'],
            (
                [
                    row.full_name,
                    row.user.email if row.user else '',
                    row.delegation.name,
                    row.position.name,
                    ', '.join(
                        assignment.role.get_role_name_display()
                        for assignment in row.active_roles
                    ),
                    'Activo' if row.is_active else 'Inactivo',
                ]
                for row in qs.filter(deleted_at__isnull=True)
            ),
        )
    return _render_list(
        request,
        "personal/functionary_list.html",
        qs,
        {
            "showing_all": request.GET.get("all") == '1',
            "selected_status": request.GET.get('status', ''),
            "delegations": _authorized_delegations(request.user),
            "positions": Position.objects.filter(
                validity=True,
                deleted_at__isnull=True,
            ),
        },
        state_key=state_key,
        sort_options=FUNCTIONARY_SORT_OPTIONS,
    )


@require("personal.view_functionary")
def functionary_detail(request, pk):
    functionary = get_object_or_404(
        _functionary_scope(
            Functionary.objects.select_related(
                'delegation',
                'position',
                'user',
            ).prefetch_related('functionaryrole_set__role'),
            request.user,
        ),
        pk=pk,
    )
    return render(request, 'personal/functionary_detail.html', {
        'object': functionary,
    })


@require("personal.add_functionary")
@require_http_methods(['GET', 'POST'])
def functionary_create(request):
    form = FunctionaryCustomForm(
        request.POST or None,
        authorized_delegations=_authorized_delegations(request.user),
    )
    if request.method == 'POST' and form.is_valid():
        functionary = form.save()
        messages.success(
            request,
            f'El funcionario “{functionary.full_name}” se creó correctamente.',
        )
        return redirect("personal:functionary_list")
    return render(request, "personal/functionary_form.html", {"form": form})


@require("personal.change_functionary")
@require_http_methods(['GET', 'POST'])
def functionary_update(request, pk):
    obj = get_object_or_404(
        _functionary_scope(Functionary.objects.select_related('user'), request.user),
        pk=pk,
    )
    form = FunctionaryUpdateForm(
        request.POST or None,
        instance=obj,
        authorized_delegations=_authorized_delegations(
            request.user,
            current=obj.delegation,
        ),
    )
    if request.method == 'POST' and form.is_valid():
        functionary = form.save()
        messages.success(
            request,
            f'Los datos de “{functionary.full_name}” se actualizaron correctamente.',
        )
        return redirect("personal:functionary_list")
    return render(request, "personal/functionary_form.html", {"form": form, "object": obj})


@require("personal.delete_functionary")
@require_http_methods(['GET', 'POST'])
def functionary_delete(request, pk):
    obj = get_object_or_404(
        _functionary_scope(Functionary.objects.select_related('user'), request.user),
        pk=pk,
    )
    if request.method == "POST":
        if obj.deleted_at is None:
            obj.is_active = False
            obj.deleted_at = timezone.now()
            obj.save(update_fields=["is_active", "deleted_at", "updated_at"])
        if obj.user:
            obj.user.is_active = False
            obj.user.save(update_fields=["is_active"])
        messages.success(
            request,
            f'El funcionario “{obj.full_name}” se archivó y su acceso quedó bloqueado.',
        )
        return redirect("personal:functionary_list")
    return render(request, "personal/functionary_confirm_delete.html", {"object": obj})
# ---------- Role ----------
@require("personal.view_role")
def role_list(request):
    queryset = Role.objects.all()
    if not request.GET.get('all'):
        queryset = queryset.filter(is_active=True, deleted_at__isnull=True)
    queryset = search_queryset(
        queryset,
        request.GET.get('q'),
        'role_name',
        'description',
        'authorized_scope',
    )
    queryset = queryset.order_by('role_name')
    queryset = apply_list_sort(queryset, request, {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('role_name', 'pk'),
        'za': ('-role_name', '-pk'),
    })
    if request.GET.get('export') == 'xlsx':
        return excel_response(
            'roles.xlsx',
            ['Rol', 'Descripción', 'Alcance', 'Estado', 'Permisos'],
            (
                [
                    row.get_role_name_display(),
                    row.description,
                    row.get_authorized_scope_display(),
                    'Activo' if row.is_active else 'Inactivo',
                    ', '.join(
                        row.permissions.values_list('codename', flat=True)
                    ),
                ]
                for row in queryset
            ),
        )
    return _render_list(request, "personal/role_list.html", queryset, {
        'showing_all': bool(request.GET.get('all')),
    })


@require("personal.add_role")
def role_create(request):
    form = RoleForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro creado correctamente.")
        return redirect("personal:role_list")
    return render(request, "personal/role_form.html", {"form": form})


@require("personal.change_role")
def role_update(request, pk):
    obj = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro actualizado correctamente.")
        return redirect("personal:role_list")
    return render(request, "personal/role_form.html", {"form": form, "object": obj})


@require("personal.delete_role")
def role_delete(request, pk):
    obj = get_object_or_404(Role, pk=pk)
    if request.method == "POST":
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, "Rol desactivado correctamente.")
        return redirect("personal:role_list")
    return render(request, "personal/role_confirm_delete.html", {"object": obj})


# ---------- FunctionaryRole (asignar roles a un funcionario) ----------
@require("personal.view_functionaryrole")
def functionary_role_list(request):
    qs = FunctionaryRole.objects.select_related("functionary", "role")
    if functionary := request.GET.get("functionary"):
        if functionary.isdigit():
            qs = qs.filter(functionary_id=functionary)
    qs = search_queryset(
        qs,
        request.GET.get('q'),
        'functionary__names',
        'functionary__lastnames',
        'role__role_name',
    )
    qs = apply_list_sort(qs, request, {
        'recent': ('-created_at', '-pk'),
        'oldest': ('created_at', 'pk'),
        'az': ('functionary__names', 'functionary__lastnames', 'pk'),
        'za': ('-functionary__names', '-functionary__lastnames', '-pk'),
    })
    if request.GET.get('export') == 'xlsx':
        return excel_response(
            'asignaciones_de_roles.xlsx',
            ['Funcionario', 'Delegación', 'Cargo', 'Rol', 'Estado del rol'],
            (
                [
                    assignment.functionary.full_name,
                    assignment.functionary.delegation.name,
                    assignment.functionary.position.name,
                    assignment.role.get_role_name_display(),
                    'Activo' if assignment.role.is_active else 'Inactivo',
                ]
                for assignment in qs
            ),
        )
    return _render_list(request, "personal/functionary_role_list.html", qs, {
        "functionaries": Functionary.objects.filter(is_active=True),
    })


@require('personal.add_functionaryrole')
def functionary_role_create(request):
  initial = {'functionary': request.GET.get('functionary')}
  form = FunctionaryRoleForm(request.POST or None, initial=initial)
  if form.is_valid():
    form.save()
    messages.success(request, 'Rol asignado correctamente.')
    # Redirige de vuelta a la lista de funcionarios
    return redirect('personal:functionary_list')
  return render(request, 'personal/functionary_role_form.html', {'form': form})


@require('personal.delete_functionaryrole')
def functionary_role_delete(request, pk):
  obj = get_object_or_404(FunctionaryRole, pk=pk)
  if request.method == 'POST':
    obj.delete()
    messages.success(request, 'Rol quitado correctamente.')
    # Redirige de vuelta a la lista de funcionarios
    return redirect('personal:functionary_list')
  return render(
      request, 'personal/functionary_role_confirm_delete.html', {'object': obj}
  )