import json
import logging
import re

# from uw_r25.reservations import create_reservation, delete_reservations

from .exceptions import InvalidParamException
from . import RESTDispatch

logger = logging.getLogger(__name__)


class Reservation(RESTDispatch):
    def __init__(self):
        self._audit_log = logging.getLogger('audit')

    def POST(self, request, **kwargs):
        try:
            data = json.loads(request.body)
            name = self._valid_reservation_name(data.get("name", "").strip())
            user_id = data.get("user_id", None)
            account_id = data.get("account_id", None)
            site_id = data.get("site_id", None)
            location_id = data.get("location_id", None)
            position_id = data.get("position_id", None)
            start_time = self._valid_time(data.get("start_time", "").strip())
            end_time = self._valid_time(data.get("end_time", "").strip())

            reservation = create_reservation({'notes': name,
                                              'start_time': start_time,
                                              'end_time': end_time,
                                              'user_id': user_id,
                                              'account_id': account_id,
                                              'site_id': site_id,
                                              'location_id': location_id,
                                              'position_id': position_id,
                                              'published': True})

            reservation_id = reservation.reservation_id

            self._audit_log.info('%s scheduled %s from %s to %s' % (
                request.user, name, start_time, end_time))

            return self.json_response({'reservation_id': reservation_id})
        except InvalidParamException as ex:
            return self.error_response(400, "%s" % ex)
        except Exception as ex:
            return self.error_response(500, "Unable to save reservation: %s" % ex)

    def DELETE(self, request, **kwargs):
        try:
            reservation_id = self._valid_reservation_id(kwargs.get('reservation_id'))

            delete_reservations([reservation_id])
            self._audit_log.info(
                '%s deleted reservation %s' % (request.user, reservation_id))
            return self.json_response({'deleted_reservation_id': reservation_id})
        except InvalidParamException as err:
            return self.error_response(400, "Invalid Parameter: %s" % err)

    def _valid_reservation_id(self, reservation_id):
        if re.match(r'^\d+$', reservation_id):
            return reservation_id

        raise InvalidParamException('missing reservation id')

    def _valid_reservation_name(self, name):
        if name and len(name):
            return name

        raise InvalidParamException('bad reservation name')

    def _valid_time(self, time):
        if time and len(time):
            return time

        raise InvalidParamException('bad time value')
