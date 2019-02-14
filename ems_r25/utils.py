import logging

from ems_client.service import Service
from uw_r25 import nsmap
from uw_r25.reservations import get_reservations

from .more_r25 import create_new_event, update_event


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

    rooms = _ems.get_all_rooms()
    space_ids = {room.id: room.external_reference for room in rooms
                 if room.external_reference is not None}

    ems_bookings = _ems.get_bookings(**search)

    ems_reservation_ids = []

    # build reservations
    for b in ems_bookings:

        if b.reservation_id not in ems_reservation_ids:
            ems_reservation_ids.append(b.reservation_id)

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
            'r25_event_name': None,
            'r25_reservation_id': None,
        }

        if b.room_id in space_ids:
            event['r25_space_id'] = space_ids[b.room_id]
        else:
            event['schedulable'] = False

        if event:
            event_data.append(event)

    alien_uids = ["AT_reservation_{}".format(r_id)
                  for r_id in ems_reservation_ids]

    mash_in_r25_reservations(event_data, params,
                             ','.join(sorted(space_ids.values())),
                             ','.join(alien_uids))

    return event_data


def mash_in_r25_reservations(event_data, params, space_ids, alien_uids):
    # mash in R25 reservation schedule
    search = {
        'space_id': space_ids,
        # 'alien_uids': alien_uids,
        'start_dt': params.get('StartDate'),
        'end_dt': params.get('EndDate'),
    }

    r25_reservations = get_reservations(**search)
    for r in r25_reservations if r25_reservations else []:
        for e in event_data:
            if (r.space_reservation.space_id == e['r25_space_id'] and
                    r.start_datetime == e['start_time'] and
                    r.end_datetime == e['end_time']):
                e['r25_reservation_id'] = r.reservation_id
                e['r25_event_id'] = r.event_id
                e['r25_event_name'] = r.event_name


def create_r25_reservation(event_data):
    # TODO: check for existing R25 Event based on our EMS Reservation

    # if no event, create blank
    event_tree = create_new_event()

    enode = event_tree.xpath("r25:event", namespaces=nsmap)[0]
    event_id = enode.xpath("r25:event_id", namespaces=nsmap)[0].text

    enode.attrib['status'] = 'mod'

    element = enode.xpath("r25:event_name", namespaces=nsmap)[0]
    element.text = event_data['event_name']

    update_event(event_id, event_tree)
