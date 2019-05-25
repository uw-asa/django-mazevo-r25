import json
import unittest

from django.contrib.auth.models import User
from django.test import Client
import pycodestyle


class TestCodeFormat(unittest.TestCase):

    def test_conformance(self):
        """Test that we conform to PEP-8."""
        style = pycodestyle.StyleGuide()
        result = style.check_files(['ems_r25'])
        self.assertEqual(result.total_errors, 0,
                         "Found code style errors (and warnings).")


def get_user(username):
    try:
        user = User.objects.get(username=username)
        return user
    except Exception:
        user = User.objects.create_user(username, password='pass')
        return user


def get_user_pass(username):
    return 'pass'


class EMSR25Test(unittest.TestCase):
    def setUp(self):
        # Every test needs a client.
        self.client = Client()

    def set_user(self, username):
        get_user(username)
        self.client.login(username=username,
                          password=get_user_pass(username))

    def test_events(self):
        self.set_user('javerage')

        # Issue a GET request.
        response = self.client.get('/')

        # Check that the response is 200 OK.
        self.assertEqual(response.status_code, 200)

    def test_api_schedule(self):
        # Issue a GET request.
        response = self.client.get(
            '/api/v1/schedule/?StartDate=2018-12-18&EndDate=2018-12-18')

        # Check that the response is 200 OK.
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(len(data), 18)
