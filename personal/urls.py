from django.urls import path

from . import views

app_name = "personal"

urlpatterns = [
    path("profile/", views.profile_update, name="profile_update"),
    path("profile/photo/", views.profile_photo, name="profile_photo"),

    # Delegation
    path("delegations/", views.delegation_list, name="delegation_list"),
    path("delegations/<int:pk>/", views.delegation_detail, name="delegation_detail"),
    path("delegations/new/", views.delegation_create, name="delegation_create"),
    path("delegations/<int:pk>/edit/", views.delegation_update, name="delegation_update"),
    path("delegations/<int:pk>/delete/", views.delegation_delete, name="delegation_delete"),

    # Position
    path("positions/", views.position_list, name="position_list"),
    path("positions/new/", views.position_create, name="position_create"),
    path("positions/<int:pk>/edit/", views.position_update, name="position_update"),
    path("positions/<int:pk>/delete/", views.position_delete, name="position_delete"),

    # Functionary
    path("functionaries/", views.functionary_list, name="functionary_list"),
    path("functionaries/<int:pk>/", views.functionary_detail, name="functionary_detail"),
    path("functionaries/<int:pk>/photo/", views.functionary_photo, name="functionary_photo"),
    path("functionaries/new/", views.functionary_create, name="functionary_create"),
    path("functionaries/<int:pk>/edit/", views.functionary_update, name="functionary_update"),
    path("functionaries/<int:pk>/delete/", views.functionary_delete, name="functionary_delete"),

    # Role
    path("roles/", views.role_list, name="role_list"),
    path("roles/new/", views.role_create, name="role_create"),
    path("roles/<int:pk>/edit/", views.role_update, name="role_update"),
    path("roles/<int:pk>/delete/", views.role_delete, name="role_delete"),

    # FunctionaryRole
    path("functionary-roles/", views.functionary_role_list, name="functionary_role_list"),
    path("functionary-roles/new/", views.functionary_role_create, name="functionary_role_create"),
    path("functionary-roles/<int:pk>/delete/", views.functionary_role_delete, name="functionary_role_delete"),
]