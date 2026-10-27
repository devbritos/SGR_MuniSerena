from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
 
 
def require(perm):
    """Exige permiso Django o el rol Administrador, además de iniciar sesión.
 
    Sin acceso responde 403. Sin login redirige al login.
    """
    def decorator(view):
        def has_access(user):
            if user.has_perm(perm) or user.is_superuser:
                return True
            functionary = getattr(user, 'functionary', None)
            return bool(functionary and functionary.is_admin)

        @login_required
        @wraps(view)
        def wrapped_view(request, *args, **kwargs):
            if not has_access(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped_view

    return decorator
 