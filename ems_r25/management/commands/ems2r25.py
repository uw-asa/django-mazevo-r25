import datetime
import re

from django.core.management.base import BaseCommand, CommandError
from ems_client.models import Booking, Status
from ems_client.service import Service
from restclients_core.exceptions import DataFailureException
from uw_r25.events import get_event_by_alien_id, get_event_by_id
from uw_r25.models import Event, Reservation, Space

from ems_r25.more_r25 import delete_event, update_event, R25MessageException
from ems_r25.utils import update_get_space_ids



def r25_event_type_id(booking):
    """map EMS event type to R25 event type id"""

    if booking.event_type_description in [
        None,
        'Blackout',
        'Class (import)',
    ]:  # Do not import
        return None

    event_type_map = {
        'Breakfast':            '395',  # 'Meal Service'
        'Class (charge)':       '432',  # 'UWS Continuing Education/Non-Credit..
        'Class (no charge)':    '412',  # 'Meeting - Class'
        'Class Review Session': '430',  # 'UWS Course Breakout/Review'
        'Concert/Performance':  '397',  # 'Concert/Performance'
        'Conference':           '402',  # 'Conference'
        'Dinner':               '395',  # 'Meal Service'
        'Exam/Test':            '405',  # 'Examination/Test'
        'Fair':                 '406',  # 'Fair'
        'Film Showing':         '408',  # 'Film (Showing)'
        'Graduation/Commencement': '409',  # 'Ceremony'
        'Lecture':              '400',  # 'Guest Speaker/Lecture/Seminar'
        'Luncheon':             '395',  # 'Meal Service'
        'Maintenance':          '416',  # 'Repair/Maintenance'
        'Meeting':              '411',  # 'Meeting'
        'Orientation':          '415',  # 'Orientation'
        'Other':                '433',  # 'UWS Event'
        'Poster Session':       '392',  # 'Exhibit'
        'Reception':            '417',  # 'Reception'
        'Seminar':              '400',  # 'Guest Speaker/Lecture/Seminar'
        'Symposium':            '402',  # 'Conference'
    }
    return event_type_map.get(booking.event_type_description,
                              '433')    # default to 'UWS Event'


Booking.r25_evtype_id = r25_event_type_id


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
            help='Try to claim conflicting R25 Events (requires --update)',
        )

        parser.add_argument(
            '-d',
            '--delete',
            action='store_true',
            help='Delete matched R25 Events',
        )

        parser.add_argument(
            '-u',
            '--update',
            action='store_true',
            help='Update R25 Events',
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

            if not booking.r25_evtype_id():
                continue

            if booking.reservation_id not in ems_reservations:
                # Use data from first booking as reservation data.
                # FIXME: we need a way to grab actual EMS Reservation data
                # FIXME: instead of just Bookings
                ems_reservations[booking.reservation_id] = booking
                ems_reservations[booking.reservation_id].bookings = {}
            ems_reservations[
                booking.reservation_id].bookings[booking.id] = booking

        for ems_res_id in ems_reservations:
            ems_reservation = ems_reservations[ems_res_id]
            print "Processing EMS Reservation %d" % ems_res_id

            r25_alien_uid = "AT_EMS_RSRV_%s" % ems_res_id

            r25_event = None
            try:
                r25_event = get_event_by_alien_id(r25_alien_uid)
                print "\tFound R25 event %s: '%s'" % (
                    r25_event.event_id, r25_event.name)

            except DataFailureException:
                # No R25 event matching this EMS event
                pass

            if options['delete']:
                if r25_event:
                    print "\tDeleting!"
                    delete_event(r25_event.event_id)
                else:
                    print "\tNothing to delete."
                continue

            if r25_event is None:
                r25_event = Event()
                r25_event.alien_uid = r25_alien_uid
                r25_event.reservations = []

            r25_event.name = ems_reservation.event_name
            r25_event.title = ems_reservation.event_name
            r25_event.event_type_id = ems_reservation.r25_evtype_id()

            ems_bookings = ems_reservation.bookings
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

            if not options['update']:
                continue

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
