import logging
from urllib.parse import quote

from uw_r25 import get_resource
from uw_r25.spaces import spaces_from_xml

from .models import MazevoRoomSpace
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
            if room.description.startswith('_'):
                continue
            try:
                space = get_space_by_short_name(room.description)
                room_space.space_id = space.space_id
                room_space.save()
            except Exception as ex:
                logger.warning("Error retrieving R25 space %s: %s" % (room.description, ex))
            
    # return MazevoRoomSpace.objects.exclude(space_id__exact=None).in_bulk()
    return MazevoRoomSpace.objects.in_bulk()
