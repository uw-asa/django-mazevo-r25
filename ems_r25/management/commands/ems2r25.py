import datetime
import re

from django.core.management.base import BaseCommand, CommandError
from ems_client.models import Status
from ems_client.service import Service
from restclients_core.exceptions import DataFailureException
from uw_r25.events import get_event_by_alien_id, get_event_by_id
from uw_r25.models import Event, Reservation, Space

from ems_r25.more_r25 import update_event, R25MessageException
from ems_r25.utils import update_get_space_ids


class Command(BaseCommand):
    help = 'adds or updates R25 events with events from EMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '-s',
            '--start',
            help='Start date',
        )
        parser.add_argument(
            '-e',
            '--end',
            help='End date',
        )

        parser.add_argument(
            '-c',
            '--claim',
            action='store_true',
            help='Try to claim conflicting R25 Events',
        )

    def handle(self, *args, **options):
        search = {
            'start_date':
                options['start'] or datetime.date.today().isoformat(),
            'end_date': options['end'] or datetime.date.today().isoformat(),
        }
        _ems = Service()

        space_ids = update_get_space_ids(_ems.get_all_rooms())

        bookings = _ems.get_bookings(**search)

        ems_reservations = {}
        for booking in bookings:
            if booking.room_id not in space_ids:
                # Room not in R25, skip it
                continue

            if booking.event_type_description == 'Class (import)':
                # Don't try to sync academic import
                continue

            if booking.reservation_id not in ems_reservations:
                ems_reservations[booking.reservation_id] = {'bookings': {}}
            ems_reservations[
                booking.reservation_id]['bookings'][booking.id] = booking

        for ems_res_id in ems_reservations:
            print "Processing EMS Reservation %d" % ems_res_id

            r25_alien_uid = "AT_EMS_RSRV_%s" % ems_res_id
            ems_bookings = ems_reservations[ems_res_id]['bookings']

            try:
                r25_event = get_event_by_alien_id(r25_alien_uid)
                print "\tFound R25 event %s: '%s'" % (
                    r25_event.event_id, r25_event.name)

            except DataFailureException:
                # No R25 event matching this EMS event
                print "\tCreating new R25 event"
                r25_event = Event()
                r25_event.alien_uid = r25_alien_uid
                r25_event.reservations = []

            for ems_bk_id in ems_bookings:
                ems_booking = ems_bookings[ems_bk_id]

                print "\tProcessing EMS Booking %d: '%s'" % (
                    ems_bk_id, ems_booking.event_name)

                r25_profile_name = "AT_EMS_BOOK_%s" % ems_bk_id

                r25_res = None
                for r in r25_event.reservations:
                    if r.profile_name == r25_profile_name:
                        print "\t\tFound R25 reservation/profile %s: '%s'" % (
                            r.reservation_id, r.profile_name)
                        r25_res = r
                        break

                if r25_res is None:
                    print "\t\tCreating new R25 reservation/profile"
                    r25_res = Reservation()
                    r25_res.profile_name = r25_profile_name
                    r25_res.space_reservation = None
                    r25_event.reservations.append(r25_res)

                r25_res.start_datetime = \
                    ems_booking.time_booking_start.isoformat()
                r25_res.end_datetime = ems_booking.time_booking_end.isoformat()
                r25_res.state = (Reservation.STANDARD_STATE
                                 if ems_booking.status_type_id ==
                                 Status.STATUS_TYPE_BOOKED_SPACE
                                 else Reservation.CANCELLED_STATE)
                if ems_booking.room_id in space_ids:
                    if r25_res.space_reservation is None:
                        r25_res.space_reservation = Space()

                    r25_res.space_reservation.space_id = space_ids[
                        ems_booking.room_id]
                else:
                    r25_res.space_reservation = None

            try:
                print "\tUpdating event"
                updated = update_event(r25_event)

            except R25MessageException as ex:
                while ex:
                    if ex.msg_id == 'EV_I_SPACECON':
                        print "\t\tConflict: %s" % ex.text
                        if options['claim']:
                            print "\t\t\tTrying to claim existing event"
                            match = re.match(
                                "Space (.+) unavailable due to \[rsrv\] "
                                "conflict with (.+) \[(?P<event_id>\d+)\]",
                                ex.text)
                            if not match:
                                raise Exception("didn't match message text")
                            event_id = match.group('event_id')
                            ev = get_event_by_id(event_id)
                            matched = False
                            for bkid in ems_bookings:
                                name = ems_bookings[bkid].event_name.lower()
                                if ev.name.lower() == name[:len(ev.name)]:
                                    matched = True
                                    break

                                if (ev.title and ev.title.lower() ==
                                        name[:len(ev.title)]):
                                    matched = True
                                    break

                            if matched:
                                print "\t\t\tReleasing our created event"
                                r25_event.alien_uid = None
                                r25_event.reservations = []
                                update_event(r25_event)

                                print "\t\t\tClaiming the existing event"
                                ev.alien_uid = r25_alien_uid
                                update_event(ev)


                    else:
                        print ex

                    ex = ex.next_msg

            # # If not booked space, no need to create in R25
            # if e['status_type'] != Status.STATUS_TYPE_BOOKED_SPACE:
            #     e['synchronized'] = True
            #
            # continue
