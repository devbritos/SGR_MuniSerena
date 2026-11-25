from django.urls import path
from . import neighbor_views, views
app_name = 'organizations'
urlpatterns = [
    path('vecinos/', neighbor_views.NeighborListView.as_view(), name='neighbors'),
    path('', views.OrganizationListView.as_view(), name='list'),
    path('nueva/', views.OrganizationCreateView.as_view(), name='create'),
    path('<int:pk>/', views.OrganizationDetailView.as_view(), name='detail'),
    path('<int:pk>/atenciones/vincular/', views.OrganizationAttentionLinkView.as_view(), name='attention_link'),
    path('<int:pk>/editar/', views.OrganizationUpdateView.as_view(), name='update'),
    path('<int:organization_pk>/dirigentes/nuevo/', views.LeaderCreateView.as_view(), name='leader_create'),
    path('<int:organization_pk>/dirigentes/<int:pk>/editar/', views.LeaderUpdateView.as_view(), name='leader_update'),
]
