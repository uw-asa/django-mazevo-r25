import logging

from django.conf import settings
from ems_client.service import Service
from lxml import etree
from restclients_core.exceptions import DataFailureException
from uw_r25 import nsmap, get_resource
from uw_r25.events import get_event_by_alien_id
from uw_r25.models import Event, Reservation, Space

from .more_r25 import put_resource, update_event


logger = logging.getLogger(__name__)


def bookings_and_reservations(params):
    search = {
        'start_date': params.get('StartDate'),
        'end_date': params.get('EndDate')
    }
    _ems = Service()

    event_data = []

    if not (search['start_date'] and search['end_date']):
        return None

    space_ids = update_get_space_ids(_ems.get_all_rooms())

    statuses = _ems.get_statuses()
    # search['statuses'] = [status.id for status in statuses
    #                       if (status.status_type_id ==
    #                           status.STATUS_TYPE_BOOKED_SPACE)]

    ems_bookings = _ems.get_bookings(**search)

    ems_reservation_ids = []

    # build reservations
    for b in ems_bookings:

        if b.reservation_id not in ems_reservation_ids:
            ems_reservation_ids.append(b.reservation_id)

        for status in statuses:
            if status.id == b.status_id:
                b.status = status
                continue

        event = {
            'room': b.room_description,
            'room_name': b.dv_room,
            'event_name': b.event_name,
            'start_time': b.time_booking_start.isoformat(),
            'end_time': b.time_booking_end.isoformat(),
            'booking_id': b.id,
            'reservation_id': b.reservation_id,
            'schedulable': True,
            'r25_space_id': None,
            'r25_event_id': None,
            'r25_alien_uid': "AT_EMS_RSRV_%s" % b.reservation_id,
            'r25_profile_name': "AT_EMS_BOOK_%s" % b.id,
            'r25_reservation_id': None,
            'synchronized': None,
        }

        if b.room_id in space_ids:
            event['r25_space_id'] = space_ids[b.room_id]
        else:
            event['schedulable'] = False

        if event:
            event_data.append(event)

    mash_in_r25_reservations(event_data, params)

    return event_data


def mash_in_r25_reservations(event_data, params):
    # mash in matching R25 reservations

    for e in event_data:
        try:
            r25_event = get_event_by_alien_id(e['r25_alien_uid'])
        except DataFailureException:
            # No R25 event matching this EMS event
            continue

        e['r25_event_id'] = r25_event.event_id
        for res in r25_event.reservations:
            if res.profile_name == e['r25_profile_name']:
                e['r25_reservation_id'] = res.reservation_id
                e['synchronized'] = (
                    e['start_time'] == res.start_datetime and
                    e['end_time'] == res.end_datetime and
                    e['r25_space_id'] == (res.space_reservation.space_id
                                          if res.space_reservation is not None
                                          else None)
                )


def create_r25_reservation(event_data):
    # The event_data we take is mapped to a reservation (with its own profile)
    # on the R25 event

    r25_event = Event()
    r25_event.event_id = event_data['r25_event_id']
    r25_event.alien_uid = event_data['r25_alien_uid']
    r25_event.name = event_data['event_name']
    r25_event.title = event_data['event_name']
    r25_event.state = r25_event.CONFIRMED_STATE

    r25_event.binding_reservations = []
    r25_event.reservations = []

    r25_reservation = Reservation()
    r25_reservation.profile_name = event_data['r25_profile_name']
    r25_reservation.reservation_id = event_data['r25_reservation_id']
    r25_reservation.start_datetime = event_data['start_time']
    r25_reservation.end_datetime = event_data['end_time']
    r25_reservation.state = r25_reservation.STANDARD_STATE
    r25_reservation.space_reservation = Space()
    r25_reservation.space_reservation.space_id = event_data['r25_space_id']
    r25_event.reservations.append(r25_reservation)

    r25_event = update_event(r25_event)

    event_data['r25_event_id'] = r25_event.event_id
    for res in r25_event.reservations:
        if res.profile_name == event_data['r25_profile_name']:
            event_data['r25_reservation_id'] = res.reservation_id
            event_data['synchronized'] = (
                    event_data['start_time'] == res.start_datetime and
                    event_data['end_time'] == res.end_datetime and
                    event_data['r25_space_id'] == (
                        res.space_reservation.space_id
                        if res.space_reservation is not None
                        else None)
            )

    return event_data


def update_get_space_ids(ems_rooms):
    """
    Get R25 space_ids for EMS Rooms.

    :param ems_rooms: A collection of ems_client.models.Room
    :return: A dictionary of Room.id: space_id
    """
    space_ids = {}
    for room in ems_rooms:
        if room.active and room.external_reference is not None:
            space_ids[room.id] = room.external_reference

    # while we're here, update the R25 saved search that we'll use
    query_url = "space_search.xml?query_id=%s" % settings.EMS_R25_SPACE_QUERY

    r25_query_tree = get_resource(query_url)

    snode = r25_query_tree.xpath("r25:search", namespaces=nsmap)[0]
    snode.attrib['status'] = 'mod'

    snode = snode.xpath("r25:step", namespaces=nsmap)[0]
    snode.attrib['status'] = 'mod'

    query_modified = False

    found_space_ids = []
    step_param_nbr = -1
    for pnode in snode.xpath("r25:step_param", namespaces=nsmap):
        space_id = pnode.xpath("r25:space_id", namespaces=nsmap)[0].text
        temp = int(pnode.xpath("r25:step_param_nbr", namespaces=nsmap)[0].text)

        found_space_ids.append(space_id)

        if temp > step_param_nbr:
            step_param_nbr = temp

        if space_id not in space_ids.values():
            pnode.attrib['status'] = 'del'
            query_modified = True

    for space_id in space_ids.values():
        if space_id in found_space_ids:
            continue
        step_param_nbr += 1
        param = etree.Element("{%s}step_param" % nsmap['r25'],
                              attrib={'status': 'new'})
        node = etree.Element("{%s}step_param_nbr" % nsmap['r25'])
        node.text = str(step_param_nbr)
        param.append(node)
        node = etree.Element("{%s}space_id" % nsmap['r25'])
        node.text = space_id
        param.append(node)
        snode.append(param)
        query_modified = True

    if query_modified:
        put_resource(query_url, etree.tostring(r25_query_tree))

    return space_ids
