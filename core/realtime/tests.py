from types import SimpleNamespace

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings

from personal.models import Delegation

from .consumers import DataUpdatesConsumer
from .signals import GROUP_NAME


@override_settings(
    CHANNEL_LAYERS={
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
)
class DataUpdateSignalTests(TransactionTestCase):
    def test_model_save_notifies_connected_clients_after_commit(self):
        channel_layer = get_channel_layer()
        channel_name = async_to_sync(channel_layer.new_channel)()
        async_to_sync(channel_layer.group_add)(GROUP_NAME, channel_name)
        self.addCleanup(
            async_to_sync(channel_layer.group_discard),
            GROUP_NAME,
            channel_name,
        )

        Delegation.objects.create(name='Delegación en tiempo real', field='URBANO')

        event = async_to_sync(channel_layer.receive)(channel_name)
        self.assertEqual(event['type'], 'data.changed')

    async def test_connected_user_receives_saved_data_notification(self):
        communicator = WebsocketCommunicator(
            DataUpdatesConsumer.as_asgi(),
            '/ws/updates/',
        )
        communicator.scope['user'] = SimpleNamespace(is_authenticated=True)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await database_sync_to_async(Delegation.objects.create)(
            name='Delegación para cliente conectado',
            field='URBANO',
        )

        self.assertEqual(
            await communicator.receive_json_from(),
            {'type': 'data_changed'},
        )
        await communicator.disconnect()
