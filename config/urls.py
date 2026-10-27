from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from core.auth_views import (
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
        auth_views.LoginView.as_view(
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