from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core.auth_views import (
    SGRLoginView,
    password_recovery_request,
    password_recovery_sent,
    password_recovery_set_password,
    password_recovery_verify,
)
from core.forms import UsernameOrEmailAuthenticationForm

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard_redirect")),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        SGRLoginView.as_view(
            authentication_form=UsernameOrEmailAuthenticationForm
        ),
        name="login",
    ),
    path(
        "accounts/recuperar-codigo/",
        password_recovery_request,
        name="password_recovery_request",
    ),
    path(
        "accounts/recuperar-codigo/enviado/",
        password_recovery_sent,
        name="password_recovery_sent",
    ),
    path(
        "accounts/recuperar-codigo/validar/",
        password_recovery_verify,
        name="password_recovery_verify",
    ),
    path(
        "accounts/recuperar-codigo/nueva-clave/",
        password_recovery_set_password,
        name="password_recovery_set_password",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("personal/", include("personal.urls")),
    path("dashboard/", include("analytics.urls")),
    path("activities/", include("activities.urls")),
    path("agenda/", include("agenda.urls")),
    path("configuration/", include("configuration.urls")),
    path("atenciones/", include("atenciones.urls")),
]

handler400 = "core.error_views.handler400"
handler403 = "core.error_views.handler403"
handler404 = "core.error_views.handler404"
handler500 = "core.error_views.handler500"