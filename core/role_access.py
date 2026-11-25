"""Controles por acción para los perfiles del descriptor, además del alcance existente.

Los roles anteriores conservan su comportamiento. Un perfil documental sin
permisos activos queda bloqueado; los permisos se suman entre roles activos.
"""
from django.core.exceptions import PermissionDenied
from personal.document_roles import ROLE_LABELS


ROUTES = {}


def register(namespace, model, actions):
    for action, names in actions.items():
        for name in names.split():
            ROUTES[f'{namespace}:{name}'] = (f'{model.split(".")[0]}.{action}_{model.split(".")[1]}',)


register('atenciones', 'atenciones.attention', {
    'view': 'attention_list attention_detail subattention_options',
    'add': 'attention_create', 'change': 'attention_update', 'delete': 'attention_delete',
})
register('agenda', 'agenda.commitment', {
    'view': 'commitment_list', 'add': 'commitment_create',
    'change': 'commitment_update', 'delete': 'commitment_delete',
})
register('agenda', 'agenda.meeting', {
    'view': 'meeting_list meeting_detail', 'add': 'meeting_create', 'change': 'meeting_update',
})
register('agenda', 'agenda.meetingagreement', {'add': 'agreement_create', 'change': 'agreement_update'})
register('organizations', 'organizations.organization', {
    'view': 'list detail', 'add': 'create', 'change': 'update',
})
register('organizations', 'organizations.organizationleader', {'add': 'leader_create', 'change': 'leader_update'})
register('correspondence', 'correspondence.officeletter', {
    'view': 'letter_list letter_detail', 'add': 'letter_create',
    'change': 'letter_update', 'delete': 'letter_delete',
})
register('activities', 'activities.activity', {
    'view': 'activity_list traffic_light', 'add': 'activity_create',
    'change': 'activity_update', 'delete': 'activity_delete',
})
register('activities', 'activities.evidence', {
    'view': 'evidence_list evidence_file', 'add': 'evidence_create', 'change': 'evidence_validate',
})
register('events', 'events.communityevent', {
    'view': 'management_list', 'add': 'event_create', 'change': 'event_update event_cancel',
})
register('events', 'events.delegationperson', {'view': 'person_list', 'add': 'person_create', 'change': 'person_update'})
register('events', 'events.eventregistration', {'view': 'registration_list', 'change': 'registration_review'})
register('events', 'events.eventorganization', {'change': 'organization_participation_update'})
ROUTES.update({
    'atenciones:attention_commitment_create': ('atenciones.view_attention', 'agenda.add_commitment'),
    'agenda:agreement_convert': ('agenda.change_meetingagreement', 'agenda.add_commitment'),
    'organizations:attention_link': ('organizations.change_organization', 'atenciones.change_attention'),
    'correspondence:letter_attention_create': ('correspondence.change_officeletter', 'atenciones.add_attention'),
    'correspondence:letter_attention_link': ('correspondence.change_officeletter', 'atenciones.change_attention'),
})
PUBLIC_ROUTES = {'events:public_list', 'events:public_register', 'events:verify_email'}
SELF_ROUTES = {'personal:profile_update', 'personal:profile_photo', 'personal:delegation_chat',
               'home', 'dashboard_redirect', 'user_dashboard'}


def document_profile(user):
    if not user.is_authenticated or user.is_superuser:
        return False
    fn = getattr(user, 'functionary', None)
    if not hasattr(user, '_document_profile'):
        user._document_profile = bool(fn and fn.functionaryrole_set.filter(role__role_name__in=ROLE_LABELS).exists())
    return user._document_profile


def can_access(user, route, method='GET'):
    from organizations.community_access import portal_access
    community_allowed = portal_access(user, route, method)
    if community_allowed is not None:
        return community_allowed
    if not document_profile(user):
        return True
    if route in PUBLIC_ROUTES:
        return True
    fn = user.functionary
    if not user.is_active or not fn.is_active or fn.deleted_at is not None:
        return False
    if route in SELF_ROUTES:
        return True
    if route == 'events:organization_invitations':
        action = 'change' if method == 'POST' else 'view'
        return user.has_perm(f'events.{action}_eventorganization')
    if route == 'atenciones:attention_detail' and method not in ('GET', 'HEAD', 'OPTIONS'):
        return user.has_perm('atenciones.change_attention')
    if route in ROUTES:
        if method not in ('GET', 'HEAD', 'OPTIONS') and all('.view_' in p for p in ROUTES[route]):
            return False
        return user.has_perms(ROUTES[route])
    # Administración, catálogos y rutas nuevas requieren autorización explícita.
    return False


class DocumentRoleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        from organizations.community_access import portal_access
        if portal_access(request.user, match.view_name, request.method) is False:
            raise PermissionDenied('Tu cuenta solo puede acceder a las funciones de su junta de vecinos.')
        # Login, recuperación, logout y administración Django conservan sus controles.
        if match.app_name == 'admin' or match.view_name in {
            'login', 'logout', 'password_change', 'password_change_done',
            'password_reset', 'password_reset_done', 'password_reset_confirm', 'password_reset_complete',
            'password_recovery_request', 'password_recovery_sent',
            'password_recovery_verify', 'password_recovery_set_password',
        }:
            return None
        if not can_access(request.user, match.view_name, request.method):
            raise PermissionDenied('Tu cargo no tiene permiso para realizar esta acción.')
