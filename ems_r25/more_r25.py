import logging
from lxml import etree

from restclients_core.exceptions import DataFailureException
from uw_r25 import nsmap, get_resource
from uw_r25.dao import R25_DAO
from uw_r25.events import events_from_xml


logger = logging.getLogger(__name__)


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


class R25MessageException(Exception):
    """
    This exception means r25 returned <messages> elements in a response.

    <r25:messages>
      <r25:msg_num>1</r25:msg_num>
      <r25:msg_id>EV_I_SPACECON</r25:msg_id>
      <r25:msg_text>Space KNE  225 unavailable due to [rsrv] conflict with
       CENTER FOR HUMAN RIGHTS 10TH ANNIVERSARY [15236046]</r25:msg_text>
      <r25:msg_entity_name>sp_reservations</r25:msg_entity_name>
      <r25:msg_object_id>5326</r25:msg_object_id>
    </r25:messages>
    """
    def __init__(self, num, msg_id, text, entity_name, object_id,
                 next_msg=None):
        self.num = num
        self.msg_id = msg_id
        self.text = text
        self.entity_name = entity_name
        self.object_id = object_id
        self.next_msg = next_msg

    def __str__(self):
        return ("Error %s with %s %s: %s%s" %
                (self.msg_id, self.entity_name, self.object_id, self.text,
                 ' [more...]' if self.next_msg else ''))


def post_resource(url):
    """
    Issue a POST request to R25 with the given url
    and return a response as an etree element.
    """

    instance = R25_DAO().get_service_setting('INSTANCE')
    if instance is not None:
        url = "/r25ws/wrd/%s/run/%s" % (instance, url)
    else:
        url = "/r25ws/servlet/wrd/run/%s" % url

    response = R25_DAO().postURL(url, {"Accept": "text/xml"})
    if response.status != 201:
        raise DataFailureException(url, response.status, response.data)

    tree = etree.fromstring(response.data.strip())

    # XHTML response is an error response
    xhtml = tree.xpath("//xhtml:html", namespaces=nsmap)
    if len(xhtml):
        raise DataFailureException(url, 500, response.data)

    return tree


def put_resource(url, body):
    """
    Issue a PUT request to R25 with the given url
    and return a response as an etree element.
    """

    instance = R25_DAO().get_service_setting('INSTANCE')
    if instance is not None:
        url = "/r25ws/wrd/%s/run/%s" % (instance, url)
    else:
        url = "/r25ws/servlet/wrd/run/%s" % url

    headers = {
        "Accept": "text/xml",
        "Content-Type": "text/xml",
    }

    response = R25_DAO().putURL(url, headers, body)
    if response.status not in (200, 201):
        raise DataFailureException(url, response.status, response.data)

    tree = etree.fromstring(response.data.strip())

    # XHTML response is an error response
    xhtml = tree.xpath("//xhtml:html", namespaces=nsmap)
    if len(xhtml):
        raise DataFailureException(url, 500, response.data)

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
                next_ex)
        raise next_ex

    return tree


def delete_resource(url):
    """
    Issue a DELETE request to R25 with the given url
    and return a response as an etree element.
    """

    instance = R25_DAO().get_service_setting('INSTANCE')
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


# Adds or updates the value of a basic text element
def update_value(node, name, value):
    try:
        element = node.xpath("r25:%s" % name, namespaces=nsmap)[0]
    except IndexError:
        # create the element
        element = etree.SubElement(node, "{%s}%s" % (nsmap['r25'], name),
                                   nsmap=nsmap)

    if value is None or element.text == value:
        # no change
        return element

    logger.debug("changing %s from %s to %s" %
                 (element.getroottree().getpath(element), element.text, value))
    element.text = value

    # mark ancestors as modified
    while 'status' in node.attrib and node.attrib['status'] == 'est':
        node.attrib['status'] = 'mod'
        node = node.getparent()

    return element


