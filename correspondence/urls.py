from django.urls import path

from . import views

app_name = 'correspondence'

urlpatterns = [
    path('', views.OfficeLetterListView.as_view(), name='letter_list'),
    path('nueva/', views.OfficeLetterCreateView.as_view(), name='letter_create'),
    path(
        '<int:pk>/editar/',
        views.OfficeLetterUpdateView.as_view(),
        name='letter_update',
    ),
    path(
        '<int:pk>/archivar/',
        views.OfficeLetterDeleteView.as_view(),
        name='letter_delete',
    ),
]
