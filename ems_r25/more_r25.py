from six.moves.urllib.parse import urlencode

from lxml import etree
from restclients_core.exceptions import DataFailureException
from uw_r25 import nsmap, get_resource
from uw_r25.dao import R25_DAO
from uw_r25.events import events_from_xml
from uw_r25.models import Reservation
from uw_r25.spaces import space_reservation_from_xml


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
    if response.status != 200:
        raise DataFailureException(url, response.status, response.data)

    tree = etree.fromstring(response.data.strip())

    # XHTML response is an error response
    xhtml = tree.xpath("//xhtml:html", namespaces=nsmap)
    if len(xhtml):
        raise DataFailureException(url, 500, response.data)

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


def get_event_by_id_xml(event_id):
    url = "event.xml?event_id=%s" % event_id
    return get_resource(url)


def create_new_event():
    """
    Return a blank occurrence with a new event ID that is used to create a new
    event
    """
    url = "events.xml"
    return post_resource(url)


def update_event(event):
    """
    Make changes to the given event
    :param event:
    :return:
    """
    event_id = event.xpath("r25:event/r25:event_id", namespaces=nsmap)[0].text

    url = "event.xml?event_id=%s" % event_id

    return put_resource(url, etree.tostring(event))


def delete_event(event_id):
    url = "event.xml?event_id=%s" % event_id

    result = delete_resource(url)

    return result


def get_reservations_multi(**kwargs):
    """
    Return a list of reservations matching the passed filter.
    Supported kwargs are listed at
    http://knowledge25.collegenet.com/display/WSW/reservations.xml
    """
    kwargs["scope"] = "extended"
    url = "reservations.xml"
    if len(kwargs):
        url += "?%s" % urlencode(kwargs)

    return reservations_from_xml_multi(get_resource(url))


def reservations_from_xml_multi(tree):
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
        if profile_name:
            reservation.profile_name = profile_name
        else:
            reservation.profile_name = node.xpath("r25:profile_name",
                                                  namespaces=nsmap)[0].text

        reservation.space_reservations = []
        for pnode in node.xpath("r25:space_reservation", namespaces=nsmap):
            reservation.space_reservations.append(
                space_reservation_from_xml(pnode))

        try:
            enode = node.xpath("r25:event", namespaces=nsmap)[0]
            reservation.event_id = enode.xpath("r25:event_id",
                                               namespaces=nsmap)[0].text
            reservation.event_name = enode.xpath("r25:event_name",
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

        except IndexError:
            enode = tree.getparent()
            reservation.event_id = enode.xpath("r25:event_id",
                                               namespaces=nsmap)[0].text
            reservation.event_name = enode.xpath("r25:event_name",
                                                 namespaces=nsmap)[0].text

        reservations.append(reservation)

    return reservations
