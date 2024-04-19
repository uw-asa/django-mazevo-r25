from django.db import models
from uw_mazevo.api import PublicConfiguration

from .more_r25 import get_space_list

room_names = {}
for room in PublicConfiguration().get_rooms():
    room_names[room.id] = room.description

space_names = dict(get_space_list())

class MazevoRoomSpace(models.Model):
    """
    Assigns R25 spaces to Mazevo rooms
    """
    room_id = models.PositiveIntegerField(primary_key=True)
    space_id = models.PositiveIntegerField(unique=True, null=True, default=None)
    date_changed = models.DateTimeField(auto_now=True)

    @property
    def room_name(self):
        return room_names[self.room_id]

    @property
    def space_name(self):
        try:
            return space_names[self.space_id]
        except:
            return 'Invalid'
