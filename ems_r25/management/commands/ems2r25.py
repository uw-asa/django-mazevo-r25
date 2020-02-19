import datetime
import logging
import re
import unicodedata

from dateutil.parser import parse
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ems_client.models import Status
from ems_client.service import Service
from urllib3.exceptions import HTTPError
from uw_r25.events import get_event_by_id, get_events
from uw_r25.models import Event, Reservation, Space

from ems_r25.more_r25 import (delete_event, update_event,
                              R25MessageException, R25ErrorException,
                              TooManyRequestsException
                              )
from ems_r25.utils import update_get_space_ids


logger = logging.getLogger('ems_r25')


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
            help="Get Bookings that have changed within date range.",
        )

        parser.add_argument(
            '-b',
            '--booking',
            help="Sync this specific EMS Booking",
        )

        parser.add_argument(
            '-r',
            '--reservation',
            help="Sync this specific EMS Reservation",
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
        verbosity = int(options['verbosity'])
        if verbosity == 0:
            logger.setLevel(logging.ERROR)
        elif verbosity == 1:  # default
            logger.setLevel(logging.WARNING)
        elif verbosity == 2:
            logger.setLevel(logging.INFO)
        elif verbosity == 3:
            logger.setLevel(logging.DEBUG)

        if options['changed']:
            if options['start']:
                start_date = parse(options['start']).date()
            else:
                start_date = datetime.date.today()
            if options['end']:
                end_date = parse(options['end']).date()
            else:
                end_date = datetime.date.today()

        else:
            if options['start']:
                start_date = parse(options['start']).date()
            else:
                start_date = datetime.date.today()
            if options['end'] == 'max':
                end_date = datetime.date.max
            elif options['end']:
                end_date = parse(options['end']).date()
            else:
                end_date = start_date + datetime.timedelta(days=7)

        _ems = Service()

        try:
            space_ids = update_get_space_ids(_ems.get_all_rooms())
        except R25ErrorException as ex:
            raise CommandError("Unable to update space search: %s" % ex)

        status_list = _ems.get_statuses()
        statuses = {}
        search_statuses = []
        for status in status_list:
            statuses[status.id] = status
            if status.description not in settings.EMS_R25_IGNORE_STATUSES:
                search_statuses.append(status.id)

        # Get all bookings in range, regardless of room, status, or event type.
        # We do this because a now-unwanted booking might already have been
        # Created in R25, and we need to cancel it there.
        if options['booking']:
            bookings = [_ems.get_booking(options['booking'])]
        elif options['reservation']:
            bookings = _ems.get_bookings2(
                reservation_id=options['reservation'],
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
        elif options['changed']:
            bookings = _ems.get_changed_bookings(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                statuses=search_statuses)
        else:
            bookings = _ems.get_bookings(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                statuses=search_statuses)

        ems_reservations = {}
        for booking in bookings:
            if booking.date_changed is None:
                # get_booking doesn't return date_changed...
                booking.date_changed = datetime.date.min

            if options['changed']:
                # Booking hasn't changed, EMS Reservation has...
                if (booking.date_changed.date() < start_date or
                        booking.date_changed.date() > end_date):
                    continue

            booking.status = statuses[booking.status_id]

            if booking.reservation_id not in ems_reservations:
                # Use data from first booking as reservation data.
                # FIXME: we need a way to grab actual EMS Reservation data
                # FIXME: instead of just Bookings
                ems_reservations[booking.reservation_id] = booking
                ems_reservations[booking.reservation_id].bookings = {}
            ems_reservations[
                booking.reservation_id].bookings[booking.id] = booking

            logger.debug("Processing EMS Booking %d: '%s'" %
                         (booking.id, booking.event_name))
            logger.debug("\tStatus: %s, space_id: %s" % (
                         (booking.status.description,
                          space_ids.get(booking.room_id))))
            logger.debug("\tStart: %s, End: %s, Changed: %s" % (
                booking.time_booking_start.isoformat(),
                booking.time_booking_end.isoformat(),
                booking.date_changed.isoformat()))

            r25_event = None
            try:
                events = get_events(starts_with="%d_" % booking.id,
                                    scope='extended',
                                    include='reservations')

                r25_event = events[0]

                if len(events) > 1:
                    logger.warning("\tFound multiple R25 events")
                    for event in events:
                        if event.reservations[0].space_reservation is None:
                            logger.warning("\tFound R25 event with no space "
                                           "reservation %s: %s" %
                                           (event.event_id, event.name))
                            if options['update']:
                                logger.debug("\tDeleting!")
                                delete_event(event.event_id)
                        else:
                            r25_event = event

                logger.debug("\tFound R25 event %s: '%s'" %
                             (r25_event.event_id, r25_event.name))

            except IndexError:
                # No R25 event matching this EMS Booking
                pass
            except HTTPError as ex:
                # Server timeout, etc
                self.stdout.write("HTTP Error retrieving R25 Event, skipping "
                                  "Booking %s: %s" % (booking.id, ex))
                continue

            if options['delete']:
                if r25_event:
                    logger.debug("\tDeleting!")
                    delete_event(r25_event.event_id)
                else:
                    logger.debug("\tNothing to delete.")
                continue

            wanted_booking = True
            if booking.status_type_id != Status.STATUS_TYPE_BOOKED_SPACE:
                wanted_booking = False
            elif booking.room_id not in space_ids:
                wanted_booking = False
            elif (booking.status.description in
                    settings.EMS_R25_REMOVE_STATUSES):
                wanted_booking = False
            elif (booking.status.description in
                    settings.EMS_R25_IGNORE_STATUSES):
                wanted_booking = False

            if r25_event is None:
                # Do we even want in r25?
                if not wanted_booking:
                    continue

                # Need to create r25 event
                r25_event = Event()
                r25_event.reservations = []

                r25_res = Reservation()
                r25_res.space_reservation = None
                r25_event.reservations.append(r25_res)

            event_name = booking.event_name
            if isinstance(event_name, unicode):
                event_name = unicodedata.normalize(
                    'NFKD', event_name).encode('ascii', 'ignore')

            r25_event.name = "%d_%s" % (
                booking.id, event_name[:30].strip().upper())
            r25_event.title = event_name.strip()
            r25_event.state = r25_event.CONFIRMED_STATE

            r25_res = r25_event.reservations[0]

            if wanted_booking:
                r25_res.start_datetime = \
                    booking.time_booking_start.isoformat()
                r25_res.end_datetime = \
                    booking.time_booking_end.isoformat()
                r25_res.state = r25_res.STANDARD_STATE
                if r25_res.space_reservation is None:
                    r25_res.space_reservation = Space()

                r25_res.space_reservation.space_id = space_ids[
                    booking.room_id]

            else:
                # Cancel this unwanted r25 event
                r25_event.state = r25_event.CANCELLED_STATE
                # r25_res.state = r25_res.CANCELLED_STATE
                # r25_res.space_reservation = None

            # by default, don't actually make changes
            if not options['update']:
                continue

            try:
                logger.debug("\tUpdating event")
                updated = update_event(r25_event)

            except R25MessageException as ex:
                while ex:
                    if ex.msg_id == 'EV_I_SPACECON':
                        logger.warning(
                            "Conflict while syncing EMS Booking %s: %s" %
                            (booking.id, ex.text))
                        match = re.search(r'\[(?P<event_id>\d+)\]', ex.text)
                        if match:
                            old_event = get_event_by_id(
                                match.group('event_id'))
                            logger.warning(
                                "Existing event: %s" % old_event.live_url())
                            logger.warning(
                                "Is blocking event: %s" % r25_event.live_url())

                    else:
                        logger.warning(
                            "R25 message while syncing EMS Booking %s to "
                            "R25 Event %s: %s" % (
                                booking.id,
                                r25_event.event_id, ex))

                    ex = ex.next_msg

            except R25ErrorException as ex:
                logger.warning(
                    "R25 error while syncing EMS Booking %s to R25 Event "
                    " %s: %s" % (booking.id,
                                 r25_event.event_id, ex))

            except HTTPError as ex:
                logger.warning(
                    "HTTP error while syncing EMS Booking %s to R25 Event "
                    " %s: %s" % (booking.id,
                                 r25_event.event_id, ex))

            except TooManyRequestsException:
                self.stdout.write(
                    "Too Many Requests while syncing EMS Booking %s to "
                    "R25 Event %s" % (booking.id,
                                      r25_event.event_id))
