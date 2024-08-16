import datetime
import logging
import re
import requests
import six
import sys
import unicodedata

from dateutil.parser import parse
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from lxml.etree import XMLSyntaxError
from restclients_core.exceptions import DataFailureException
from urllib3.exceptions import InsecureRequestWarning
from uw_mazevo.api import PublicConfiguration, PublicEvent
from uw_r25.events import get_event_by_id, get_events
from uw_r25.models import Event, Reservation, Space

from mazevo_r25.models import MazevoStatusMap
from mazevo_r25.more_r25 import (
    delete_event,
    update_event,
    R25MessageException,
    R25ErrorException,
    TooManyRequestsException,
)
from mazevo_r25.utils import update_get_space_ids, update_get_status_map


logger = logging.getLogger("mazevo_r25")


class Command(BaseCommand):
    help = "adds or updates R25 events with events from Mazevo"

    def set_logger(self, verbosity):
        """
        Set logger level based on verbosity option
        """
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if verbosity == 0:
            self.logger.setLevel(logging.WARN)
        elif verbosity == 1:  # default
            self.logger.setLevel(logging.INFO)
        elif verbosity > 1:
            self.logger.setLevel(logging.DEBUG)

        # verbosity 3: also enable all logging statements that reach the root
        # logger
        if verbosity > 2:
            logging.getLogger().setLevel(logging.DEBUG)

    def __init__(self, logger=None, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.logger = logger or logging.getLogger(__name__)

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--start",
            help="Start of date range. Default is today.",
        )
        parser.add_argument(
            "-e",
            "--end",
            help="End of date range. Default is START+7 days.",
        )

        parser.add_argument(
            "-c",
            "--changed",
            nargs="?",
            const="today",
            help="Get Bookings that have changed since date."
            " Default is today if no argument given.",
        )

        parser.add_argument(
            "-b",
            "--booking",
            help="Sync this specific Mazevo Booking",
        )

        parser.add_argument(
            "-r",
            "--event",
            help="Sync this specific Mazevo Event",
        )

        parser.add_argument(
            "-d",
            "--delete",
            action="store_true",
            help="Delete matched R25 Events",
        )

        parser.add_argument(
            "-u",
            "--update",
            action="store_true",
            help="Update R25 Events",
        )

    def handle(self, *args, **options):
        messages = []

        self.set_logger(options.get("verbosity"))

        if options["start"]:
            start_date = parse(options["start"]).date()
        else:
            start_date = datetime.date.today()
        if options["end"] == "max":
            end_date = datetime.date.max
        elif options["end"]:
            end_date = parse(options["end"]).date()
        else:
            end_date = start_date + datetime.timedelta(days=7)
        logger.info("Considering bookings from %s to %s" % (start_date, end_date))
        if options["changed"]:
            if options["changed"] == "today":
                changed_date = datetime.date.today()
            else:
                changed_date = parse(options["changed"]).date()
            logger.info("\tand changed since %s" % (changed_date))

        if settings.DEBUG:
            requests.urllib3.disable_warnings(InsecureRequestWarning)
        space_ids = update_get_space_ids(PublicConfiguration().get_rooms())

        status_list = PublicConfiguration().get_statuses()
        statuses = {}
        search_statuses = []
        for status in status_list:
            statuses[status.id] = status

        status_map = update_get_status_map(status_list)
        for id in status_map:
            if id not in statuses:
                logger.warning(
                    "Mapped status {} missing from Mazevo status list".format(id))
                continue
            if status_map[id].action != MazevoStatusMap.ACTION_IGNORE:
                search_statuses.append(id)
        logger.info(
            "Considering statuses %s"
            % ", ".join(statuses[status].description for status in search_statuses)
        )

        # Mazevo works best with full tz-aware datetimes
        start_date = datetime.datetime.combine(
            start_date, datetime.datetime.min.time()).astimezone()
        if not options["end"] == "max":
            end_date = datetime.datetime.combine(
                end_date, datetime.datetime.min.time()).astimezone()

        # Get all bookings in range, regardless of room, status, or event type.
        # We do this because a now-unwanted booking might already have been
        # Created in R25, and we need to cancel it there.
        if options["booking"]:
            logger.info("Looking for single booking %s" % options["booking"])
            try:
                bookings = PublicEvent().get_events_with_booking_details(
                    [options["booking"]])
            except IndexError:
                bookings = []
        # elif options["event"]:
        #     logger.info("Looking for event %s" % options["event"])
        #     bookings = get_bookings2(
        #         event_number=options["event"],
        #         start_date=start_date.isoformat(),
        #         end_date=end_date.isoformat(),
        #     )
        elif options["changed"]:
            logger.info("Looking for changed bookings")
            bookings = PublicEvent().get_events(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                statusIds=search_statuses,
                minDateChanged=changed_date.isoformat(),
            )
        else:
            logger.info("Looking for all bookings")
            bookings = PublicEvent().get_events(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                statusIds=search_statuses,
            )
        logger.info("Found %d bookings" % len(bookings))

        mazevo_events = {}
        current_num = 0
        for booking in bookings:
            current_num += 1

            booking.status = statuses[booking.status_id]
            booking.mapped_status = status_map[booking.status_id]
            booking.space_id = space_ids.get(booking.room_id).space_id

            if booking.event_number not in mazevo_events:
                # Use data from first booking as event data.
                # FIXME: we need a way to grab actual Mazevo Event data
                # FIXME: instead of just Bookings
                mazevo_events[booking.event_number] = booking
                mazevo_events[booking.event_number].bookings = {}
            mazevo_events[booking.event_number].bookings[booking.id] = booking

            logger.debug(
                "Processing Mazevo Booking %d/%d %d: '%s'"
                % (current_num, len(bookings), booking.id, booking.event_name)
            )
            logger.debug(
                "\tEvent: {}, Status: {}, room: {}, space_id: {}".format(
                    booking.event_number, booking.status.description, booking.room_description,
                    booking.space_id
                )
            )
            logger.debug(
                "\tStart: %s, End: %s, Changed: %s"
                % (
                    booking.date_time_start.isoformat(),
                    booking.date_time_end.isoformat(),
                    booking.date_changed.isoformat(),
                )
            )

            if booking.setup_minutes or booking.teardown_minutes:
                logger.debug(
                    "\tSetup Minutes: {}, Teardown Minutes: {}".format(
                        booking.setup_minutes, booking.teardown_minutes
                    )
                )

            r25_event = None
            try:
                events = get_events(
                    starts_with="%d_" % booking.id,
                    scope="extended",
                    include="reservations",
                )

                r25_event = events[0]

                if len(events) > 1:
                    logger.warning("\tFound multiple R25 events")
                    messages.append("\tFound multiple R25 events")
                    for event in events:
                        if event.reservations[0].space_reservation is None:
                            logger.warning(
                                "\tFound R25 event with no space "
                                "reservation %s: %s" % (event.event_id, event.name)
                            )
                            messages.append(
                                "\tFound R25 event with no space "
                                "reservation %s: %s" % (event.event_id, event.name)
                            )
                            if options["update"]:
                                logger.debug("\tDeleting!")
                                delete_event(event.event_id)
                        else:
                            r25_event = event

                logger.debug(
                    "\tFound R25 event %s: '%s'" % (r25_event.event_id, r25_event.name)
                )

            except IndexError:
                # No R25 event matching this Mazevo Booking
                logger.debug("\tNo R25 event found")
                pass
            except DataFailureException as ex:
                # Server timeout, etc
                self.stdout.write(
                    "Error retrieving R25 Event, skipping "
                    "Booking %s (%s): %s" % (booking.id, booking.event_number, ex)
                )
                messages.append(
                    "Error retrieving R25 Event, skipping "
                    "Booking %s (%s): %s" % (booking.id, booking.event_number, ex)
                )
                continue
            except XMLSyntaxError as ex:
                # Bad response from R25 server - usually means outage
                self.stdout.write(
                    "XML Error retrieving R25 Event, skipping "
                    "Booking %s (%s): %s" % (booking.id, booking.event_number, ex)
                )
                messages.append(
                    "XML Error retrieving R25 Event, skipping "
                    "Booking %s (%s): %s" % (booking.id, booking.event_number, ex)
                )
                continue

            if options["delete"]:
                if r25_event:
                    logger.debug("\tDeleting!")
                    delete_event(r25_event.event_id)
                else:
                    logger.debug("\tNothing to delete.")
                continue

            wanted_booking = True
            if booking.mapped_status.action == MazevoStatusMap.ACTION_REMOVE:
                wanted_booking = False
            elif booking.mapped_status.action == MazevoStatusMap.ACTION_IGNORE:
                wanted_booking = False
            elif booking.space_id is None:
                if not booking.room_description.startswith("__"):
                    logger.warning(
                        "No R25 space for Mazevo Booking %s (%s): %s"
                        % (booking.id, booking.event_number, booking.room_description)
                    )
                    messages.append(
                        "No R25 space for Mazevo Booking %s (%s): %s"
                        % (booking.id, booking.event_number, booking.room_description)
                    )
                wanted_booking = False

            if r25_event is None:
                # Do we even want in r25?
                if not wanted_booking:
                    logger.debug("\t\tGood")
                    continue

                # Need to create r25 event
                logger.debug("\t\tWill create")
                r25_event = Event()
                r25_event.reservations = []

                r25_res = Reservation()
                r25_res.space_reservation = None
                r25_event.reservations.append(r25_res)

            event_name = booking.event_name
            if isinstance(event_name, six.text_type):
                event_name = unicodedata.normalize("NFKD", event_name).encode(
                    "ascii", "ignore"
                )
                event_name = six.ensure_text(event_name)

            r25_event.name = "%d_%s" % (
                booking.id,
                event_name[:30].strip().upper(),
            )
            r25_event.title = event_name.strip()
            r25_event.state = r25_event.CONFIRMED_STATE
            if not booking.mapped_status.event_type_id == MazevoStatusMap.EVENT_TYPE_UNDEFINED:
                r25_event.event_type_id = booking.mapped_status.event_type_id
            r25_event.node_type = "E"
            r25_event.organization_id = settings.MAZEVO_R25_ORGANIZATION

            r25_res = r25_event.reservations[0]

            if wanted_booking:
                r25_res.start_datetime = booking.date_time_start.isoformat()
                r25_res.end_datetime = booking.date_time_end.isoformat()

                # calculate weird setup and takedown time format
                # P#DT##H##M
                days = booking.setup_minutes // 1440
                hours = booking.setup_minutes // 60 - days * 24
                minutes = booking.setup_minutes % 60
                if days or hours or minutes:
                    r25_res.setup_tm = "P"
                else:
                    r25_res.setup_tm = None
                if days:
                    r25_res.setup_tm += "{}D".format(days)
                if hours or minutes:
                    r25_res.setup_tm += "T"
                if hours:
                    r25_res.setup_tm += "{:02d}H".format(hours)
                if minutes:
                    r25_res.setup_tm += "{:02d}M".format(minutes)

                days = booking.teardown_minutes // 1440
                hours = booking.teardown_minutes // 60 - days * 24
                minutes = booking.teardown_minutes % 60
                if days or hours or minutes:
                    r25_res.tdown_tm = "P"
                else:
                    r25_res.tdown_tm = None
                if days:
                    r25_res.tdown_tm += "{}D".format(days)
                if hours or minutes:
                    r25_res.tdown_tm += "T"
                if hours:
                    r25_res.tdown_tm += "{:02}H".format(hours)
                if minutes:
                    r25_res.tdown_tm += "{:02}M".format(minutes)

                r25_res.reservation_start_dt = (
                    booking.date_time_start - datetime.timedelta(
                        minutes=booking.setup_minutes)).isoformat()
                r25_res.reservation_end_dt = (
                    booking.date_time_end + datetime.timedelta(
                        minutes=booking.teardown_minutes)).isoformat()

                r25_res.state = r25_res.STANDARD_STATE
                if r25_res.space_reservation is None:
                    r25_res.space_reservation = Space()

                r25_res.space_reservation.space_id = booking.space_id

            else:
                # Cancel this unwanted r25 event
                logger.debug("\t\tSetting event state to cancelled")
                r25_event.state = r25_event.CANCELLED_STATE
                r25_res.state = r25_res.CANCELLED_STATE
                # r25_res.space_reservation = None

            # by default, don't actually make changes
            if not options["update"]:
                continue

            try:
                logger.debug("\tUpdating event")
                updated = update_event(r25_event)
                logger.debug("\t\tUpdated event %s" % updated.event_id)

            except R25MessageException as ex:
                while ex:
                    if ex.msg_id == "EV_I_SPACECON":
                        logger.warning(
                            "Conflict while syncing Mazevo Booking %s (%s): %s"
                            % (booking.id, booking.event_number, ex.text)
                        )
                        messages.append(
                            "Conflict while syncing Mazevo Booking %s (%s): %s"
                            % (booking.id, booking.event_number, ex.text)
                        )
                        match = re.search(r"\[(?P<event_id>\d+)\]", ex.text)
                        if match:
                            try:
                                old_event = get_event_by_id(match.group("event_id"))
                                logger.warning(
                                    "Existing event: %s" % old_event.live_url()
                                )
                                messages.append(
                                    "Existing event: %s" % old_event.live_url()
                                )
                            except Exception:
                                logger.warning("Unknown event ")
                                messages.append("Unknown event ")
                            logger.warning(
                                "Is blocking event: %s" % r25_event.live_url()
                            )
                            messages.append(
                                "Is blocking event: %s" % r25_event.live_url()
                            )

                    else:
                        logger.warning(
                            "R25 message while syncing Mazevo Booking %s (%s) to "
                            "R25 Event %s: %s" % (booking.id, booking.event_number, r25_event.event_id, ex)
                        )
                        messages.append(
                            "R25 message while syncing Mazevo Booking %s (%s) to "
                            "R25 Event %s: %s" % (booking.id, booking.event_number, r25_event.event_id, ex)
                        )

                    ex = ex.next_msg

            except R25ErrorException as ex:
                logger.warning(
                    "R25 error while syncing Mazevo Booking %s (%s) to R25 Event "
                    " %s: %s" % (booking.id, booking.event_number, r25_event.event_id, ex)
                )
                messages.append(
                    "R25 error while syncing Mazevo Booking %s (%s) to R25 Event "
                    " %s: %s" % (booking.id, booking.event_number, r25_event.event_id, ex)
                )

            except DataFailureException as ex:
                logger.warning(
                    "HTTP error while syncing Mazevo Booking %s (%s) to R25 Event "
                    " %s: %s" % (booking.id, booking.event_number, r25_event.event_id, ex)
                )
                messages.append(
                    "HTTP error while syncing Mazevo Booking %s (%s) to R25 Event "
                    " %s: %s" % (booking.id, booking.event_number, r25_event.event_id, ex)
                )

            except TooManyRequestsException:
                self.stdout.write(
                    "Too Many Requests while syncing Mazevo Booking %s (%s) to "
                    "R25 Event %s" % (booking.id, booking.event_number, r25_event.event_id)
                )
                messages.append(
                    "Too Many Requests while syncing Mazevo Booking %s (%s) to "
                    "R25 Event %s" % (booking.id, booking.event_number, r25_event.event_id)
                )

        # send email
        if options["update"] and len(messages) > 0:
            send_mail(
                "Mazevo2R25 report",
                "\n".join(messages),
                settings.MAZEVO_R25_EMAIL_HOST_USER,
                settings.MAZEVO_R25_EMAIL_RECIPIENTS,
                fail_silently=False,
                auth_user=settings.MAZEVO_R25_EMAIL_HOST_USER,
                auth_password=settings.MAZEVO_R25_EMAIL_HOST_PASSWORD,
            )
