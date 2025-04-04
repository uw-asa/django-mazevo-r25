from collections import OrderedDict
import json
import logging
from lxml import etree
from urllib.parse import quote, urlencode

from restclients_core import models
from restclients_core.exceptions import DataFailureException
from restclients_core.util.retry import retry
from uw_r25 import nsmap, get_resource
from uw_r25.dao import R25_DAO
from uw_r25.events import events_from_xml
from uw_r25.models import Event, Reservation
from uw_r25.spaces import space_reservation_from_xml, spaces_from_xml


logger = logging.getLogger(__name__)


RETRY_STATUS_CODES = [0, 429]


def live_url(self):
    return "https://25live.collegenet.com/pro/%s#!/home/event/%s/details" % (
        R25_DAO().get_service_setting("INSTANCE"),
        self.event_id,
    )


Event.live_url = live_url


class R25ErrorException(Exception):
    """
    This exception means r25 returned <error> elements in a response.

    <?xml version="1.0" encoding="UTF-8"?>
    <r25:results xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xl="http://www.w3.org/1999/xlink"
                 xmlns:r25="http://www.collegenet.com/r25"
                 pubdate="2019-05-24T00:27:08-07:00"
                 engine="accl">
       <r25:error>
          <r25:msg_id>SY_E_DATAERROR</r25:msg_id>
          <r25:msg>Error saving; data format/validation error</r25:msg>
          <r25:id>789166</r25:id>
       </r25:error>
       <r25:error_details>
          <r25:error_detail table="events"
                            field="event_type_id"
                            value="306"
                            object_id="789166"
                            object_type="4">
            Inactive event_type_id
          </r25:error_detail>
       </r25:error_details>
    </r25:results>
    """

    def __init__(self, **kwargs):
        self.msg_id = kwargs.get("msg_id")
        self.msg = kwargs.get("msg")
        self.object_id = kwargs.get("id")
        self.proc_error = kwargs.get("proc_error")
        self.details = kwargs.get("details")

    def __str__(self):
        return "Error %s%s: %s%s%s" % (
            self.msg_id,
            " with %s" % self.object_id if self.object_id else "",
            self.msg,
            ", %s" % self.proc_error if self.proc_error else "",
            " %s" % json.dumps(self.details) if self.details else "",
        )


class R25MessageException(Exception):
    """
    This exception means r25 returned <messages> elements in a response.

    If the response contains more than one message, the next message is linked
    as 'next_msg'

    <r25:messages>
      <r25:msg_num>1</r25:msg_num>
      <r25:msg_id>EV_I_SPACECON</r25:msg_id>
      <r25:msg_text>Space KNE  225 unavailable due to [rsrv] conflict with
       CENTER FOR HUMAN RIGHTS 10TH ANNIVERSARY [15236046]</r25:msg_text>
      <r25:msg_entity_name>sp_reservations</r25:msg_entity_name>
      <r25:msg_object_id>5326</r25:msg_object_id>
    </r25:messages>
    """

    def __init__(self, num, msg_id, text, entity_name, object_id, next_msg=None):
        self.num = num
        self.msg_id = msg_id
        self.text = text
        self.entity_name = entity_name
        self.object_id = object_id
        self.next_msg = next_msg

    def __str__(self):
        return "Error %s with %s %s: %s%s" % (
            self.msg_id,
            self.entity_name,
            self.object_id,
            self.text,
            " [more...]" if self.next_msg else "",
        )


class TooManyRequestsException(Exception):
    pass


def post_resource(url):
    """
    Issue a POST request to R25

    :param url: endpoint to POST to
    :return: the response as an lxml.etree
    """

    instance = R25_DAO().get_service_setting("INSTANCE")
    if instance is not None:
        url = "/r25ws/wrd/%s/run/%s" % (instance, url)
    else:
        url = "/r25ws/servlet/wrd/run/%s" % url

    response = R25_DAO().postURL(url, {"Accept": "text/xml"})
    if response.status == 429:
        raise TooManyRequestsException(url)
    if response.status != 201:
        raise DataFailureException(url, response.status, response.data)

    tree = etree.fromstring(response.data.strip())

    # XHTML response is an error response
    xhtml = tree.xpath("//xhtml:html", namespaces=nsmap)
    if len(xhtml):
        raise DataFailureException(url, 500, response.data)

    return tree


def node_as_dict(node):
    mydict = {}
    for element in node:
        name = etree.QName(element).localname
        mydict[name] = element.text

    return mydict


