import logging

from django.conf import settings
from lxml import etree
from uw_r25 import nsmap, get_resource

from .more_r25 import put_resource


logger = logging.getLogger(__name__)


def update_get_space_ids(ems_rooms):
    """
    Get R25 space_ids for EMS Rooms.

    :param ems_rooms: A collection of ems_client.models.Room
    :return: A dictionary of Room.id: space_id
    """
    space_ids = {}
    for room in ems_rooms:
        if room.active and room.external_reference is not None:
            space_ids[room.id] = room.external_reference

    # while we're here, update the R25 saved search that we'll use
    query_url = "space_search.xml?query_id=%s" % settings.EMS_R25_SPACE_QUERY

    r25_query_tree = get_resource(query_url)

    snode = r25_query_tree.xpath("r25:search", namespaces=nsmap)[0]
    snode.attrib['status'] = 'mod'

    step = snode.xpath("r25:step", namespaces=nsmap)[0]
    step.attrib['status'] = 'del'

    query_modified = False

    found_space_ids = []
    for pnode in step.xpath("r25:step_param", namespaces=nsmap):
        space_id = pnode.xpath("r25:space_id", namespaces=nsmap)[0].text
        found_space_ids.append(space_id)
        pnode.attrib['status'] = 'del'

        if space_id not in space_ids.values():
            query_modified = True

    # replace with new search step
    step = etree.Element("{%s}step" % nsmap['r25'],
                         attrib={'status': 'new'})
    node = etree.Element("{%s}step_number" % nsmap['r25'])
    node.text = '1'
    step.append(node)
    node = etree.Element("{%s}step_type_id" % nsmap['r25'])
    node.text = '407'   # Spaces
    step.append(node)
    node = etree.Element("{%s}qualifier" % nsmap['r25'])
    node.text = '1'     # Include Any
    step.append(node)
    snode.append(step)

    step_param_nbr = 0
    for space_id in space_ids.values():
        step_param_nbr += 1
        param = etree.Element("{%s}step_param" % nsmap['r25'])
        node = etree.Element("{%s}step_param_nbr" % nsmap['r25'])
        node.text = str(step_param_nbr)
        param.append(node)
        node = etree.Element("{%s}space_id" % nsmap['r25'])
        node.text = space_id
        param.append(node)
        step.append(param)

        if space_id not in found_space_ids:
            query_modified = True

    if query_modified:
        put_resource(query_url, etree.tostring(r25_query_tree))

    return space_ids
