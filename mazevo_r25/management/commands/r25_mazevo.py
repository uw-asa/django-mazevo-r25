from collections import OrderedDict
import datetime
import logging
import re
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from uw_mazevo.api import PublicCourses
from uw_sws.term import (get_current_term, get_next_term, get_term_after,
                         get_term_before, get_term_by_year_and_quarter)
from uw_r25.models import Event, Reservation

from mazevo_r25.more_r25 import get_event_list, get_reservations_attrs

logger = logging.getLogger("r25_mazevo")

"""
# There's a variety of formats to look out for when matching course names in R25.
# Here's some examples of ones we currently handle:
*ASL 302 A ASL302A 20251
*BIO A 206 A BIOA206A 20251
*BIO A 344 A XL BIOA344A 20251
A A 210 A AA210A 20251
ACADEM 198 AA ACADEM198AA 20251
AFRAM 241 A XL AFRAM241A 20251
*CS&SS 221 A XL CS&SS221A 20251
*EXAM: AMATH 502 A XL AMATH502A 20251
*AMATH 502 A XL AMATH502A 20251
EXAM:* STAT 391 A XL STAT391A 20251

# These are for rooms on hold in advance of the actual TS import
INFO 201 A /AUT25 Large Lecture
MUSEN 350/550/AUT25 Large Lecture               # No section!
STAT/SOC/CS&SS 221 /AUT25 Large Lecture         # No section!
STAT/SOC /CS&SS 221 / WIN26 Large Lect          # extra space in currics
"""
event_pat = re.compile(
    r"""
    ^                               # start at beginning
    (?:\*?)                         # optional asterisk
    (?P<exam>EXAM:\*?\ )?           # it's an exam, and another asterisk?
    (?P<curric>[A-Z &]+?)           # curric abbrev, can contain space, &
    (?:\ ?\/                        # slash separator, maybe an extra space
     (?P<curric2>[A-Z &]+?))?       # second curric
    (?:\ ?\/                        # slash separator, maybe an extra space
     (?P<curric3>[A-Z &]+?))?       # third curric
    [ ]                             # space separator
    (?P<number>\d{3})               # course number, 3 digits
    (?:\/                           # slash separator
     (?P<number2>\d{3}))?           # second number
    [ ]*                            # optional space separator
    (?P<section>\w{0,2})            # section, 1 or 2 letters, or absent
                                    # rest is ignored
    """, re.VERBOSE)

"""
# some room names to match
BAG  260
HST T568
SWS  026-030
CSE2 G20
GNOMS060
"""
room_pat = re.compile(
    r"""
    ^                               # start at beginning
    (?P<building>[A-Z0-9]{,4}?)     # building code, 4 chars or less
    [ ]*                            # optional space separator
    (?P<room>[A-Z]?\d{2,3}[A-Z]?)   # room number, 2 or 3 digits
    (?:-.*)?                        # combined room number, ignore it
    $                               # end at end
    """, re.VERBOSE)


