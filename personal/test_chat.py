from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .consumers import DelegationChatConsumer
from .models import (
    Delegation,
    DelegationChatMessage,
    Functionary,
    Position,
)


class DelegationChatViewTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name='Delegación Chat Norte',
            field='URBANO',
        )
        self.position = Position.objects.create(name='Cargo Chat')
        self.user = User.objects.create_user(
            username='chat_usuario',
            password='test-password',
        )
        self.functionary = Functionary.objects.create(
            user=self.user,
            delegation=self.delegation,
            position=self.position,
            names='Camila',
            lastnames='Rojas',
        )
        self.client.force_login(self.user)

    def test_chat_page_shows_only_this_delegations_messages_and_members(self):
        colleague_user = User.objects.create_user(
            username='chat_colega',
            password='test-password',
        )
        colleague = Functionary.objects.create(
            user=colleague_user,
            delegation=self.delegation,
            position=self.position,
            names='Pedro',
            lastnames='Soto',
        )
        other_delegation = Delegation.objects.create(
            name='Delegación Chat Sur',
            field='RURAL',
        )
        other_user = User.objects.create_user(
            username='chat_otra_delegacion',
            password='test-password',
        )
        other_functionary = Functionary.objects.create(
            user=other_user,
            delegation=other_delegation,
            position=self.position,
            names='Isabel',
            lastnames='Vera',
        )
        DelegationChatMessage.objects.create(
            delegation=self.delegation,
            sender=colleague,
            body='Mensaje visible para el equipo',
        )
        DelegationChatMessage.objects.create(
            delegation=other_delegation,
            sender=other_functionary,
            body='Mensaje privado de otra delegación',
        )

        response = self.client.get(reverse('personal:delegation_chat'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chat de Delegación Chat Norte')
        self.assertContains(response, 'Pedro Soto')
        self.assertContains(response, 'Mensaje visible para el equipo')
        self.assertNotContains(response, 'Isabel Vera')
        self.assertNotContains(response, 'Mensaje privado de otra delegación')
        self.assertContains(response, 'data-websocket-path="/ws/chat/"')
        self.assertContains(response, 'data-delegation-chat-shortcut')
        self.assertContains(
            response,
            f'aria-label="Abrir el chat de {self.delegation.name}"',
        )

    def test_chat_is_unavailable_without_an_active_functionary(self):
        self.functionary.is_active = False
        self.functionary.save(update_fields=['is_active'])

        response = self.client.get(reverse('personal:delegation_chat'))

        self.assertEqual(response.status_code, 403)

    def test_chat_shortcut_is_available_for_an_inactive_delegation(self):
        self.delegation.state = 'INACTIVO'
        self.delegation.save(update_fields=['state'])

        response = self.client.get(reverse('personal:delegation_chat'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-delegation-chat-shortcut')

    def test_chat_messages_do_not_trigger_a_global_page_refresh(self):
        with patch('core.realtime.signals.schedule_data_update') as notify_clients:
            DelegationChatMessage.objects.create(
                delegation=self.delegation,
                sender=self.functionary,
                body='Mensaje solo para el chat',
            )

        notify_clients.assert_not_called()


@override_settings(
    CHANNEL_LAYERS={
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
)
class DelegationChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.north = Delegation.objects.create(
            name='Delegación WS Norte',
            field='URBANO',
        )
        self.south = Delegation.objects.create(
            name='Delegación WS Sur',
            field='RURAL',
        )
        self.position = Position.objects.create(name='Cargo WS')
        self.users = []
        for username, delegation, names in (
            ('ws_emisor', self.north, 'Ana'),
            ('ws_colega', self.north, 'Luis'),
            ('ws_otra_delegacion', self.south, 'Marta'),
        ):
            user = User.objects.create_user(
                username=username,
                password='test-password',
            )
            Functionary.objects.create(
                user=user,
                delegation=delegation,
                position=self.position,
                names=names,
                lastnames='Prueba',
            )
            self.users.append(user)

    async def _connect(self, user):
        communicator = WebsocketCommunicator(
            DelegationChatConsumer.as_asgi(),
            '/ws/chat/',
        )
        communicator.scope['user'] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def test_messages_are_persisted_and_only_reach_the_same_delegation(self):
        sender, colleague, other_delegation = self.users
        communicators = [
            await self._connect(sender),
            await self._connect(colleague),
            await self._connect(other_delegation),
        ]
        try:
            for communicator in communicators:
                history = await communicator.receive_json_from()
                self.assertEqual(history['type'], 'history')

            await communicators[0].send_json_to({'message': 'Hola, equipo'})

            for communicator in communicators[:2]:
                payload = await communicator.receive_json_from()
                self.assertEqual(payload['type'], 'message')
                self.assertEqual(payload['message']['body'], 'Hola, equipo')
                self.assertEqual(payload['message']['sender_name'], 'Ana Prueba')

            self.assertTrue(await communicators[2].receive_nothing(timeout=0.1))
            stored_messages = await database_sync_to_async(
                DelegationChatMessage.objects.filter(
                    delegation=self.north,
                    body='Hola, equipo',
                ).count
            )()
            self.assertEqual(stored_messages, 1)
        finally:
            for communicator in communicators:
                await communicator.disconnect()

    async def test_unlinked_user_cannot_join_the_chat(self):
        user = await database_sync_to_async(
            User.objects.create_user
        )(
            username='ws_sin_funcionario',
            password='test-password',
        )
        communicator = WebsocketCommunicator(
            DelegationChatConsumer.as_asgi(),
            '/ws/chat/',
        )
        communicator.scope['user'] = user

        connected, _ = await communicator.connect()

        self.assertFalse(connected)
