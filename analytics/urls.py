from django.urls import path
from . import views
from activities.views import TrafficLightView

urlpatterns = [
    path('', views.dashboard_redirect, name='dashboard_redirect'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('mi-panel/', views.user_dashboard, name='user_dashboard'),
    path(
        'delegacion/<int:delegacion_id>/',
        TrafficLightView.as_view(),
        name='dashboard_delegation_detail',
    ),
]