def put_resource(url, body):
    """
    Issue a PUT request to R25

    :param url: endpoint to PUT to
    :param body: text to PUT
    :return: the response as an lxml.etree
    """

    instance = R25_DAO().get_service_setting("INSTANCE")
    if instance is not None:
        url = "/r25ws/wrd/%s/run/%s" % (instance, url)
    else:
        url = "/r25ws/servlet/wrd/run/%s" % url

    headers = {
        "Accept": "text/xml",
        "Content-Type": "text/xml",
    }

    response = R25_DAO().putURL(url, headers, body)
    if response.status not in (200, 201, 400, 403, 425):
        raise DataFailureException(url, response.status, response.data)

    tree = etree.fromstring(response.data.strip())

    # XHTML response is an error response
    xhtml = tree.xpath("//xhtml:html", namespaces=nsmap)
    if len(xhtml):
        raise DataFailureException(url, 500, response.data)

    enodes = tree.xpath("r25:error", namespaces=nsmap)
    if len(enodes):
        err = node_as_dict(enodes[0])
        details = tree.xpath("r25:error_details/r25:error_detail", namespaces=nsmap)
        if len(details):
            err["details"] = []
        for node in details:
            detail = dict(node.attrib)
            detail["description"] = node.text
            err["details"].append(detail)
        raise R25ErrorException(**err)

    mnodes = tree.xpath("r25:messages", namespaces=nsmap)
    if len(mnodes):
        next_ex = None
        for mnode in reversed(mnodes):
            next_ex = R25MessageException(
                mnode.xpath("r25:msg_num", namespaces=nsmap)[0].text,
                mnode.xpath("r25:msg_id", namespaces=nsmap)[0].text,
                mnode.xpath("r25:msg_text", namespaces=nsmap)[0].text,
                mnode.xpath("r25:msg_entity_name", namespaces=nsmap)[0].text,
                mnode.xpath("r25:msg_object_id", namespaces=nsmap)[0].text,
                next_ex,
            )
        raise next_ex

    return tree


def delete_resource(url):
    """
    Issue a DELETE request to R25

    :param url: endpoint to DELETE
    :return: the response as an lxml.etree
    """

    instance = R25_DAO().get_service_setting("INSTANCE")
    if instance is not None:
        url = "/r25ws/wrd/%s/run/%s" % (instance, url)
    else:
        url = "/r25ws/servlet/wrd/run/%s" % url

    headers = {
        "Accept": "text/xml",
        "Content-Type": "text/xml",
    }

    response = R25_DAO().deleteURL(url, headers)
    if response.status != 200:
        raise DataFailureException(url, response.status, response.data)

    tree = etree.fromstring(response.data.strip())

    # XHTML response is an error response
    xhtml = tree.xpath("//xhtml:html", namespaces=nsmap)
    if len(xhtml):
        raise DataFailureException(url, 500, response.data)

    return tree


def update_value(node, name, value):
    """
    Adds or updates the value of a basic text element in an R25 etree.

    Adds 'status="mod"' to all ancestor elements so that R25 recognizes our
    change.

    :param node: The node which contains our element
    :param name: The element's name
    :param value: The new value for the element
    :return: The new or updated element
    """

    try:
        element = node.xpath("r25:%s" % name, namespaces=nsmap)[0]
    except IndexError:
        # create the element
        element = etree.SubElement(node, "{%s}%s" % (nsmap["r25"], name), nsmap=nsmap)

    if (
        (not value and not element.text)
        or element.text == value
        or (element.text and value and (element.text.lower() == str(value).lower()))
    ):
        # no change
        return element

    logger.debug(
        "changing %s from %s to %s"
        % (element.getroottree().getpath(element), element.text, value)
    )
    element.text = None if value is None else str(value)

    # mark ancestors as modified
    while "status" in node.attrib and node.attrib["status"] == "est":
        node.attrib["status"] = "mod"
        node = node.getparent()

    return element


def add_node(node, name):
    """
    Adds a new node to an R25 etree

    Adds 'status="mod"' to all ancestor elements so that R25 recognizes our
    change.

    :param node: The parent of our new node
    :param name: The new node's name
    :return: The new node
    """

    logger.debug("adding %s to %s" % (name, node.getroottree().getpath(node)))

    element = etree.SubElement(
        node,
        "{%s}%s" % (nsmap["r25"], name),
        attrib={"status": "new"},
        nsmap=nsmap,
    )

    # mark ancestors as modified
    while "status" in node.attrib and node.attrib["status"] == "est":
        node.attrib["status"] = "mod"
        node = node.getparent()

    return element


