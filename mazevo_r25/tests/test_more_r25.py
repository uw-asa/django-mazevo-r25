from django.test import TestCase

from mazevo_r25.more_r25 import get_space_list


class TestMoreR25(TestCase):

    def test_get_space_list(self):
        spaces = get_space_list()
        self.assertEquals(len(spaces), 3)
        space = spaces[2]
        self.assertEquals(len(space), 2)
        (id, name) = space
        self.assertEquals(id, 1002)
        self.assertAlmostEquals(name, 'JHN 303')
