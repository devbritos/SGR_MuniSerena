from django.urls import path
from . import views
from . import meeting_views

app_name = 'agenda'

urlpatterns = [
    path('reuniones/', meeting_views.MeetingListView.as_view(), name='meeting_list'),
    path('reuniones/nueva/', meeting_views.MeetingFormView.as_view(), name='meeting_create'),
    path('reuniones/<int:pk>/', meeting_views.MeetingDetailView.as_view(), name='meeting_detail'),
    path('reuniones/<int:pk>/editar/', meeting_views.MeetingFormView.as_view(), name='meeting_update'),
    path('reuniones/<int:pk>/acuerdos/nuevo/', meeting_views.AgreementFormView.as_view(), name='agreement_create'),
    path('reuniones/<int:pk>/acuerdos/<int:agreement_pk>/editar/', meeting_views.AgreementFormView.as_view(), name='agreement_update'),
    path('reuniones/<int:pk>/acuerdos/<int:agreement_pk>/compromiso/nuevo/', meeting_views.AgreementConvertView.as_view(), name='agreement_convert'),
    path('', views.CommitmentListView.as_view(), name='commitment_list'),
    path('nuevo/', views.CommitmentCreateView.as_view(), name='commitment_create'),
    path('<int:pk>/editar/', views.CommitmentUpdateView.as_view(), name='commitment_update'),
    path('<int:pk>/eliminar/', views.CommitmentDeleteView.as_view(), name='commitment_delete'),
]
