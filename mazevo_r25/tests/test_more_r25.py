from django.test import TestCase
from uw_r25.models import Event

from mazevo_r25.more_r25 import (
    get_event_type_list,
    get_space_by_short_name,
    get_space_list,
    update_event,
)


class TestMoreR25(TestCase):

    def test_get_space_by_short_name(self):
        space = get_space_by_short_name("GLD 100A")
        self.assertEqual(space.space_id, "1001")

    def test_get_space_list(self):
        spaces = get_space_list()
        self.assertEqual(len(spaces), 3)
        space = spaces[2]
        self.assertEqual(len(space), 2)
        (id, name) = space
        self.assertEqual(id, 1002)
        self.assertEqual(name, "JHN 303")

    def test_get_event_type_list(self):
        types = get_event_type_list()  # only cabinets
        self.assertEqual(len(types), 2, "cabinet event type count")

        types = get_event_type_list(all_types="T")
        self.assertEqual(len(types), 7, "event type count")

    def test_update_event(self):
        event = Event()
        event.reservations = []
        event.event_type_id = 433
        event.node_type = "E"
        event.organization_id = 4211
        update_event(event)
