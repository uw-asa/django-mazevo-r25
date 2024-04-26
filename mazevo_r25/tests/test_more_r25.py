from django.test import TestCase

from mazevo_r25.more_r25 import get_event_type_list, get_space_by_short_name, get_space_list


class TestMoreR25(TestCase):

    def test_get_space_by_short_name(self):
        space = get_space_by_short_name("GLD 100A")
        self.assertEquals(space.space_id, "1001")

    def test_get_space_list(self):
        spaces = get_space_list()
        self.assertEquals(len(spaces), 3)
        space = spaces[2]
        self.assertEquals(len(space), 2)
        (id, name) = space
        self.assertEquals(id, 1002)
        self.assertEquals(name, "JHN 303")

    def test_get_event_type_list(self):
        types = get_event_type_list()  # only cabinets
        self.assertEqual(len(types), 2, "cabinet event type count")

        types = get_event_type_list(all_types="T")
        self.assertEqual(len(types), 7, "event type count")
