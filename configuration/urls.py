from django.urls import path
from . import views


app_name = 'configuration'


urlpatterns = [
    path('items/', views.MeasuringListView.as_view(), name='measuring_list'),
    path('items/nuevo/', views.MeasuringCreateView.as_view(), name='measuring_create'),
    path('items/<int:pk>/editar/', views.MeasuringUpdateView.as_view(), name='measuring_update'),
    path('items/<int:pk>/desactivar/', views.MeasuringDeactivateView.as_view(), name='measuring_deactivate'),
    path('metas/',views.GoalListView.as_view(), name = 'goal_list'),
    path('metas/nueva/',views.GoalCreateView.as_view(), name = 'goal_create'),
    path('metas/<int:pk>/editar/', views.GoalUpdateView.as_view(), name='goal_update'),
    path('metas/<int:pk>/desactivar/', views.GoalDeactivateView.as_view(), name='goal_deactivate'),
    path('periodos/nuevo/',views.PeriodCreateView.as_view(), name = 'period_create')
]