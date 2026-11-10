from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


def _active_functionary(user):
    if not user.is_authenticated or not user.is_active:
        return None
    functionary = getattr(user, 'functionary', None)
    if (
        functionary is None
        or functionary.deleted_at is not None
        or not functionary.is_active
    ):
        return None
    return functionary


class FunctionaryRequiredMixin(UserPassesTestMixin):
    """Verifica que el usuario esté autenticado y posea un perfil de Funcionario activo."""

    def test_func(self):
        return _active_functionary(self.request.user) is not None

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            'Tu usuario no posee un perfil de funcionario activo asignado.'
        )


class FunctionaryOrStaffRequiredMixin(UserPassesTestMixin):
    """Permite el acceso a funcionarios activos y administradores de Django."""

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (
            user.is_staff or user.is_superuser or _active_functionary(user) is not None
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            'Se requiere una cuenta administrativa o un perfil de funcionario activo.'
        )


class VerifierRequiredMixin(UserPassesTestMixin):
    """
    Permite el acceso a Verificadores, Delegados o Administradores (RF-013).
    Utilizado para validar actividades y revisar evidencias.
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        functionary = _active_functionary(user)
        return functionary is not None and functionary.is_verifier

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            'No tienes permisos de Verificador para validar actividades o evidencias.'
        )


class DelegateRequiredMixin(UserPassesTestMixin):
    """
    Permite el acceso a Delegados/Jefaturas, Coordinadores o Administradores.
    Utilizado para monitoreo de la delegación y reasignación de compromisos.
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        functionary = _active_functionary(user)
        return functionary is not None and (
            functionary.is_delegate or functionary.is_admin
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            'Acceso restringido a Delegados de área o Coordinadores del SGR.'
        )


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Permite el acceso únicamente a Administradores del Sistema (RF-001, RF-002).
    Utilizado para configuración de cargos, períodos, metadatos y usuarios.
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        functionary = _active_functionary(user)
        return functionary is not None and functionary.is_admin

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            'Se requieren privilegios de Administrador del SGR.'
        )