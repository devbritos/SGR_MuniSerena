from django.urls import path

from . import views

app_name = 'atenciones'

urlpatterns = [
    path('', views.AttentionListView.as_view(), name='attention_list'),
    path('nueva/', views.AttentionCreateView.as_view(), name='attention_create'),
    path(
        '<int:pk>/editar/',
        views.AttentionUpdateView.as_view(),
        name='attention_update',
    ),
    path(
        '<int:pk>/eliminar/',
        views.AttentionDeleteView.as_view(),
        name='attention_delete',
    ),
    path(
        'tipos/',
        views.AttentionTypeListView.as_view(),
        name='attention_type_list',
    ),
    path(
        'tipos/nuevo/',
        views.AttentionTypeCreateView.as_view(),
        name='attention_type_create',
    ),
    path(
        'tipos/<int:pk>/editar/',
        views.AttentionTypeUpdateView.as_view(),
        name='attention_type_update',
    ),
    path(
        'tipos/<int:pk>/desactivar/',
        views.AttentionTypeDeactivateView.as_view(),
        name='attention_type_deactivate',
    ),
    path(
        'subatenciones/',
        views.SubAttentionListView.as_view(),
        name='subattention_list',
    ),
    path(
        'subatenciones/nueva/',
        views.SubAttentionCreateView.as_view(),
        name='subattention_create',
    ),
    path(
        'subatenciones/<int:pk>/editar/',
        views.SubAttentionUpdateView.as_view(),
        name='subattention_update',
    ),
    path(
        'subatenciones/<int:pk>/desactivar/',
        views.SubAttentionDeactivateView.as_view(),
        name='subattention_deactivate',
    ),
    path(
        'api/tipos/<int:type_id>/subatenciones/',
        views.subattention_options,
        name='subattention_options',
    ),
]