# Adds a new element
def add_node(node, name):
    logger.debug("adding %s to %s" % (name, node.getroottree().getpath(node)))

    element = etree.SubElement(node, "{%s}%s" % (nsmap['r25'], name),
                               attrib={'status': 'new'}, nsmap=nsmap)

    # mark ancestors as modified
    while 'status' in node.attrib and node.attrib['status'] == 'est':
        node.attrib['status'] = 'mod'
        node = node.getparent()

    return element


def update_event(event):
    """
    Make changes to the given event
    :param event:
    :return:
    """

    if event.event_id is None:
        # Create event from scratch
        url = "events.xml"
        event_tree = post_resource(url)
        enode = event_tree.xpath("r25:event", namespaces=nsmap)[0]

        event.event_id = enode.xpath("r25:event_id", namespaces=nsmap)[0].text

        # initialize some things that aren't kept in the uw_r25 model
        update_value(enode, 'node_type', 'E')
        update_value(enode, 'event_type_id', '433')  # UWS Event

        onode = enode.xpath("r25:organization", namespaces=nsmap)[0]
        update_value(onode, 'organization_id', '4211')
        # update_value(onode, 'primary', 'T')

        # delete the blank profile
        pnode = enode.xpath("r25:profile", namespaces=nsmap)[0]
        enode.remove(pnode)

    else:
        url = "event.xml?event_id=%s&mode=edit" % event.event_id
        event_tree = get_resource(url)
        enode = event_tree.xpath("r25:event", namespaces=nsmap)[0]

    update_value(enode, 'alien_uid', event.alien_uid)
    update_value(enode, 'event_name', event.name)
    update_value(enode, 'event_title', event.title)
    update_value(enode, 'start_date', event.start_date)
    update_value(enode, 'end_date', event.end_date)
    update_value(enode, 'state', event.state)
    update_value(enode, 'parent_id', event.parent_id)
    update_value(enode, 'cabinet_id', event.cabinet_id)
    update_value(enode, 'cabinet_name', event.cabinet_name)
    # update_value(enode, 'event_type_id', event.event_type_id)

    for res in event.reservations:
        if res.reservation_id:
            # find existing profile
            xpath = \
                "r25:profile[./r25:reservation/r25:reservation_id = '%s']" % \
                res.reservation_id
            pnode = enode.xpath(xpath, namespaces=nsmap)[0]
            rnode = pnode.xpath("r25:reservation", namespaces=nsmap)[0]

        else:
            # add new profile and reservation
            pnode = add_node(enode, 'profile')
            rnode = add_node(pnode, 'reservation')

        update_value(pnode, 'profile_name', res.profile_name)
        update_value(pnode, 'init_start_dt', res.start_datetime)
        update_value(pnode, 'init_end_dt', res.end_datetime)

        update_value(rnode, 'reservation_start_dt', res.start_datetime)
        update_value(rnode, 'reservation_end_dt', res.end_datetime)
        update_value(rnode, 'reservation_state', res.state)

        if res.space_reservation is not None:
            try:
                srnode = rnode.xpath("r25:space_reservation",
                                     namespaces=nsmap)[0]
            except IndexError:
                srnode = add_node(rnode, 'space_reservation')

            update_value(srnode, 'space_id', res.space_reservation.space_id)

    # Make sure event dates encompass all reservations
    # for res in r25_event.reservations:
    #     res_start_date = res.start_datetime.split('T')[0]
    #     res_end_date = res.end_datetime.split('T')[0]
    #     if res_start_date < r25_event.start_date:
    #         r25_event.start_date = res_start_date.isoformat()
    #     if res_end_date > r25_event.end_date:
    #         r25_event.end_date = res_end_date

    if enode.attrib['status'] == 'est':
        logger.debug("Event unchanged")
        return event

    url = "event.xml?event_id=%s" % event.event_id

    return events_from_xml(put_resource(url, etree.tostring(event_tree)))[0]


def delete_event(event_id):
    url = "event.xml?event_id=%s" % event_id

    result = delete_resource(url)

    return result
