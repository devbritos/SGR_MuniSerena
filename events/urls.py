from django.urls import path

from . import views

app_name = 'events'

urlpatterns = [
    path('', views.PublicEventListView.as_view(), name='public_list'),
    path(
        'inscribirse/<int:pk>/',
        views.PublicEventRegistrationView.as_view(),
        name='public_register',
    ),
    path(
        'verificar-correo/<str:token>/',
        views.VerifyRegistrationEmailView.as_view(),
        name='verify_email',
    ),
    path('gestion/', views.EventManagementListView.as_view(), name='management_list'),
    path('gestion/nuevo/', views.EventCreateView.as_view(), name='event_create'),
    path(
        'gestion/<int:pk>/editar/',
        views.EventUpdateView.as_view(),
        name='event_update',
    ),
    path(
        'gestion/<int:pk>/cancelar/',
        views.EventCancelView.as_view(),
        name='event_cancel',
    ),
    path('gestion/padron/', views.PersonListView.as_view(), name='person_list'),
    path(
        'gestion/padron/nueva/',
        views.PersonCreateView.as_view(),
        name='person_create',
    ),
    path(
        'gestion/padron/<int:pk>/editar/',
        views.PersonUpdateView.as_view(),
        name='person_update',
    ),
    path(
        'gestion/inscripciones/',
        views.RegistrationListView.as_view(),
        name='registration_list',
    ),
    path(
        'gestion/inscripciones/<int:pk>/revisar/',
        views.RegistrationReviewView.as_view(),
        name='registration_review',
    ),
]
