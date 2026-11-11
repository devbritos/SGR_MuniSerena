from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import DelegationChatMessage, Functionary


MAX_MESSAGE_LENGTH = 2000


@database_sync_to_async
def _active_delegation_id(user_id):
    return Functionary.objects.filter(
        user_id=user_id,
        user__is_active=True,
        is_active=True,
        deleted_at__isnull=True,
        delegation__deleted_at__isnull=True,
    ).values_list('delegation_id', flat=True).first()


@database_sync_to_async
def _save_message(user_id, delegation_id, body):
    functionary = Functionary.objects.filter(
        user_id=user_id,
        user__is_active=True,
        delegation_id=delegation_id,
        is_active=True,
        deleted_at__isnull=True,
        delegation__deleted_at__isnull=True,
    ).first()
    if functionary is None:
        return None

    message = DelegationChatMessage.objects.create(
        delegation_id=delegation_id,
        sender=functionary,
        body=body,
    )
    return _serialize_message(message)


def _serialize_message(message):
    return {
        'id': message.pk,
        'sender_id': message.sender.user_id,
        'sender_name': message.sender.full_name,
        'body': message.body,
        'sent_at': timezone.localtime(message.created_at).isoformat(),
    }


@database_sync_to_async
def _recent_messages(user_id, delegation_id):
    still_authorized = Functionary.objects.filter(
        user_id=user_id,
        user__is_active=True,
        delegation_id=delegation_id,
        is_active=True,
        deleted_at__isnull=True,
        delegation__deleted_at__isnull=True,
    ).exists()
    if not still_authorized:
        return None

    messages = list(
        DelegationChatMessage.objects.filter(
            delegation_id=delegation_id,
            sender__is_active=True,
            sender__deleted_at__isnull=True,
        )
        .select_related('sender')
        .order_by('-created_at', '-pk')[:50]
    )
    messages.reverse()
    return [_serialize_message(message) for message in messages]


class DelegationChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        delegation_id = await _active_delegation_id(user.pk)
        if delegation_id is None:
            await self.close(code=4403)
            return

        self.delegation_id = delegation_id
        self.group_name = f'delegation_chat_{delegation_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        messages = await _recent_messages(user.pk, delegation_id)
        if messages is None:
            await self.close(code=4403)
            return
        await self.send_json({'type': 'history', 'messages': messages})

    async def disconnect(self, close_code):
        group_name = getattr(self, 'group_name', None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.send_json({
                'type': 'error',
                'message': 'El mensaje enviado no es válido.',
            })
            return

        body = content.get('message')
        if not isinstance(body, str) or not body.strip():
            await self.send_json({
                'type': 'error',
                'message': 'Escribe un mensaje antes de enviarlo.',
            })
            return

        body = body.strip()
        if len(body) > MAX_MESSAGE_LENGTH:
            await self.send_json({
                'type': 'error',
                'message': 'El mensaje supera el máximo de 2000 caracteres.',
            })
            return

        message = await _save_message(
            self.scope['user'].pk,
            self.delegation_id,
            body,
        )
        if message is None:
            await self.close(code=4403)
            return

        await self.channel_layer.group_send(
            self.group_name,
            {'type': 'chat.message', 'message': message},
        )

    async def chat_message(self, event):
        if await _active_delegation_id(self.scope['user'].pk) != self.delegation_id:
            await self.close(code=4403)
            return

        await self.send_json({
            'type': 'message',
            'message': event['message'],
        })
