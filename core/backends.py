from django.contrib.auth.backends import ModelBackend


class FunctionaryRoleBackend(ModelBackend):
    def get_all_permissions(self, user_obj, obj=None):
        permissions = set(super().get_all_permissions(user_obj, obj))
        if obj is not None or not user_obj.is_active:
            return permissions
        from organizations.community_access import portal_identity
        _, neighbor = portal_identity(user_obj)
        if neighbor and neighbor.portal_active:
            board_permissions = {f'{app}.{code}' for app, code in neighbor.role.permissions.values_list('content_type__app_label', 'codename')}
            if not neighbor.can_send_letters:
                board_permissions.discard('correspondence.add_officeletter')
            permissions.update(board_permissions)
        functionary = getattr(user_obj, 'functionary', None)
        if (
            functionary is None
            or not functionary.is_active
            or functionary.deleted_at is not None
        ):
            return permissions
        if not hasattr(user_obj, '_sgr_role_perm_cache'):
            role_permissions = functionary.functionaryrole_set.values_list(
                'role__permissions__content_type__app_label',
                'role__permissions__codename',
            ).filter(role__is_active=True, role__deleted_at__isnull=True, deleted_at__isnull=True)
            user_obj._sgr_role_perm_cache = {
                f'{app_label}.{codename}'
                for app_label, codename in role_permissions
                if app_label and codename
            }
        permissions.update(user_obj._sgr_role_perm_cache)
        return permissions
