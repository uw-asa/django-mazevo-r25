import datetime
import logging
import re

from django.core.management.base import BaseCommand, CommandError
from ems_client.models import Booking, Status
from ems_client.service import Service
from restclients_core.exceptions import DataFailureException
from uw_r25.events import get_event_by_alien_id, get_event_by_id
from uw_r25.models import Event, Reservation, Space

from ems_r25.more_r25 import delete_event, update_event, R25MessageException
from ems_r25.utils import update_get_space_ids


logger = logging.getLogger(__name__)


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
        'Class (charge)':       '432',  # 'UWS Continuing Education/Non-Cred...
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


def r25_event_state(booking):
    return (Event.CONFIRMED_STATE
            if booking.status_type_id == Status.STATUS_TYPE_BOOKED_SPACE
            else Event.CANCELLED_STATE)


Booking.r25_evtype_id = r25_event_type_id
Booking.r25_event_state = r25_event_state


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

        # parser.add_argument(
        #     '-c',
        #     '--claim',
        #     action='store_true',
        #     help='Try to claim conflicting R25 Events (requires --update)',
        # )

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
        start_date = options['start'] or datetime.date.today().isoformat()
        end_date = options['end'] or (
                datetime.datetime.strptime(start_date, "%Y-%m-%d") +
                datetime.timedelta(days=7)
        ).date().isoformat()

        _ems = Service()

        space_ids = update_get_space_ids(_ems.get_all_rooms())

        bookings = _ems.get_bookings(start_date=start_date, end_date=end_date)

        ems_reservations = {}
        for booking in bookings:
            if booking.event_type_description == 'Class (import)':
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
            logger.debug("Processing EMS Reservation %d" % ems_res_id)

            r25_alien_uid = "AT_EMS_RSRV_%s" % ems_res_id

            r25_event = None
            try:
                r25_event = get_event_by_alien_id(r25_alien_uid)
                logger.debug("\tFound R25 event %s: '%s'" %
                             (r25_event.event_id, r25_event.name))

            except DataFailureException:
                # No R25 event matching this EMS event
                pass

            if options['delete']:
                if r25_event:
                    logger.debug("\tDeleting!")
                    delete_event(r25_event.event_id)
                else:
                    logger.debug("\tNothing to delete.")
                continue

            if r25_event is None:
                r25_event = Event()
                r25_event.alien_uid = r25_alien_uid
                r25_event.reservations = []

            r25_event.name = ems_reservation.event_name
            r25_event.title = ems_reservation.event_name
            # r25_event.event_type_id = ems_reservation.r25_evtype_id()
            r25_event.state = ems_reservation.r25_event_state()

            ems_bookings = ems_reservation.bookings
            for ems_bk_id in ems_bookings:
                ems_booking = ems_bookings[ems_bk_id]

                logger.debug("\tProcessing EMS Booking %d: '%s'" %
                             (ems_bk_id, ems_booking.event_name))

                r25_profile_name = "AT_EMS_BOOK_%s" % ems_bk_id

                r25_res = None
                for r in r25_event.reservations:
                    if r.profile_name == r25_profile_name:
                        logger.debug(
                            "\t\tFound R25 reservation/profile %s: '%s'" %
                            (r.reservation_id, r.profile_name))
                        r25_res = r
                        break

                if (ems_booking.status_type_id ==
                        Status.STATUS_TYPE_BOOKED_SPACE and
                        ems_booking.room_id in space_ids and
                        ems_booking.r25_evtype_id()):

                    # We want a reservation. Create if necessary.
                    if r25_res is None:
                        r25_res = Reservation()
                        r25_res.profile_name = r25_profile_name
                        r25_res.space_reservation = None
                        r25_event.reservations.append(r25_res)

                    r25_res.start_datetime = \
                        ems_booking.time_booking_start.isoformat()
                    r25_res.end_datetime = \
                        ems_booking.time_booking_end.isoformat()
                    r25_res.state = r25_res.STANDARD_STATE
                    if r25_res.space_reservation is None:
                        r25_res.space_reservation = Space()

                    r25_res.space_reservation.space_id = space_ids[
                        ems_booking.room_id]

                elif r25_res is not None:
                    # Cancel this unwanted r25 reservation
                    r25_res.state = r25_res.CANCELLED_STATE
                    r25_res.space_reservation = None

            if not r25_event.reservations:
                logger.debug("\tevent has no existing reservations and no "
                             "wanted new reservations")
                continue

            if not options['update']:
                continue

            try:
                logger.debug("\tUpdating event")
                updated = update_event(r25_event)

            except R25MessageException as ex:
                while ex:
                    if ex.msg_id == 'EV_I_SPACECON':
                        logger.warning("Conflict: %s" % ex.text)
                        # if options['claim']:
                        #     logger.debug(
                        #         "\t\t\tTrying to claim existing event")
                        #     match = re.match(
                        #         r"Space (.+) unavailable due to \[rsrv\] "
                        #         r"conflict with (.+) \[(?P<event_id>\d+)\]",
                        #         ex.text)
                        #     if not match:
                        #         raise CommandError("Unrecognized conflict "
                        #                            "message format")
                        #     event_id = match.group('event_id')
                        #     ev = get_event_by_id(event_id)
                        #     matched = False
                        #     for bkid in ems_bookings:
                        #         name = ems_bookings[bkid].event_name.lower()
                        #         if ev.name.lower() == name[:len(ev.name)]:
                        #             matched = True
                        #             break
                        #
                        #         if (ev.title and ev.title.lower() ==
                        #                 name[:len(ev.title)]):
                        #             matched = True
                        #             break
                        #
                        #     if matched:
                        #         logger.debug(
                        #             "\t\t\tReleasing our created event")
                        #         r25_event.alien_uid = None
                        #         r25_event.reservations = []
                        #         update_event(r25_event)
                        #
                        #         logger.debug(
                        #             "\t\t\tClaiming the existing event")
                        #         ev.alien_uid = r25_alien_uid
                        #         update_event(ev)
                        # else:
                        #     raise CommandError("Unresolved conflict")

                    elif ex.msg_id == 'EV_I_SPACEREQ':
                        raise CommandError("Space not booked: %s" % ex.text)

                    else:
                        raise CommandError(ex)

                    ex = ex.next_msg
