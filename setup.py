#!/usr/bin/env python

import os
from setuptools import setup

PACKAGE = "mazevo_r25"

README = open(os.path.join(os.path.dirname(__file__), "README.md")).read()

# The VERSION file is created during build, based on the tag name
version_path = os.path.join(PACKAGE, "VERSION")
VERSION = open(os.path.join(os.path.dirname(__file__), version_path)).read()
VERSION = VERSION.replace("\n", "")

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="Django-Mazevo-R25",
    version=VERSION,
    packages=[PACKAGE],
    include_package_data=True,
    install_requires=[
        "Dickens",
        "Django>=1.11.19,<3.2",
        'Django-SupportTools<3.0 ; python_version < "3.0"',
        'Django-SupportTools ; python_version >= "3.0"',
        "lxml",
        "python-dateutil",
        "requests",
        "UW-RestClients-Mazevo @ git+https://github.com/uw-asa/uw-restclients-mazevo.git",
        'UW-RestClients-GWS<2.0 ; python_version < "3.0"',
        'UW-RestClients-GWS ; python_version >= "3.0"',
        "UW-RestClients-R25",
        'UW-RestClients-SWS<2.0 ; python_version < "3.0"',
        'UW-RestClients-SWS ; python_version >= "3.0"',
    ],
    license="Apache License, Version 2.0",
    description="Django app to generate R25 events from Mazevo",
    long_description=README,
    url="https://github.com/uw-asa/django-mazevo-r25",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
    ],
)
