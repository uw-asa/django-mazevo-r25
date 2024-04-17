from django.db import models

class MazevoRoomSpace(models.Model):
    """
    Assigns R25 spaces to Mazevo rooms
    """
    room_id = models.PositiveIntegerField(primary_key=True)
    space_id = models.PositiveIntegerField(unique=True, null=True, default=None)
    date_changed = models.DateTimeField(auto_now=True)
