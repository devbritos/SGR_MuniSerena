from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import require
from core.exports import excel_response
from core.lists import paginate, search_queryset

from .forms import (
    DelegationForm,
    FunctionaryCustomForm,
    FunctionaryRoleForm,
    FunctionaryUpdateForm,
    PositionForm,
    RoleForm,
)
from .models import Delegation, Functionary, FunctionaryRole, Position, Role


def _global_scope(user):
    functionary = getattr(user, 'functionary', None)
    return user.is_staff or user.is_superuser or (
        functionary is not None and functionary.has_global_scope
    )


def _render_list(request, template, queryset, context=None):
    page = paginate(request, queryset)
    data = context or {}
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_params.pop('export', None)
    data.update({
        'object_list': page.object_list,
        'page_obj': page,
        'paginator': page.paginator,
        'is_paginated': page.has_other_pages(),
        'search_query': request.GET.get('q', ''),
        'query_params': query_params.urlencode(),
    })
    return render(request, template, data)


# ---------- Delegation ----------
@require("personal.view_delegation")
def delegation_list(request):
    qs = Delegation.objects.all()
    if not request.GET.get("all"):
        qs = qs.filter(state='ACTIVO', deleted_at__isnull=True)
    functionary = getattr(request.user, 'functionary', None)
    if functionary is not None and not _global_scope(request.user):
        qs = qs.filter(pk=functionary.delegation_id)
    qs = search_queryset(
        qs,
        request.GET.get('q'),
        'code',
        'name',
        'address',
        'commune',
    )
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
                for row in qs.order_by('name')
            ),
        )
    return _render_list(request, "personal/delegation_list.html", qs, {
        "showing_all": bool(request.GET.get("all")),
    })


@require("personal.add_delegation")
def delegation_create(request):
    form = DelegationForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro creado correctamente.")
        return redirect("personal:delegation_list")
    return render(request, "personal/delegation_form.html", {"form": form})


@require("personal.change_delegation")
def delegation_update(request, pk):
    obj = get_object_or_404(Delegation, pk=pk)
    form = DelegationForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro actualizado correctamente.")
        return redirect("personal:delegation_list")
    return render(request, "personal/delegation_form.html", {"form": form, "object": obj})


@require("personal.change_delegation")
def delegation_delete(request, pk):
    """No borra: marca el registro como inactivo."""
    obj = get_object_or_404(Delegation, pk=pk)
    if request.method == "POST":
        obj.state = 'INACTIVO'
        obj.save(update_fields=["state"])
        messages.success(request, "Registro desactivado.")
        return redirect("personal:delegation_list")
    return render(request, "personal/delegation_confirm_delete.html", {"object": obj})

# ---------- Position ----------
@require("personal.view_position")
def position_list(request):
    qs = Position.objects.all()
    if not request.GET.get("all"):
        qs = qs.filter(validity=True)
    qs = search_queryset(qs, request.GET.get('q'), 'name')
    if request.GET.get('export') == 'xlsx':
        return excel_response(
            'cargos.xlsx',
            ['Cargo', 'Estado', 'Rol por defecto'],
            (
                [row.name, 'Activo' if row.validity else 'Inactivo',
                 str(row.default_role or '')]
                for row in qs.order_by('name')
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
    qs = Functionary.objects.select_related(
        "delegation", "position", "user"
    ).prefetch_related('functionaryrole_set__role')
    if not request.GET.get('all'):
        qs = qs.filter(is_active=True, deleted_at__isnull=True)
    if not _global_scope(request.user):
        functionary = getattr(request.user, 'functionary', None)
        if functionary is None:
            qs = qs.none()
        elif functionary.is_delegate:
            qs = qs.filter(delegation=functionary.delegation)
        else:
            qs = qs.filter(pk=functionary.pk)
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
    if position := request.GET.get("position"):
        if position.isdigit():
            qs = qs.filter(position_id=position)
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
                for row in qs.order_by('names', 'lastnames')
            ),
        )
    return _render_list(request, "personal/functionary_list.html", qs, {
        "showing_all": bool(request.GET.get("all")),
        "delegations": Delegation.objects.filter(state="ACTIVO"),
        "positions": Position.objects.filter(validity=True),
    })


@require("personal.add_functionary")
def functionary_create(request):
    form = FunctionaryCustomForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Usuario y funcionario creados correctamente.")
        return redirect("personal:functionary_list")
    return render(request, "personal/functionary_form.html", {"form": form})


@require("personal.change_functionary")
def functionary_update(request, pk):
    obj = get_object_or_404(Functionary, pk=pk)
    # Para editar datos básicos del funcionario (sin cambiar credenciales)
    form = FunctionaryUpdateForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Registro actualizado correctamente.")
        return redirect("personal:functionary_list")
    return render(request, "personal/functionary_form.html", {"form": form, "object": obj})


@require("personal.delete_functionary")
def functionary_delete(request, pk):
    obj = get_object_or_404(Functionary, pk=pk)
    if request.method == "POST":
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        if obj.user:
            obj.user.is_active = False
            obj.user.save(update_fields=["is_active"])
        messages.success(request, "Funcionario desactivado correctamente.")
        return redirect("personal:functionary_list")
    return render(request, "personal/functionary_confirm_delete.html", {"object": obj})
# ---------- Role ----------
@require("personal.view_role")
def role_list(request):
    queryset = Role.objects.all()
    if not request.GET.get('all'):
        queryset = queryset.filter(is_active=True, deleted_at__isnull=True)
    queryset = queryset.order_by('role_name')
    queryset = search_queryset(
        queryset,
        request.GET.get('q'),
        'role_name',
        'description',
        'authorized_scope',
    )
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
                for row in queryset.order_by('role_name')
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
                for assignment in qs.order_by(
                    'functionary__names',
                    'functionary__lastnames',
                    'role__role_name',
                )
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