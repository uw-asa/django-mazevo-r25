from lxml import etree
from restclients_core.exceptions import DataFailureException
from uw_r25 import nsmap
from uw_r25.dao import R25_DAO


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


def create_new_event():
    """
    Return a blank occurrence with a new event ID that is used to create a new
    event
    """
    url = "events.xml"
    return post_resource(url)


def update_event(event_id, event):
    """
    Make changes to the given event
    :param event:
    :return:
    """
    url = "event.xml?event_id=%s" % event_id

    result = put_resource(url, etree.tostring(event))

    return result