class Command(BaseCommand):
    help = "Get course data from R25 and upload it to Mazevo"

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
            "-t",
            "--term",
            default="0",
            help="Single digit <n> for <n>th next term. Default is 0 (current term)",
        )

    def handle(self, *args, **options):

        self.set_logger(options.get("verbosity"))

        if options["term"] == "afternext":
            term = get_term_after(get_next_term())
        elif options["term"] == "next":
            term = get_next_term()
        elif len(options["term"]) < 2 and options["term"].isnumeric():
            # get <n> terms ahead (current term is 0)
            term = get_current_term()
            for i in range(int(options["term"])):
                term = get_term_after(term)
        elif options["term"]:
            first, second = re.split(r'\W', options["term"])
            if first.isdigit():
                year = first
                quarter = second
            else:
                year = second
                quarter = first
            term = get_term_by_year_and_quarter(year, quarter)
        else:
            term = get_current_term()

        prev_term = get_term_before(term)

        # import_term is the data structure we upload to Mazevo.
        # By coincidence, this format of startDate and endDate also works for the R25
        # API, so we re-use it in those queries.
        import_term = {
            "termDescription": "{} {}".format(term.quarter, term.year).title(),
            # can't use term.first_day_quarter because of early start classes
            "startDate": (
                prev_term.last_final_exam_date + datetime.timedelta(days=1)
                ).isoformat(),
            "endDate": term.last_final_exam_date.isoformat(),
        }

        logger.info("Retrieving R25 reservations for {}: {} - {}".format(
            import_term["termDescription"],
            import_term["startDate"], import_term["endDate"]))

        courses = {}

        """
        Querying R25 reservations:

        We search for event types of TS_SECTION for course meetings, and
        TS_SECTION_FINAL for final exams.

        We only search the spaces marked as our "favorites" in R25. The list of
        favorites is maintained automatically by the separate tool mazevo2r25.
        """

        # search for events in categories we want to be unlisted
        unlisted_events = get_event_list(
            event_type_id="+".join(settings.MAZEVO_R25_EVENTTYPES_ACADEMIC_IMPORT),
            space_favorite="T",
            state="+".join([Event.TENTATIVE_STATE,
                            Event.CONFIRMED_STATE,
                            Event.SEALED_STATE]),
            reservation_start_dt=import_term["startDate"],
            reservation_end_dt=import_term["endDate"],
            category_id="+".join(settings.MAZEVO_R25_CATEGORIES_UNLISTED))

        unlisted_event_ids = unlisted_events.keys()

        paginate = "T"
        page = 1

        while True:

            (reservations, attrs) = get_reservations_attrs(
                event_type_id="+".join(settings.MAZEVO_R25_EVENTTYPES_ACADEMIC_IMPORT),
                space_favorite="T",
                space_match="occurrence",
                state="+".join([Reservation.STANDARD_STATE,
                                Reservation.EXCEPTION_STATE,
                                Reservation.WARNING_STATE,
                                Reservation.OVERRIDE_STATE]),
                start_dt=import_term["startDate"],
                end_dt=import_term["endDate"],
                paginate=paginate, page=page, page_size=1000)

            if page == 1:
                logger.info("Total reservations: {}".format(attrs["total_results"]))

            logger.info("page {}/{}: {} reservations".format(
                page, attrs["page_count"], len(reservations)))

            paginate = attrs["paginate_key"]
            page += 1

            for reservation in reservations:
                if not reservation.space_reservation:
                    continue
                event_id = int(reservation.event_id)
                if event_id not in courses:
                    matches = event_pat.match(reservation.event_name)
                    courses[event_id] = {
                        "courseTitle": reservation.event_title,
                        "subjectCode": matches.group("curric"),
                        "courseNumber": matches.group("number"),
                        "section": matches.group("section"),
                        # "enrollment": reservation.registered_count,
                        "enrollment": "0",
                        "meetingTimesDict": {},
                    }
                    if not courses[event_id]["section"]:
                        logger.info("No section for {}".format(reservation.event_name))
                        courses[event_id]["section"] = "-"
                    # if not courses[event_id]["enrollment"]:
                    #     courses[event_id]["enrollment"] = "0"

                    if event_id in unlisted_event_ids or (
                            reservation.event_notes and
                            "safecampus" in reservation.event_notes.lower()):
                        """
                        For unlisted meetings, make it show:
                            ----- In use -----
                        Once everything is concatenated together.
                        """
                        courses[event_id]["subjectCode"] = "-"
                        courses[event_id]["courseNumber"] = "-"
                        courses[event_id]["section"] = "-"
                        courses[event_id]["courseTitle"] = "In use -----"

                course = courses[event_id]

                start_dt = datetime.datetime.fromisoformat(reservation.start_datetime)
                end_dt = datetime.datetime.fromisoformat(reservation.end_datetime)
                date = start_dt.date()
                dayname = PublicCourses().DAYS_OF_WEEK[date.isoweekday() % 7]

                # Weeks are Sunday To Saturday
                week_start = (date - datetime.timedelta(
                    days=date.isoweekday() % 7)).isoformat()
                week_end = (date + datetime.timedelta(
                    days=6 - date.isoweekday() % 7)).isoformat()

                s_time = start_dt.strftime("%H%M")
                e_time = end_dt.strftime("%H%M")

                # Some R25 spaces do not have whitespace between building and
                # room. First 4 characters are building, rest is room.
                if " " not in reservation.space_reservation.name:
                    reservation.space_reservation.name = \
                        reservation.space_reservation.name[:4] + " " + \
                        reservation.space_reservation.name[4:]
                matches = room_pat.match(reservation.space_reservation.name)
                building = matches.group("building")
                room = matches.group("room")

                # meetings on different days in the same week will be
                # consolidated as long as this data all matches
                key = "{}_{}_{}_{}".format(s_time, e_time, building, room)

                # meeting time and place doesn't exist yet
                if key not in course["meetingTimesDict"]:
                    # create new meeting/week dict
                    course["meetingTimesDict"][key] = {}

                # this week doesn't exist for this meeting time and place yet
                if week_start not in course["meetingTimesDict"][key]:
                    # add this week to meeting/week dict
                    course["meetingTimesDict"][key][week_start] = {
                        "startDate": week_start,
                        "endDate": week_end,
                        "startTime": s_time,
                        "endTime": e_time,
                        "sunday": False,
                        "monday": False,
                        "tuesday": False,
                        "wednesday": False,
                        "thursday": False,
                        "friday": False,
                        "saturday": False,
                        "buildingCode": building,
                        "roomCode": room,
                        "instructorName": "UNK",
                    }

                # Finally, make this day active for this time, place, and week
                course["meetingTimesDict"][key][week_start][dayname] = True

            # Last page?
            if not int(attrs["page_num"]) < int(attrs["page_count"]):
                break

        logger.info("Courses to upload: {}".format(len(courses)))

        # Merge adjacent weeks with matching schedules
        meeting_count = 0
        for course in courses.values():

            course["meetingTimes"] = []

            for weekDict in course["meetingTimesDict"].values():

                # make sure we have the weeks in order
                weeks = OrderedDict(sorted(weekDict.items()))

                n, week_a = weeks.popitem(False)
                while len(weeks):
                    n, week_b = weeks.popitem(False)
                    if (week_b["sunday"] == week_a["sunday"] and
                        week_b["monday"] == week_a["monday"] and
                        week_b["tuesday"] == week_a["tuesday"] and
                        week_b["wednesday"] == week_a["wednesday"] and
                        week_b["thursday"] == week_a["thursday"] and
                        week_b["friday"] == week_a["friday"] and
                        week_b["saturday"] == week_a["saturday"] and
                        week_b["startDate"] == (
                            datetime.datetime.fromisoformat(week_a["endDate"]) +
                            datetime.timedelta(days=1)).date().isoformat()):

                        # if they're compatible, and contiguous, merge them
                        week_a["endDate"] = week_b["endDate"]

                    else:
                        # done with week_a, move it over to meetingTimes
                        course["meetingTimes"].append(week_a)
                        meeting_count += 1

                        # week_b becomes the new week_a
                        week_a = week_b

                # move the final week_a over to meetingTimes
                course["meetingTimes"].append(week_a)
                meeting_count += 1

            del course["meetingTimesDict"]

        logger.info("Meetings to upload: {}".format(meeting_count))

        if meeting_count < 1:
            logger.warning("No meetings found. Exiting now")
            return

        import_term["courses"] = list(courses.values())

        PublicCourses().import_term(import_term)
