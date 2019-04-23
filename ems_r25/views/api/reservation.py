import json
import logging
import re

from ...utils import create_r25_reservation
from .exceptions import InvalidParamException
from . import RESTDispatch

logger = logging.getLogger(__name__)


class Reservation(RESTDispatch):
    def __init__(self):
        self._audit_log = logging.getLogger('audit')

    def POST(self, request, **kwargs):
        try:
            data = json.loads(request.body)
            data['event_name'] = self._valid_reservation_name(
                data.get("event_name", "").strip())
            data['start_time'] = self._valid_time(
                data.get("start_time", "").strip())
            data['end_time'] = self._valid_time(
                data.get("end_time", "").strip())

            reservation = create_r25_reservation(data)

            self._audit_log.info('%s scheduled %s from %s to %s' % (
                request.user, reservation['r25_alien_uid'],
                reservation['start_time'], reservation['end_time']))

            return self.json_response({
                'r25_event_id': reservation['r25_event_id'],
                'r25_reservation_id': reservation['r25_reservation_id'],
                'synchronized': reservation['synchronized'],
            })
        except InvalidParamException as ex:
            return self.error_response(400, "%s" % ex)
        except Exception as ex:
            return self.error_response(
                500, "Unable to save reservation: %s" % ex)

    def DELETE(self, request, **kwargs):
        try:
            reservation_id = self._valid_reservation_id(
                kwargs.get('reservation_id'))

            delete_reservations([reservation_id])
            self._audit_log.info(
                '%s deleted reservation %s' % (request.user, reservation_id))
            return self.json_response({
                'deleted_reservation_id': reservation_id})
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
