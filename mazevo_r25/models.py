from descriptors import cachedclassproperty
from django.db import models
from uw_mazevo.api import PublicConfiguration

from .more_r25 import get_event_type_list, get_space_list


class MazevoRoomSpace(models.Model):
    """
    Assigns R25 spaces to Mazevo rooms
    """

    @cachedclassproperty
    def room_names(cls):
        room_names = {}
        for room in PublicConfiguration().get_rooms():
            room_names[room.id] = room.description
        return room_names

    @cachedclassproperty
    def space_names(cls):
        return dict(get_space_list())

    room_id = models.PositiveIntegerField(primary_key=True)
    space_id = models.PositiveIntegerField(unique=True, null=True, default=None)
    date_changed = models.DateTimeField(auto_now=True)

    @property
    def room_name(self):
        if self.room_id not in self.room_names:
            return ''
        return self.room_names[self.room_id]

    @property
    def space_name(self):
        try:
            return self.space_names[self.space_id]
        except Exception:
            return "Invalid"


class MazevoStatusMap(models.Model):
    """
    Maps Mazevo status to action and R25 event type
    """

    @cachedclassproperty
    def status_names(cls):
        status_names = {}
        for status in PublicConfiguration().get_statuses():
            status_names[status.id] = status.description
        return status_names

    @cachedclassproperty
    def event_type_names(cls):
        return dict(get_event_type_list(all_types="T"))

    ACTION_IGNORE = "ignore"
    ACTION_REMOVE = "remove"
    ACTION_ADD = "add"
    ACTION_CHOICES = (
        (ACTION_IGNORE, "Neither add nor remove from R25"),
        (ACTION_REMOVE, "Remove if present in R25"),
        (ACTION_ADD, "Add if not present in R25"),
    )

    status_id = models.PositiveIntegerField(primary_key=True)
    action = models.SlugField(choices=ACTION_CHOICES, null=True)
    event_type_id = models.IntegerField(null=True)

    @property
    def status_name(self):
        if self.status_id not in self.status_names:
            return ''
        return self.status_names[self.status_id]

    @property
    def event_type_name(self):
        try:
            return self.event_type_names[self.event_type_id]
        except Exception:
            return "Invalid"
