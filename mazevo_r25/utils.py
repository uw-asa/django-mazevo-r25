import logging
from urllib.parse import quote

from uw_r25 import get_resource
from uw_r25.spaces import spaces_from_xml

from .models import MazevoRoomSpace


logger = logging.getLogger(__name__)


def update_get_space_ids(mazevo_rooms):
    """
    Get R25 space_ids for Mazevo Rooms.

    :param mazevo_rooms: A collection of uw_mazevo.models.Room
    :return: A dictionary of Room.id: space_id
    """
    space_ids = {}

    for room in mazevo_rooms:
        logger.info("Mazevo room %s" % room.description)
        try:
            url = "spaces.xml"
            url += "?short_name={}".format(quote(room.description))
            space = spaces_from_xml(get_resource(url))[0]
        except Exception as ex:
            logger.warning("R25 error while retrieving space %s: %s" % (room.description, ex))

        space_ids[room.id] = space.space_id

    return MazevoRoomSpace.objects.in_bulk()
