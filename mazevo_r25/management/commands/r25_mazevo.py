from collections import OrderedDict
import datetime
import logging
import re
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from mazevo_r25.more_r25 import get_reservations_attrs
from uw_mazevo.api import PublicCourses
from uw_sws.term import get_current_term, get_next_term, get_term_by_year_and_quarter
from uw_r25.models import Reservation


logger = logging.getLogger("r25_mazevo")

# some event names to match
# '*ASL 302 A ASL302A 20251'
# '*BIO A 206 A BIOA206A 20251'
# '*BIO A 344 A XL BIOA344A 20251'
# 'A A 210 A AA210A 20251'
# 'ACADEM 198 AA ACADEM198AA 20251'
# 'AFRAM 241 A XL AFRAM241A 20251'
# '*CS&SS 221 A XL CS&SS221A 20251'
# '*EXAM: AMATH 502 A XL AMATH502A 20251'
# '*AMATH 502 A XL AMATH502A 20251'
# 'EXAM:* STAT 391 A XL STAT391A 20251'

event_pat = re.compile(r"""
                       ^                        # start at beginning
                       (?:\*?)                  # optional asterisk (why?)
                       (?P<exam>EXAM:\*? )?     # it's an exam, and another asterisk?
                       (?P<curric>[A-Z &]+)\s+  # curric abbrev, can contain space, &
                       (?P<number>\d{3})\s+     # course number, 3 digits
                       (?P<section>\w{1,2})\s+  # section, 1 or 2 letters
                                                # rest is ignored
""", re.VERBOSE)

# some room names to match
# 'BAG  260'
# 'HST T568'
# 'SWS  026-030'
room_pat = re.compile(r"""
                      ^                             # start at beginning
                      (?P<building>[A-Z]+[0-9]?)\s+ # building code
                      (?P<room>[A-Z]?\d{2,3}[A-Z]?) # room number
                      (?:-.*)?                      # room "extension"
                      $                             # end at end
""", re.VERBOSE)


class Command(BaseCommand):
    help = "uploads course data from SWS to Mazevo"

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
            help="Term to upload. Default is current term. 'next' for next term",
        )
        parser.add_argument(
            "-u",
            "--update",
            action="store_true",
            help="Update the term in Mazevo",
        )
        parser.add_argument(
            "--finals",
            action="store_true",
            help="Get finals, rather than instruction days",
        )

    def handle(self, *args, **options):

        self.set_logger(options.get("verbosity"))

        if options["term"] == "next":
            term = get_next_term()
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

        import_term = {
            "termDescription": "{} {}".format(term.quarter, term.year).title(),
        }

        if options["finals"]:
            import_term["termDescription"] += " Finals"
            import_term["startDate"] = (term.last_day_instruction
                                        + datetime.timedelta(days=1)).isoformat()
            import_term["endDate"] = term.last_final_exam_date.isoformat()
        else:
            import_term["startDate"] = term.first_day_quarter.isoformat()
            import_term["endDate"] = term.last_day_instruction.isoformat()

        logger.info("Retrieving R25 reservations for {}".format(
            import_term["termDescription"]))

        courses = {}

        """
        Querying R25 reservations:

        We search for event type of either TS_SECTION for course meetings, or
        TS_SECTION_FINAL for final exams. We can't do both at once because for
        one thing, event type isn't returned by the rest client, and we'd want
        to use it in order to separate them into different terms for import to
        Mazevo.

        We only search the spaces marked as our "favorites" in R25. The list of
        favorites is maintained automatically by the separate tool mazevo2r25.
        """

        reservation_search = {
            "event_type_id": (
                settings.MAZEVO_R25_EVENTTYPE_TS_SECTION_FINAL if options["finals"]
                else settings.MAZEVO_R25_EVENTTYPE_TS_SECTION),
            "space_favorite": "T",
            "space_match": "occurrence",
            "state": "+".join([Reservation.STANDARD_STATE,
                               Reservation.EXCEPTION_STATE,
                               Reservation.WARNING_STATE,
                               Reservation.OVERRIDE_STATE]),
            "start_dt": term.first_day_quarter.isoformat(),
            "end_dt": term.last_final_exam_date.isoformat(),
        }

        paginate = "T"
        page = 1

        while True:

            (reservations, attrs) = get_reservations_attrs(
                **reservation_search, paginate=paginate, page=page, page_size=1000)

            if page == 1:
                logger.info("Total reservations: {}".format(attrs["total_results"]))

            logger.info("page {}/{}: {} reservations".format(
                page, attrs["page_count"], len(reservations)))

            paginate = attrs["paginate_key"]
            page += 1

            for reservation in reservations:
                if reservation.event_id not in courses:
                    matches = event_pat.match(reservation.event_name)
                    courses[reservation.event_id] = {
                        "courseTitle": reservation.event_name,
                        "subjectCode": matches.group("curric"),
                        "courseNumber": matches.group("number"),
                        "section": matches.group("section"),
                        "enrollment": 0,
                        "meetingTimesDict": {},
                    }

                course = courses[reservation.event_id]

                start_dt = datetime.datetime.fromisoformat(reservation.start_datetime)
                end_dt = datetime.datetime.fromisoformat(reservation.end_datetime)
                date = start_dt.date()
                week = term.get_calendar_week_of_term_for_date(start_dt)
                dayname = PublicCourses().DAYS_OF_WEEK[date.isoweekday() % 7]

                # Weeks are Sunday To Saturday
                week_start = (date - datetime.timedelta(
                    days=date.isoweekday() % 7)).isoformat()
                week_end = (date + datetime.timedelta(
                    days=6 - date.isoweekday() % 7)).isoformat()

                s_time = start_dt.strftime("%H%M")
                e_time = end_dt.strftime("%H%M")

                # Some R25 spaces do not have whitesspace between building and
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
                if week not in course["meetingTimesDict"][key]:
                    # add this week to meeting/week dict
                    course["meetingTimesDict"][key][week] = {
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
                course["meetingTimesDict"][key][week][dayname] = True

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

        import_term["courses"] = list(courses.values())

        # by default, don't actually make changes
        if not options["update"]:
            logger.info("Not running with --update. Exiting now")
            return

        PublicCourses().import_term(import_term)
