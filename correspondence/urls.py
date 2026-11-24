from django.urls import path

from . import views

app_name = 'correspondence'

urlpatterns = [
    path('', views.OfficeLetterListView.as_view(), name='letter_list'),
    path('nueva/', views.OfficeLetterCreateView.as_view(), name='letter_create'),
    path('<int:pk>/', views.OfficeLetterDetailView.as_view(), name='letter_detail'),
    path('<int:pk>/atencion/nueva/', views.OfficeLetterAttentionCreateView.as_view(), name='letter_attention_create'),
    path('<int:pk>/atencion/vincular/', views.OfficeLetterAttentionLinkView.as_view(), name='letter_attention_link'),
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
