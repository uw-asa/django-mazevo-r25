import datetime

from django.core.management.base import BaseCommand, CommandError
from ems_client.models import Status
from ems_client.service import Service
from restclients_core.exceptions import DataFailureException
from uw_r25.events import get_event_by_alien_id
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

    def handle(self, *args, **options):
        search = {
            'start_date': options['start'] or datetime.date.today().isoformat(),
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
            r25_alien_uid = "AT_EMS_RSRV_%s" % ems_res_id
            ems_bookings = ems_reservations[ems_res_id]['bookings']

            try:
                r25_event = get_event_by_alien_id(r25_alien_uid)
            except DataFailureException:
                # No R25 event matching this EMS event
                r25_event = Event()
                r25_event.alien_uid = r25_alien_uid
                r25_event.reservations = []

            for ems_bk_id in ems_bookings:
                ems_booking = ems_bookings[ems_bk_id]

                r25_profile_name = "AT_EMS_BOOK_%s" % ems_bk_id

                r25_res = None
                for r in r25_event.reservations:
                    if r.profile_name == r25_profile_name:
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

            try:
                updated = update_event(r25_event)

            except R25MessageException as ex:
                if ex.id == 'EV_I_SPACECON':
                    print ex.text

            # # If not booked space, no need to create in R25
            # if e['status_type'] != Status.STATUS_TYPE_BOOKED_SPACE:
            #     e['synchronized'] = True
            #
            # continue