def delete_node(node):
    """
    Deletes a node from an R25 etree

    Just marks the node with 'status="del"' and adds 'status="mod"' to all
    ancestor elements so that R25 recognizes our change.

    :param node: The node to mark deleted
    :return: The node
    """

    logger.debug("deleting %s" % node.getroottree().getpath(node))

    node.attrib["status"] = "del"
    node = node.getparent()

    # mark ancestors as modified
    while "status" in node.attrib and node.attrib["status"] == "est":
        node.attrib["status"] = "mod"
        node = node.getparent()

    return node


@retry(DataFailureException, status_codes=RETRY_STATUS_CODES)
def get_editable_event(event):
    """
    Retrieves from R25 the editable version of the event, or a new blank event
    if necessary.
    """
    if event.event_id is None:
        # Create a new event
        url = "events.xml"
        return post_resource(url)

    else:
        url = "event.xml?event_id=%s&mode=edit" % event.event_id
        return get_resource(url)


def update_event(event):
    """
    Create or update the given event in R25

    We use some fields not supported by uw_r25, by just having more properties on the
    event object. We start with the editable event xml that R25 provides to us, parse
    it, make any needed changes, and send it back again as xml.

    :param event: a uw_r25.models.event
    :return: the new or updated event from R25, as a uw_r25.models.event
    """

    event_tree = get_editable_event(event)
    enode = event_tree.xpath("r25:event", namespaces=nsmap)[0]

    if event.event_id is None:
        event.event_id = enode.xpath("r25:event_id", namespaces=nsmap)[0].text
        logger.debug("created new event %s" % event.event_id)

        # delete the blank profile
        pnode = enode.xpath("r25:profile", namespaces=nsmap)[0]
        enode.remove(pnode)

    update_value(enode, "alien_uid", event.alien_uid)
    update_value(enode, "event_name", event.name)
    update_value(enode, "event_title", event.title)
    update_value(enode, "start_date", event.start_date)
    update_value(enode, "end_date", event.end_date)
    update_value(enode, "state", event.state)
    if hasattr(event, "event_type_id"):
        update_value(enode, "event_type_id", event.event_type_id)
    update_value(enode, "parent_id", event.parent_id)
    update_value(enode, "cabinet_id", event.cabinet_id)
    update_value(enode, "cabinet_name", event.cabinet_name)
    update_value(enode, "node_type", event.node_type)

    onode = enode.xpath("r25:organization", namespaces=nsmap)[0]
    update_value(
        onode,
        "organization_id",
        event.organization_id,
    )
    update_value(onode, "primary", "T")

    # add or update each reservation/profile
    # only one reservation per profile is supported
    for res in event.reservations:
        if res.reservation_id:
            # find existing profile
            xpath = (
                "r25:profile[./r25:reservation/r25:reservation_id = '%s']"
                % res.reservation_id
            )
            pnode = enode.xpath(xpath, namespaces=nsmap)[0]
            rnode = pnode.xpath("r25:reservation", namespaces=nsmap)[0]

        else:
            # add new profile and reservation
            pnode = add_node(enode, "profile")
            rnode = add_node(pnode, "reservation")

        # add or update setup time
        setup_node = None
        try:
            setup_node = pnode.xpath("r25:setup_profile", namespaces=nsmap)[0]
        except IndexError:
            pass

        if setup_node is not None:
            if res.setup_tm is None:
                # We don't want a setup time. delete it
                delete_node(setup_node)
                setup_node = None

        if res.setup_tm is not None:
            if setup_node is None:
                # We want a setup time. add it.
                setup_node = add_node(pnode, "setup_profile")

            # Update to our current setup time.
            update_value(setup_node, "setup_tm", res.setup_tm)

        # add or update takedown time
        tdown_node = None
        try:
            tdown_node = pnode.xpath("r25:takedown_profile", namespaces=nsmap)[0]
        except IndexError:
            pass

        if tdown_node is not None:
            if res.tdown_tm is None:
                # We don't want a takedown time. delete it
                delete_node(tdown_node)
                tdown_node = None

        if res.tdown_tm is not None:
            if tdown_node is None:
                # We want a takedown time. add it.
                tdown_node = add_node(pnode, "takedown_profile")

            # Update to our current takedown time.
            update_value(tdown_node, "tdown_tm", res.tdown_tm)

        update_value(pnode, "profile_name", res.profile_name)
        update_value(pnode, "init_start_dt", res.start_datetime)
        update_value(pnode, "init_end_dt", res.end_datetime)

        # reservation_start_dt and reservation_end_dt are when setup time starts and
        # takedown time ends. It looks like they will be ignored by the server and
        # instead calculated from the values in setup_profile and takedown_profile.
        update_value(rnode, "reservation_start_dt", res.reservation_start_dt)
        update_value(rnode, "reservation_end_dt", res.reservation_end_dt)

        update_value(rnode, "event_start_dt", res.start_datetime)
        update_value(rnode, "event_end_dt", res.end_datetime)
        # update_value(rnode, "pre_event_start_dt", res.start_datetime)
        # update_value(rnode, "post_event_end_dt", res.end_datetime)
        update_value(rnode, "reservation_state", res.state)

        # add or update space_reservation
        # only one space_reservation per reservation is supported
        srnode = None
        try:
            srnode = rnode.xpath("r25:space_reservation", namespaces=nsmap)[0]
        except IndexError:
            pass

        if srnode is not None:
            if res.space_reservation is None or srnode.xpath(
                "r25:space_id", namespaces=nsmap
            )[0].text != str(res.space_reservation.space_id):
                # outdated space reservation. delete it
                delete_node(srnode)
                srnode = None

        if res.space_reservation is not None:
            if srnode is None:
                # Add space reservation
                srnode = add_node(rnode, "space_reservation")

            update_value(srnode, "space_id", str(res.space_reservation.space_id))

    # Make sure event dates encompass all reservations
    # for res in r25_event.reservations:
    #     res_start_date = res.start_datetime.split('T')[0]
    #     res_end_date = res.end_datetime.split('T')[0]
    #     if res_start_date < r25_event.start_date:
    #         r25_event.start_date = res_start_date.isoformat()
    #     if res_end_date > r25_event.end_date:
    #         r25_event.end_date = res_end_date

    if enode.attrib["status"] == "est":
        logger.debug("Event unchanged")
        return event

    url = "event.xml?event_id=%s&return_doc=T" % event.event_id

    return _update_event(url, event_tree)


