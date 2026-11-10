from django.urls import path

from .consumers import DataUpdatesConsumer

websocket_urlpatterns = [
    path('ws/updates/', DataUpdatesConsumer.as_asgi()),
]
