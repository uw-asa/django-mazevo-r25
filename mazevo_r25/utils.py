import logging

from django.conf import settings
from uw_mazevo.models import Status

from .models import MazevoRoomSpace, MazevoStatusMap
from .more_r25 import get_space_by_short_name


logger = logging.getLogger(__name__)


def update_get_space_ids(mazevo_rooms):
    """
    Get R25 space_ids for Mazevo Rooms.

    :param mazevo_rooms: A collection of uw_mazevo.models.Room
    :return: A dictionary of Room.id: space_id
    """
    for room in mazevo_rooms:
        room_space, _ = MazevoRoomSpace.objects.get_or_create(room_id=room.id)
        if room_space.space_id is None:
            if room.description.startswith("_"):
                logger.info("Skipping room {}".format(room.description))
                room_space.save()
                continue
            try:
                space = get_space_by_short_name(room.description)
                room_space.space_id = space.space_id
                room_space.save()
            except Exception:
                logger.warning("No R25 space found for {}".format(room.description))

    return MazevoRoomSpace.objects.in_bulk()


def update_get_status_map(mazevo_statuses):
    """
    Get the updated map of Mazevo statuses to actions and event types.
    """
    for status in mazevo_statuses:
        statusmap, _ = MazevoStatusMap.objects.get_or_create(status_id=status.id)
        if statusmap.action is None:
            if status.status_type == Status.STATUS_TYPE_BLOCKS_SPACE:
                statusmap.action = MazevoStatusMap.ACTION_ADD
            else:
                statusmap.action = MazevoStatusMap.ACTION_REMOVE
        if statusmap.event_type_id is None:
            statusmap.event_type_id = settings.MAZEVO_R25_EVENTTYPE_DEFAULT
        statusmap.save()

    return MazevoStatusMap.objects.in_bulk()
