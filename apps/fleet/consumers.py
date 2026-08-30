import json
from channels.generic.websocket import AsyncWebsocketConsumer

class FleetLocationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.vehicle_id = self.scope['url_route']['kwargs']['vehicle_id']
        self.room_group_name = f'bus_{self.vehicle_id}_location'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from room group
    async def location_update(self, event):
        latitude = event['latitude']
        longitude = event['longitude']
        timestamp = event.get('timestamp')
        speed = event.get('speed', 0)

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'location_update',
            'latitude': latitude,
            'longitude': longitude,
            'timestamp': timestamp,
            'speed': speed,
        }))