@retry(DataFailureException, status_codes=RETRY_STATUS_CODES)
def _update_event(url, event_tree):
    return events_from_xml(put_resource(url, etree.tostring(event_tree)))[0]


def delete_event(event_id):
    """
    Delete event from R25

    :param event_id: an R25 event id
    :return: the response from R25, as an lxml.etree
    """

    url = "event.xml?event_id=%s" % event_id

    result = delete_resource(url)

    return result


def get_space_by_short_name(short_name):
    """
    Get a single space with the given short name

    Can't just use get_spaces because the argument won't be quoted properly
    """
    url = "spaces.xml"
    url += "?short_name={}".format(quote(short_name))
    return spaces_from_xml(get_resource(url))[0]


def get_event_type_list(**kwargs):
    """
    Get the list of event type ids and names
    Note that you need to pass all_types="T" if you want all node types
    """
    url = "evtype.xml"
    kwargs["scope"] = "list"
    url += "?{}".format(urlencode(kwargs))
    return list_items_from_xml(get_resource(url))


def get_space_list(**kwargs):
    """
    Get the list of space ids and names
    """
    url = "spaces.xml"
    kwargs["scope"] = "list"
    url += "?{}".format(urlencode(kwargs))
    return list_items_from_xml(get_resource(url))


def get_event_list(**kwargs):
    """
    Get the list of event ids and names
    """
    url = "events.xml"
    kwargs["scope"] = "list"
    url += "?{}".format(urlencode(kwargs))
    return list_items_from_xml(get_resource(url))


def list_items_from_xml(tree):
    items = OrderedDict()
    for node in tree.xpath("//r25:item", namespaces=nsmap):
        id = int(node.xpath("r25:id", namespaces=nsmap)[0].text)
        name = node.xpath("r25:name", namespaces=nsmap)[0].text
        items[id] = name
    return items


class Object(models.Model):
    EVENT_TYPE = 1
    ORGANIZATION_TYPE = 2
    CONTACT_TYPE = 3
    SPACE_TYPE = 4
    RATE_SCHEDULE_TYPE = 5
    RESOURCE_TYPE = 6
    EVENT_TYPE_TYPE = 7
    REPORT_TYPE = 9
    TASK_SEARCH_TYPE = 10
    EVENT_SEARCH_TYPE = 11
    SPACE_SEARCH_TYPE = 14
    RESOURCE_SEARCH_TYPE = 15
    ORGANIZATION_SEARCH_TYPE = 16


