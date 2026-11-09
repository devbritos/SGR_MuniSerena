from channels.generic.websocket import AsyncJsonWebsocketConsumer


class DataUpdatesConsumer(AsyncJsonWebsocketConsumer):
    group_name = 'sgr_data_updates'

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if self.scope.get('user') and self.scope['user'].is_authenticated:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def data_changed(self, event):
        await self.send_json({'type': 'data_changed'})
