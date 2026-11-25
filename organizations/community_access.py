from django.core.exceptions import PermissionDenied

PORTAL_GROUP = 'Acceso portal junta de vecinos'
MEMBER_ROLE = 'NEIGHBORHOOD_MEMBER'
ADMIN_ROLE = 'NEIGHBORHOOD_ADMIN'
AUTH_ROUTES = {
    'login', 'logout', 'password_change', 'password_change_done', 'password_reset',
    'password_reset_done', 'password_reset_confirm', 'password_reset_complete',
    'password_recovery_request', 'password_recovery_sent', 'password_recovery_verify',
    'password_recovery_set_password',
}


def portal_identity(user):
    if not user.is_authenticated:
        return False, None
    if not hasattr(user, '_community_identity'):
        from .models import NeighborhoodMember
        member = NeighborhoodMember.objects.select_related(
            'organization__delegation', 'role', 'leadership',
        ).filter(user_id=user.pk).first()
        restricted = member is not None or user.groups.filter(name=PORTAL_GROUP).exists()
        user._community_identity = restricted, member
    return user._community_identity


def portal_access(user, route, method='GET'):
    restricted, member = portal_identity(user)
    if not restricted:
        return None
    if route in AUTH_ROUTES:
        return True
    if not user.is_active or not member or not member.portal_active:
        return False
    if route in {'home', 'dashboard_redirect', 'user_dashboard', 'personal:profile_update', 'personal:profile_photo'}:
        return True
    if route in {'community:home', 'community:letters', 'community:letter_detail', 'community:members', 'community:profile'}:
        return method in ('GET', 'HEAD') or route == 'community:profile' and method == 'POST'
    if route == 'community:letter_create':
        return member.can_send_letters and method in ('GET', 'POST', 'HEAD')
    if route in {'community:member_create', 'community:member_update', 'community:board'}:
        return member.is_manager and method in ('GET', 'POST', 'HEAD')
    return False


def require_member(user, manage=False):
    _, member = portal_identity(user)
    if not user.is_authenticated or not user.is_active or not member or not member.portal_active:
        raise PermissionDenied('Tu cuenta no tiene un acceso activo a una junta de vecinos.')
    if manage and not member.is_manager:
        raise PermissionDenied('Solo el administrador de esta junta puede gestionar integrantes y cargos.')
    return member
