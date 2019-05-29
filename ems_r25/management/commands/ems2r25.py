import datetime
import logging
import re

from django.core.management.base import BaseCommand, CommandError
from ems_client.models import Booking, Status
from ems_client.service import Service
from restclients_core.exceptions import DataFailureException
from uw_r25.events import get_event_by_alien_id
from uw_r25.models import Event, Reservation, Space

from ems_r25.more_r25 import delete_event, update_event, R25MessageException
from ems_r25.utils import update_get_space_ids


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'adds or updates R25 events with events from EMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '-s',
            '--start',
            help="Start of date range. Default is today, or yesterday if "
                 "using --changed.",
        )
        parser.add_argument(
            '-e',
            '--end',
            help="End of date range. Default is START+7 days, or today if "
                 "using --changed.",
        )

        parser.add_argument(
            '-c',
            '--changed',
            action='store_true',
            help="Get Bookings that have changed within date range. Includes "
                 "Bookings where the Reservation has changed, even if the "
                 "Booking has not.",
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
        if options['changed']:
            start_date = options['start'] or (
                    datetime.date.today() -
                    datetime.timedelta(days=1)
            ).isoformat()
            end_date = options['end'] or datetime.date.today().isoformat()

        else:
            start_date = options['start'] or datetime.date.today().isoformat()
            end_date = options['end'] or (
                    datetime.datetime.strptime(start_date, "%Y-%m-%d") +
                    datetime.timedelta(days=7)
            ).date().isoformat()

        _ems = Service()

        space_ids = update_get_space_ids(_ems.get_all_rooms())

        # Get all bookings in range, regardless of room, status, or event type.
        # We do this because a now-unwanted booking might already have been
        # Created in R25, and we need to cancel it there.
        bookings = _ems.get_changed_bookings(
            start_date=start_date, end_date=end_date
        ) if options['changed'] else _ems.get_bookings(
            start_date=start_date, end_date=end_date
        )

        ems_reservations = {}
        for booking in bookings:
            # The vast majority of unwanted bookings are academic import.
            # Skip them because we don't want to sync them, and there should
            # never be a case where one was already synced.
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

            # alien_uid is how we tie EMS Reservation to R25 Event.
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

            r25_event.name = ems_reservation.event_name[:40].strip()
            r25_event.title = ems_reservation.event_name.strip()
            r25_event.state = r25_event.CONFIRMED_STATE

            ems_bookings = ems_reservation.bookings
            for ems_bk_id in ems_bookings:
                ems_booking = ems_bookings[ems_bk_id]

                logger.debug("\tProcessing EMS Booking %d: '%s'" %
                             (ems_bk_id, ems_booking.event_name))
                logger.debug("\t\tStatusType: %s, EventType: %s, space_id: %s" %
                             (dict(Status.STATUS_TYPE_CHOICES)[
                                 ems_booking.status_type_id],
                              ems_booking.event_type_description,
                              space_ids.get(ems_booking.room_id)))
                logger.debug("\t\tStart: %s, End: %s, Changed: %s" % (
                    ems_booking.time_booking_start.isoformat(),
                    ems_booking.time_booking_end.isoformat(),
                    ems_booking.date_changed.isoformat()))

                # profile_name is how we tie EMS Booking to R25 Reservation.
                # We only use the most basic type of profile, so profile to
                # reservation is a 1:1 relationship.
                r25_profile_name = "AT_EMS_BOOK_%s" % ems_bk_id

                r25_res = None
                for r in r25_event.reservations:
                    if r.profile_name == r25_profile_name:
                        logger.debug(
                            "\t\tFound R25 reservation/profile %s: '%s'" %
                            (r.reservation_id, r.profile_name))
                        r25_res = r
                        break

                # does this Booking belong in R25?
                if (ems_booking.status_type_id ==
                        Status.STATUS_TYPE_BOOKED_SPACE and
                        ems_booking.room_id in space_ids and
                        ems_booking.event_type_description not in[
                            'Blackout',
                            'Class (import)',
                        ]):

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

                # does not belong. Does one already exist?
                elif r25_res is not None:
                    # Cancel this unwanted r25 reservation
                    r25_res.state = r25_res.CANCELLED_STATE
                    r25_res.space_reservation = None

            # if this R25 Event is empty, there's nothing to do
            if not r25_event.reservations:
                logger.debug("\tNo existing R25 reservations and no wanted "
                             "new R25 reservations")
                continue

            # by default, don't actually make changes
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
