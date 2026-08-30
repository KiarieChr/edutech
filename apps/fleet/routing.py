from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/fleet/live/(?P<vehicle_id>\w+)/$', consumers.FleetLocationConsumer.as_asgi()),
]
