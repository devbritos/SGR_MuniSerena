from django.urls import path
from . import views

app_name = 'activities'


urlpatterns = [
    path('', views.ActivityListView.as_view(), name = "activity_list"),
    path('nueva/', views.ActivityCreateView.as_view(), name='activity_create'),
    path('<int:pk>/editar/', views.ActivityUpdateView.as_view(), name='activity_update'),
    path('<int:pk>/eliminar/', views.ActivityDeleteView.as_view(), name='activity_delete'),

    path('evidencias/', views.EvidenceListView.as_view(), name='evidence_list'),
    path('evidencias/nueva/', views.EvidenceCreateView.as_view(), name='evidence_create'),
    path(
        'evidencias/<int:pk>/validar/',
        views.EvidenceValidateView.as_view(),
        name='evidence_validate',
    ),
    path('traffic_light/',views.TrafficLightView.as_view(),name = 'traffic_light'),
]