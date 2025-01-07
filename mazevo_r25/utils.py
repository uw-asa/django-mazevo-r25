import logging

from .models import MazevoRoomSpace, MazevoStatusMap
from .more_r25 import (Object, get_space_by_short_name, add_favorite, delete_favorite,
                       get_favorites)


logger = logging.getLogger(__name__)


def update_get_space_ids(mazevo_rooms):
    """
    Get R25 space_ids for Mazevo Rooms.

    :param mazevo_rooms: A collection of uw_mazevo.models.Room
    :return: A dictionary of Room.id: space_id
    """

    # get current favorites
    favorite_space_ids = list(get_favorites(Object.SPACE_TYPE).keys())

    for room in mazevo_rooms:
        room_space, _ = MazevoRoomSpace.objects.get_or_create(room_id=room.id)
        if room_space.space_id is None:
            if room.description.startswith("__"):
                logger.info("Skipping room {}".format(room.description))
                continue
            try:
                space = get_space_by_short_name(room.description)
                room_space.space_id = space.space_id
                room_space.save()
            except Exception:
                logger.warning("No R25 space found for {}".format(room.description))
                continue

        if room_space.space_id in favorite_space_ids:
            # reduce the list so we can remove any leftovers
            favorite_space_ids.remove(room_space.space_id)
        else:
            # make the space a favorite
            add_favorite(Object.SPACE_TYPE, room_space.space_id)

    # remove old spaces from favorites
    for space_id in favorite_space_ids:
        delete_favorite(Object.SPACE_TYPE, space_id)

    return MazevoRoomSpace.objects.in_bulk()


def update_get_status_map(mazevo_statuses):
    """
    Get the updated map of Mazevo statuses to actions and event types.
    """
    for status in mazevo_statuses:
        statusmap, _ = MazevoStatusMap.objects.get_or_create(status_id=status.id)
        if statusmap.event_type_id is None:
            statusmap.event_type_id = settings.MAZEVO_R25_EVENTTYPE_DEFAULT
            statusmap.save()

    return MazevoStatusMap.objects.in_bulk()
