from django.urls import path
from . import community_views as views

app_name = 'community'
urlpatterns = [
    path('', views.home, name='home'),
    path('cartas/', views.letters, name='letters'),
    path('cartas/nueva/', views.letter_create, name='letter_create'),
    path('cartas/<int:pk>/', views.letter_detail, name='letter_detail'),
    path('integrantes/', views.members, name='members'),
    path('integrantes/nuevo/', views.member_form, name='member_create'),
    path('integrantes/<int:pk>/editar/', views.member_form, name='member_update'),
    path('directiva/', views.board, name='board'),
    path('perfil/', views.profile, name='profile'),
]
