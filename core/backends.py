from django.contrib.auth.backends import ModelBackend


class FunctionaryRoleBackend(ModelBackend):
    def get_all_permissions(self, user_obj, obj=None):
        permissions = set(super().get_all_permissions(user_obj, obj))
        if obj is not None or not user_obj.is_active:
            return permissions
        functionary = getattr(user_obj, 'functionary', None)
        if (
            functionary is None
            or not functionary.is_active
            or functionary.deleted_at is not None
        ):
            return permissions
        role_permissions = functionary.functionaryrole_set.values_list(
            'role__permissions__content_type__app_label',
            'role__permissions__codename',
        ).filter(role__is_active=True)
        permissions.update(
            f'{app_label}.{codename}'
            for app_label, codename in role_permissions
            if app_label and codename
        )
        return permissions
