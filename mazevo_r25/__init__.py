import os
from os.path import abspath, dirname

from restclients_core.dao import MockDAO
from uw_mazevo.mock import MazevoMockData

MockDAO.register_mock_path(
    os.path.join(abspath(dirname(__file__)), "resources")
)

MazevoMockData.register_mock_path(
    os.path.join(abspath(dirname(__file__)), "resources")
)