def object_from_xml(tree):
    id = int(tree.xpath("r25:object_id", namespaces=nsmap)[0].text)
    name = tree.xpath("r25:object_name", namespaces=nsmap)[0].text
    return (id, name)


def objects_from_xml(tree):
    objects = []
    for node in tree.xpath("//r25:object", namespaces=nsmap):
        item = object_from_xml(node)
        objects.append(item)
    return objects


def get_favorites(object_type):
    """
    Returns a list of favorite objects for the object type supplied in the argument
    """
    url = "favorites.xml"
    url += "?object_type={}".format(object_type)
    return dict(objects_from_xml(get_resource(url)))


def add_favorite(object_type, object_id):
    """
    Make an individual object a favorite
    """
    url = "favorites.xml"
    url += "?object_type={}&object_id={}".format(object_type, object_id)
    result = put_resource(url, "")

    return result


def delete_favorite(object_type, object_id):
    """
    Remove an individual object as a favorite
    """
    url = "favorites.xml"
    url += "?object_type={}&object_id={}".format(object_type, object_id)
    result = delete_resource(url)

    return result


def reservations_from_xml(tree):
    try:
        profile_name = tree.xpath("r25:profile_name", namespaces=nsmap)[0].text
    except Exception:
        profile_name = None

    reservations = []
    for node in tree.xpath("r25:reservation", namespaces=nsmap):
        reservation = Reservation()
        reservation.reservation_id = node.xpath("r25:reservation_id",
                                                namespaces=nsmap)[0].text
        reservation.start_datetime = node.xpath("r25:reservation_start_dt",
                                                namespaces=nsmap)[0].text
        reservation.end_datetime = node.xpath("r25:reservation_end_dt",
                                              namespaces=nsmap)[0].text
        reservation.state = node.xpath("r25:reservation_state",
                                       namespaces=nsmap)[0].text
        reservation.registered_count = node.xpath("r25:registered_count",
                                                  namespaces=nsmap)[0].text
        if profile_name:
            reservation.profile_name = profile_name
        else:
            reservation.profile_name = node.xpath("r25:profile_name",
                                                  namespaces=nsmap)[0].text

        try:
            pnode = node.xpath("r25:space_reservation", namespaces=nsmap)[0]
            reservation.space_reservation = space_reservation_from_xml(pnode)
        except IndexError:
            reservation.space_reservation = None

        try:
            enode = node.xpath("r25:event", namespaces=nsmap)[0]
            reservation.event_id = enode.xpath("r25:event_id",
                                               namespaces=nsmap)[0].text
            reservation.event_name = enode.xpath("r25:event_name",
                                                 namespaces=nsmap)[0].text
            reservation.event_title = enode.xpath("r25:event_title",
                                                  namespaces=nsmap)[0].text

            rnode = enode.xpath("r25:role", namespaces=nsmap)[0]
            cnode = rnode.xpath("r25:contact", namespaces=nsmap)[0]
            reservation.contact_name = cnode.xpath("r25:contact_name",
                                                   namespaces=nsmap)[0].text
            try:
                anode = cnode.xpath("r25:address", namespaces=nsmap)[0]
                reservation.contact_email = anode.xpath(
                    "r25:email", namespaces=nsmap)[0].text
            except IndexError:
                reservation.contact_email = None

            reservation.event_notes = None
            for tnode in enode.xpath("r25:event_text", namespaces=nsmap):
                if tnode.xpath("r25:text_type_id", namespaces=nsmap)[0].text == '2':
                    reservation.event_notes = tnode.xpath(
                        "r25:text", namespaces=nsmap)[0].text

        except IndexError:
            enode = tree.getparent()
            reservation.event_id = enode.xpath("r25:event_id",
                                               namespaces=nsmap)[0].text
            reservation.event_name = enode.xpath("r25:event_name",
                                                 namespaces=nsmap)[0].text

        reservations.append(reservation)

    return reservations


@retry(DataFailureException, status_codes=RETRY_STATUS_CODES)
def get_reservations_attrs(**kwargs):
    kwargs["scope"] = "extended"
    url = "reservations.xml"
    if len(kwargs):
        url += "?{}".format(urlencode(kwargs))

    result = get_resource(url)

    return (reservations_from_xml(result), dict(result.attrib))
