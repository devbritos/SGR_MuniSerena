from django.urls import path
from . import views

app_name = 'agenda'

urlpatterns = [
    path('', views.CommitmentListView.as_view(), name='commitment_list'),
    path('nuevo/', views.CommitmentCreateView.as_view(), name='commitment_create'),
    path('<int:pk>/editar/', views.CommitmentUpdateView.as_view(), name='commitment_update'),
    path('<int:pk>/eliminar/', views.CommitmentDeleteView.as_view(), name='commitment_delete'),
]