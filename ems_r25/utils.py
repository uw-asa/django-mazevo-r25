import logging

from django.conf import settings
from ems_client.service import Service
from lxml import etree
from uw_r25 import nsmap, get_resource
from uw_r25.events import get_events, events_from_xml

from .more_r25 import (put_resource, get_event_by_id_xml,
                       create_new_event, update_event, get_reservations_multi)


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
    search['statuses'] = [status.id for status in statuses
                          if (status.status_type_id ==
                              status.STATUS_TYPE_BOOKED_SPACE)]

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
            'event_name': "%s.%s" % (b.status.description, b.event_name),
            'start_time': b.time_booking_start.isoformat(),
            'end_time': b.time_booking_end.isoformat(),
            'booking_id': b.id,
            'reservation_id': b.reservation_id,
            'schedulable': True,
            'r25_space_id': None,
            'r25_event_id': None,
            'r25_event_name': "AT_EMS_RSRV_%s" % b.reservation_id,
            'r25_profile_name': "AT_EMS_BOOK_%s" % b.id,
            'r25_reservation_id': None,
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
    # mash in R25 reservation schedule
    search = {
        'space_query_id': settings.EMS_R25_SPACE_QUERY,
        'start_dt': params.get('StartDate'),
        'end_dt': params.get('EndDate'),
    }

    for e in event_data:
        try:
            r25_event = get_events(event_name=e['r25_event_name'])[0]
        except IndexError:
            continue
        e['r25_event_id'] = r25_event.event_id
        for res in r25_event.reservations:
            if res.profile_name == e['r25_profile_name']:
                e['r25_reservation_id'] = res.reservation_id

    return

    # R25 reservations can have multiple spaces on a single reservation_id,
    # get_reservations can't handle that.
    # Are EMS Bookings analogous?
    r25_reservations = get_reservations_multi(**search)
    for r in r25_reservations if r25_reservations else []:
        for s in r.space_reservations:
            for e in event_data:
                if (s.space_id == e['r25_space_id'] and
                        r.start_datetime == e['start_time'] and
                        r.end_datetime == e['end_time']):
                    e['r25_reservation_id'] = r.reservation_id
                    e['r25_event_id'] = r.event_id
                    e['r25_event_name'] = r.event_name


def create_r25_reservation(event_data):
    if event_data['r25_event_id']:
        event_tree = get_event_by_id_xml(event_data['r25_event_id'])
    else:
        event_tree = create_r25_event(event_data)

    # enode = event_tree.xpath("r25:event", namespaces=nsmap)[0]

    # Add reservation details (date and time) and space_reservation(s)
    # node = enode.xpath("r25:profile", namespaces=nsmap)[0]
    # node.attrib['status'] = 'mod'
    # node.xpath("r25:profile_name", namespaces=nsmap)[0].text = \
    #     event_data['r25_profile_name']

    # node = node.xpath("r25:reservation", namespaces=nsmap)[0]
    # node.attrib['status'] = 'mod'
    #
    # node.xpath("r25:reservation_start_dt", namespaces=nsmap)[0].text = \
    #     event_data['start_time']
    # node.xpath("r25:reservation_end_dt", namespaces=nsmap)[0].text = \
    #     event_data['end_time']

    # node = node.xpath("r25:space_reservation", namespaces=nsmap)[0]
    # node.attrib['status'] = 'mod'
    #
    # node.xpath("r25:space_id", namespaces=nsmap)[0].text = \
    #     event_data['r25_space_id']

    r25_event = events_from_xml(update_event(event_tree))[0]

    for res in r25_event.reservations:
        if res.profile_name == event_data['r25_profile_name']:
            event_data['r25_reservation_id'] = res.reservation_id

    return event_data


def create_r25_event(event_data):
    event_tree = create_new_event()

    enode = event_tree.xpath("r25:event", namespaces=nsmap)[0]
    event_data['r25_event_id'] = \
        enode.xpath("r25:event_id", namespaces=nsmap)[0].text

    # enode.attrib['status'] = 'mod'

    enode.xpath("r25:event_name", namespaces=nsmap)[0].text = \
        event_data['r25_event_name']
    enode.xpath("r25:event_title", namespaces=nsmap)[0].text = \
        event_data['event_name']

    element = enode.xpath("r25:node_type", namespaces=nsmap)[0]
    element.text = 'E'

    # Required information:
    # Event Name
    # Event Type
    # Primary Organization

    # element = enode.xpath("r25:event_name", namespaces=nsmap)[0]
    # element.text = event_data['event_name']

    element = enode.xpath("r25:event_type_id", namespaces=nsmap)[0]
    element.text = "402"

    onode = enode.xpath("r25:organization", namespaces=nsmap)[0]
    element = onode.xpath("r25:organization_id", namespaces=nsmap)[0]
    element.text = "4211"
    # element = onode.xpath("r25:primary", namespaces=nsmap)[0]
    # element.text = "T"

    return update_event(event_tree)


def update_get_space_ids(ems_rooms):
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
