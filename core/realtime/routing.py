from django.urls import path

from .consumers import DataUpdatesConsumer
from personal.consumers import DelegationChatConsumer

websocket_urlpatterns = [
    path('ws/updates/', DataUpdatesConsumer.as_asgi()),
    path('ws/chat/', DelegationChatConsumer.as_asgi()),
]
