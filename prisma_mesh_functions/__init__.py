#!/usr/bin/env python
"""
CGNX API -> Manage VPN Mesh

Aaron Edwards

"""
# standard modules
import argparse
import json
import logging
import time
import sys
import os

from . import sites, menus, vpn, anynets
from .utils import dump_version
from .versions import SCRIPT_VERSION, SCRIPT_NAME
from progressbar import Bar, ETA, Percentage, ProgressBar

# CloudGenix Python SDK
try:
    import cloudgenix
    jdout = cloudgenix.jdout
    jd = cloudgenix.jd
except ImportError as e:
    cloudgenix = None
    sys.stderr.write("ERROR: 'cloudgenix' python module required. (try 'pip install cloudgenix').\n {0}\n".format(e))
    sys.exit(1)

# Get AUTH_TOKEN/X_AUTH_TOKEN from env variable, if it exists. X_AUTH_TOKEN takes priority.
if "X_AUTH_TOKEN" in os.environ:
    CLOUDGENIX_AUTH_TOKEN = os.environ.get('X_AUTH_TOKEN')
elif "AUTH_TOKEN" in os.environ:
    CLOUDGENIX_AUTH_TOKEN = os.environ.get('AUTH_TOKEN')
else:
    # not set
    CLOUDGENIX_AUTH_TOKEN = None


# Global Vars
TIME_BETWEEN_API_UPDATES = 60       # seconds
REFRESH_LOGIN_TOKEN_INTERVAL = 7    # hours
CLOUDGENIX_VERSION = cloudgenix.version
__version__ = SCRIPT_VERSION
ARGS = {}
CGX_SESSION = cloudgenix.API()

# Set NON-SYSLOG logging to use function name
logger = logging.getLogger(__name__)

# Generic structure to keep authentication info

sdk_vars = {
    "load_list_a": None,            # Filename to load site list a
    "load_list_b": None,            # Filename to load site list b
    "load_wn_list_a": None,         # Filename to load wan network list a
    "load_wn_list_b": None,         # Filename to load wan network list b
    "reload_list_a": None,          # list of sites a to be used on re-loop of logic
    "reload_list_b": None,          # list of sites b to be used on re-loop of logic
    "reload_wn_list_a": None,       # list of WAN Networks a to be used on re-loop of logic
    "reload_wn_list_b": None,       # list of WAN Networks b to be used on re-loop of logic
    "loop_counter": 0               # Loop counter, arg files only loaded on first loop.
}


def siteid_to_name_dict(sdk_vars, sdk_session):
    """
    Create a Site ID <-> Name xlation constructs
    :param passed_sdk_vars: sdk_vars global info struct
    :return: xlate_dict, a dict with siteid key to site name. site_list, a list of site IDs
    """
    id_xlate_dict = {}
    name_xlate_dict = {}
    site_id_list = []
    site_name_list = []
    site_tags = {}
    site_id_to_role = {}

    resp = sdk_session.get.sites()
    status = resp.cgx_status
    raw_sites = resp.cgx_content

    sites_list = raw_sites.get('items', None)

    if not status or not sites_list:
        print("ERROR: unable to get sites for account '{0}'.".format(sdk_vars['tenant_name']))
        return {}, {}, [], []

    # build translation dict
    for site in sites_list:
        name = site.get('name')
        site_id = site.get('id')
        role = site.get('element_cluster_role')

        if name and site_id:
            id_xlate_dict[site_id] = name
            name_xlate_dict[name] = site_id
            site_id_list.append(site_id)
            site_name_list.append(name)
            if not site['tags']:
                site['tags'] = []
            site_tags[name] = site['tags']

        if site_id and role:
            site_id_to_role[site_id] = role

    return id_xlate_dict, name_xlate_dict, site_id_list, site_name_list, site_id_to_role, site_tags


def wannetworkid_to_name_dict(sdk_vars, sdk_session):
    """
    Create a Site ID <-> Name xlation constructs
    :param passed_sdk_vars: sdk_vars global info struct
    :return: xlate_dict, a dict with wannetworkid key to wan_network name. wan_network_list, a list of wan_network IDs
    """
    id_xlate_dict = {}
    name_xlate_dict = {}
    wan_network_id_list = []
    wan_network_name_list = []
    wan_network_id_type = {}

    resp = sdk_session.get.wannetworks()
    status = resp.cgx_status
    raw_wan_networks = resp.cgx_content

    wan_networks_list = raw_wan_networks.get('items', None)

    if not status or not wan_networks_list:
        print("ERROR: unable to get wan networks for account '{0}'.".format(sdk_vars['tenant_name']))
        return {}, {}, [], []

    # build translation dict
    for wan_network in wan_networks_list:
        name = wan_network.get('name')
        wan_network_id = wan_network.get('id')
        wn_type = wan_network.get('type')

        if name and wan_network_id:
            id_xlate_dict[wan_network_id] = name
            name_xlate_dict[name] = wan_network_id
            wan_network_id_list.append(wan_network_id)
            wan_network_name_list.append(name)

        if wan_network_id and wn_type:
            wan_network_id_type[wan_network_id] = wn_type

    return id_xlate_dict, name_xlate_dict, wan_network_id_list, wan_network_name_list, wan_network_id_type


def selective_loop_function():

    # check for initial launch
    if sdk_vars["loop_counter"] == 0:

        sdk_vars['load_list_a'] = ARGS['load_list_a']
        sdk_vars['load_list_b'] = ARGS['load_list_b']
        sdk_vars['load_wn_list_a'] = ARGS['load_wn_list_a']
        sdk_vars['load_wn_list_b'] = ARGS['load_wn_list_b']

        if ARGS["verbose"] == 1:
            logging.basicConfig(level=logging.INFO,
                                format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
            clilogger = logging.getLogger()
            clilogger.setLevel(logging.INFO,)
        elif ARGS["verbose"] >= 2:
            logging.basicConfig(level=logging.DEBUG,
                                format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
            clilogger = logging.getLogger()
            clilogger.setLevel(logging.DEBUG)
        else:
            # set logging off unless asked for
            pass

        # Log
        logger.debug("LOOP_COUNTER: {0}".format(sdk_vars["loop_counter"]))

        logger.info("Initial Launch:")

        # create file-system friendly tenant str.
        sdk_vars["tenant_str"] = "".join([x for x in CGX_SESSION.tenant_name if x.isalnum()]).lower()

        # load site lists for first run.
        if sdk_vars['load_list_a']:
            try:
                with open(sdk_vars['load_list_a']) as data_file:
                    data = json.load(data_file)
                site_list_a = data[:]
                print("\n Site List A:\n\tSuccessfully loaded {0} entries from {1}.".format(len(data), sdk_vars['load_list_a']))
            except (ValueError, IOError) as e:
                print("ERROR, Site List A: Could not load {0}: {1}.".format(sdk_vars['load_list_a'], e))
                site_list_a = []
        else:
            site_list_a = []

        if sdk_vars['load_list_b']:
            try:
                with open(sdk_vars['load_list_b']) as data_file:
                    data = json.load(data_file)
                site_list_b = data[:]
                print("\n Site List B:\n\tSuccessfully loaded {0} entries from {1}.".format(len(data), sdk_vars['load_list_b']))
            except (ValueError, IOError) as e:
                print("ERROR, Site List B: Could not load {0}: {1}.".format(sdk_vars['load_list_b'], e))
                site_list_b = []
        else:
            site_list_b = []

        # load wan network for first run.
        if sdk_vars['load_wn_list_a']:
            try:
                with open(sdk_vars['load_wn_list_a']) as data_file:
                    data = json.load(data_file)
                sdk_vars['reload_wn_list_a'] = data[:]
                print("\n Site WAN Network List A:\n\tSuccessfully loaded {0} entries from {1}.".format(len(data), sdk_vars['load_wn_list_a']))
            except (ValueError, IOError) as e:
                print("ERROR, Site WAN Network List A: Could not load {0}: {1}.".format(sdk_vars['load_wn_list_a'], e))
                sdk_vars['reload_wn_list_a'] = []
        else:
            sdk_vars['reload_wn_list_a'] = []

        if sdk_vars['load_wn_list_b']:
            try:
                with open(sdk_vars['load_wn_list_a']) as data_file:
                    data = json.load(data_file)
                sdk_vars['reload_wn_list_b'] = data[:]
                print("\n Site WAN Network List B:\n\t Successfully loaded {0} entries from {1}.".format(len(data), sdk_vars['load_wn_list_b']))
            except (ValueError, IOError) as e:
                print("ERROR, Site WAN Network List B: Could not load {0}: {1}.".format(sdk_vars['load_wn_list_b'], e))
                sdk_vars['reload_wn_list_b'] = []
        else:
            sdk_vars['reload_wn_list_b'] = []

    else:
        # re-loop, pull previous list out of sdk_vars dict.
        site_list_a = sdk_vars["reload_list_a"]
        site_list_b = sdk_vars["reload_list_b"]

    # Get/update list of sites, create python dictionary to map site ID to name.
    print("Caching all site information, please wait...")

    id_sitename_dict, sitename_id_dict, site_id_list, site_name_list, site_id_to_role_dict, site_tags \
        = siteid_to_name_dict(sdk_vars, CGX_SESSION)
    id_wan_network_name_dict, wan_network_name_id_dict, wan_network_id_list, wan_network_name_list, \
        wan_network_to_type_dict = wannetworkid_to_name_dict(sdk_vars, CGX_SESSION)

    logger.debug("SITE -> ROLE ({0}): {1}".format(len(site_id_to_role_dict),
                                                  json.dumps(site_id_to_role_dict, indent=4)))

    # Begin Site Selection Loop
    loop = True
    while loop:

        # Print header
        print("")
        sites.print_selection_overview(site_list_a, site_list_b, sitename_id_dict, site_id_to_role_dict)
        print("")

        action = [
            ("Edit Site List A", 'edit_sitelista'),
            ("Edit Site List B", 'edit_sitelistb'),
            ("Continue", 'continue')
        ]

        banner = "Select Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        list_name, selected_action = menus.quick_menu(banner, line_fmt, action)

        if selected_action == 'edit_sitelista':
            site_list_a = sites.edit_site_list(site_list_a, "Site List A", site_name_list, sdk_vars["tenant_str"],
                                               site_tags)
        elif selected_action == 'edit_sitelistb':
            site_list_b = sites.edit_site_list(site_list_b, "Site List B", site_name_list, sdk_vars["tenant_str"],
                                               site_tags)
        elif selected_action == "continue":
            if (len(site_list_a) < 1) or (len(site_list_b) < 1):
                print("\nERROR, must select at least one site in each list.")
            else:
                # Good to go, continue.
                loop = False
        else:
            CGX_SESSION.interactive.logout()
            sys.exit()

    # save lists for re-use next loop.
    sdk_vars["reload_list_a"] = site_list_a
    sdk_vars["reload_list_b"] = site_list_b

    # sites selected, determine if this will be Internet or VPNoMPLS mesh
    action = [
        ("Internet VPN (Public)", 'publicwan'),
        ("Private WAN VPN (Private, VPN over MPLS)", 'privatewan'),
    ]

    banner = "Managing which type of VPN mesh:"
    line_fmt = "{0}: {1}"

    mesh_type = menus.quick_menu(banner, line_fmt, action)[1]

    # map type-specific anynet based on choice above
    anynet_specific_type = 'anynet'
    if mesh_type in ['privatewan']:
        anynet_specific_type = "private-anynet"
    elif mesh_type in ['publicwan']:
        anynet_specific_type = "public-anynet"

    # convert site lists (by name) to ID lists. Look up ID in previous sitename_id dict. if exists, enter.
    site_id_list_a = []
    for site in site_list_a:
        site_id = sitename_id_dict.get(site, None)
        if site_id:
            site_id_list_a.append(site_id)

    site_id_list_b = []
    for site in site_list_b:
        site_id = sitename_id_dict.get(site, None)
        if site_id:
            site_id_list_b.append(site_id)

    # combine site lists and remove duplicates so we can pull topology info from API once per site.
    combined_site_id_list = list(site_id_list_a)
    combined_site_id_list.extend(x for x in site_id_list_b if x not in site_id_list_a)

    # print json.dumps(combined_site_id_list, indent=4)

    # get/update topology

    print("Loading VPN topology information for {0} sites, please wait...".format(len(combined_site_id_list)))

    logger.debug('COMBINED_SITE_ID_LIST ({0}): {1}'.format(len(combined_site_id_list),
                                                           json.dumps(combined_site_id_list, indent=4)))

    swi_to_wan_network_dict = {}
    swi_to_site_dict = {}
    wan_network_to_swi_dict = {}
    all_anynets = {}
    site_swi_dict = {}

    # could be a long query - start a progress bar.
    pbar = ProgressBar(widgets=[Percentage(), Bar(), ETA()], max_value=len(combined_site_id_list)+1).start()
    site_processed = 1

    for site in combined_site_id_list:
        site_swi_list = []

        query = {
            "type": "basenet",
            "nodes": [
                site
            ]
        }

        status = False
        rest_call_retry = 0

        while not status:
            resp = CGX_SESSION.post.topology(query)
            status = resp.cgx_status
            topology = resp.cgx_content

            if not status:
                print("API request for topology for site ID {0} failed/timed out. Retrying.".format(site))
                rest_call_retry += 1
                # have we hit retry limit?
                if rest_call_retry >= sdk_vars['rest_call_max_retry']:
                    # Bail out
                    print("ERROR: could not query site ID {0}. Continuing.".format(site))
                    status = True
                    topology = False
                else:
                    # wait and keep going.
                    time.sleep(1)

        if status and topology:
            # iterate topology. We need to iterate all of the matching SWIs, and existing anynet connections (sorted).
            logger.debug("TOPOLOGY: {0}".format(json.dumps(topology, indent=4)))

            for link in topology.get('links', []):
                link_type = link.get('type', "")

                # if an anynet link (SWI to SWI)
                if link_type in ["anynet", anynet_specific_type]:
                    # vpn record, check for uniqueness.
                    # 4.4.1
                    source_swi = link.get('source_wan_if_id')
                    if not source_swi:
                        # 4.3.x compatibility
                        source_swi = link.get('source_wan_path_id')
                        if source_swi:
                            link['source_wan_if_id'] = source_swi
                    # 4.4.1
                    dest_swi = link.get('target_wan_if_id')
                    if not dest_swi:
                        # 4.3.x compatibility
                        dest_swi = link.get('target_wan_path_id')
                        if dest_swi:
                            link['target_wan_if_id'] = dest_swi
                    # create anynet lookup key
                    anynet_lookup_key = "_".join(sorted([source_swi, dest_swi]))
                    if not all_anynets.get(anynet_lookup_key, None):
                        # path is not in current anynets, add
                        all_anynets[anynet_lookup_key] = link

        # Query 2 - now need to query SWI for site, since stub-topology may not be in topology info.
        status = False

        while not status:
            resp = CGX_SESSION.get.waninterfaces(site)
            status = resp.cgx_status
            site_wan_if_result = resp.cgx_content

            if not status:
                print("API request for Site WAN Interfaces for site ID {0} failed/timed out. Retrying.".format(site))
                time.sleep(1)

        if status and site_wan_if_result:
            site_wan_if_items = site_wan_if_result.get('items', [])
            logger.debug('SITE WAN IF ITEMS ({0}): {1}'.format(len(site_wan_if_items),
                                                               json.dumps(site_wan_if_items, indent=4)))

            # iterate all the site wan interfaces
            for current_swi in site_wan_if_items:
                # get the WN bound to the SWI.
                wan_network_id = current_swi.get('network_id', "")
                swi_id = current_swi.get('id', "")

                if swi_id:
                    # update SWI -> Site xlation dict
                    swi_to_site_dict[swi_id] = site

                # get the SWIs that match the mesh_type
                if wan_network_id and swi_id and wan_network_to_type_dict.get(wan_network_id, "") == mesh_type:
                    logger.debug('SWI_ID = SITE: {0} = {1}'.format(swi_id, site))

                    # query existing wan_network_to_swi dict if entry exists.
                    existing_swi_list = wan_network_to_swi_dict.get(wan_network_id, [])

                    # update swi -> WN xlate dict
                    swi_to_wan_network_dict[swi_id] = wan_network_id

                    # update site-level SWI list.
                    site_swi_list.append(swi_id)

                    # update WN -> swi xlate dict
                    existing_swi_list.append(swi_id)
                    wan_network_to_swi_dict[wan_network_id] = existing_swi_list

        # add all matching mesh_type stubs to site_swi_dict
        site_swi_dict[site] = site_swi_list

        # iterate bar and counter.
        site_processed += 1
        pbar.update(site_processed)

    # finish after iteration.
    pbar.finish()

    # update all_anynets with site info. Can't do this above, because xlation table not finished when needed.
    for anynet_key, link in all_anynets.items():
        # 4.4.1
        source_swi = link.get('source_wan_if_id')
        if not source_swi:
            # 4.3.x compatibility
            source_swi = link.get('source_wan_path_id')
        # 4.4.1
        dest_swi = link.get('target_wan_if_id')
        if not dest_swi:
            # 4.3.x compatibility
            dest_swi = link.get('target_wan_path_id')
        link['source_site_id'] = swi_to_site_dict.get(source_swi, 'UNKNOWN (Unable to map SWI to Site ID)')
        link['target_site_id'] = swi_to_site_dict.get(dest_swi, 'UNKNOWN (Unable to map SWI to Site ID)')

    logger.debug("SWI -> WN xlate ({0}): {1}".format(len(swi_to_wan_network_dict),
                                               json.dumps(swi_to_wan_network_dict, indent=4)))
    logger.debug("All Anynets ({0}): {1}".format(len(all_anynets),
                                                     json.dumps(all_anynets, indent=4)))
    logger.debug("SWI construct ({0}): {1}".format(len(site_swi_dict),
                                                   json.dumps(site_swi_dict, indent=4)))
    logger.debug("WN xlate ({0}): {1}".format(len(wan_network_to_swi_dict),
                                              json.dumps(wan_network_to_swi_dict, indent=4)))
    logger.debug("SWI -> SITE xlate ({0}): {1}".format(len(swi_to_site_dict),
                                              json.dumps(swi_to_site_dict, indent=4)))

    new_anynets, current_anynets = vpn.main_vpn_menu(site_id_list_a,
                                                     site_id_list_b,
                                                     all_anynets,
                                                     site_swi_dict,
                                                     swi_to_wan_network_dict,
                                                     wan_network_to_swi_dict,
                                                     id_wan_network_name_dict,
                                                     wan_network_name_id_dict,
                                                     swi_to_site_dict,
                                                     id_sitename_dict,
                                                     mesh_type,
                                                     site_id_to_role_dict, sdk_vars=sdk_vars, sdk_session=CGX_SESSION)

    reload_or_exit = anynets.main_anynet_menu(new_anynets,
                                              current_anynets,
                                              site_swi_dict,
                                              swi_to_wan_network_dict,
                                              wan_network_to_swi_dict,
                                              id_wan_network_name_dict,
                                              wan_network_name_id_dict,
                                              swi_to_site_dict,
                                              id_sitename_dict,
                                              mesh_type,
                                              site_id_to_role_dict,
                                              sdk_vars, CGX_SESSION)

    # Increment global loop counter
    sdk_vars["loop_counter"] += 1

    return reload_or_exit


def allchange_loop_function(operation):
    """
    For enable Full Mesh or Disable Full Mesh (HUB/SPOKE)
    :param operation: The operation string, one of 'create_n' (Full Mesh) 'delete_c' (hub/spoke)
    :return:
    """

    if ARGS["verbose"] == 1:
        logging.basicConfig(level=logging.INFO,
                            format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
        clilogger = logging.getLogger()
        clilogger.setLevel(logging.INFO,)
    elif ARGS["verbose"] >= 2:
        logging.basicConfig(level=logging.DEBUG,
                            format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
        clilogger = logging.getLogger()
        clilogger.setLevel(logging.DEBUG)
    else:
        # set logging off unless asked for
        pass

    # Get/update list of sites, create python dictionary to map site ID to name.
    id_sitename_dict, sitename_id_dict, site_id_list, site_name_list, site_id_to_role_dict, site_tags \
        = siteid_to_name_dict(sdk_vars, CGX_SESSION)
    id_wan_network_name_dict, wan_network_name_id_dict, wan_network_id_list, wan_network_name_list, \
        wan_network_to_type_dict = wannetworkid_to_name_dict(sdk_vars, CGX_SESSION)

    logger.debug("SITE -> ROLE ({0}): {1}".format(len(site_id_to_role_dict),
                                                  json.dumps(site_id_to_role_dict, indent=4)))

    # Begin Site Selection - Full mesh is easy - all sites all wans.
    site_list_a = site_name_list[:]
    site_list_b = site_name_list[:]
    # TODO count site types here.

    # we need to process for both public and private WANs.
    anynet_specific_type_pub = "public-anynet"
    anynet_specific_type_priv = "private-anynet"

    # convert site lists (by name) to ID lists. Look up ID in previous sitename_id dict. if exists, enter.
    site_id_list_a = []
    for site in site_list_a:
        site_id = sitename_id_dict.get(site, None)
        if site_id:
            site_id_list_a.append(site_id)

    site_id_list_b = []
    for site in site_list_b:
        site_id = sitename_id_dict.get(site, None)
        if site_id:
            site_id_list_b.append(site_id)

    # combine site lists and remove duplicates so we can pull topology info from API once per site.
    combined_site_id_list = list(site_id_list_a)
    combined_site_id_list.extend(x for x in site_id_list_b if x not in site_id_list_a)

    # print json.dumps(combined_site_id_list, indent=4)

    # get/update topology

    print("Loading VPN topology information for {0} sites, please wait.".format(len(combined_site_id_list)))

    logger.debug('COMBINED_SITE_ID_LIST ({0}): {1}'.format(len(combined_site_id_list),
                                                           json.dumps(combined_site_id_list, indent=4)))

    swi_to_wan_network_dict = {}
    swi_to_site_dict = {}
    wan_network_to_swi_dict = {}
    all_anynets_pub = {}
    all_anynets_priv = {}
    site_swi_dict_pub = {}
    site_swi_dict_priv = {}

    # could be a long query - start a progress bar.
    pbar = ProgressBar(widgets=[Percentage(), Bar(), ETA()], max_value=len(combined_site_id_list)+1).start()
    site_processed = 1

    for site in combined_site_id_list:
        site_swi_list_pub = []
        site_swi_list_priv = []

        query = {
            "type": "basenet",
            "nodes": [
                site
            ]
        }

        status = False
        rest_call_retry = 0
        topology = None

        while not status:
            resp = CGX_SESSION.post.topology(query)
            status = resp.cgx_status
            topology = resp.cgx_content

            if not status:
                print("API request for topology for site ID {0} failed/timed out. Retrying.".format(site))
                rest_call_retry += 1
                # have we hit retry limit?
                if rest_call_retry >= sdk_vars['rest_call_max_retry']:
                    # Bail out
                    print("ERROR: could not query site ID {0}. Continuing.".format(site))
                    status = True
                    topology = False
                else:
                    # wait and keep going.
                    time.sleep(1)

        if status and topology:
            # iterate topology. We need to iterate all of the matching SWIs, and existing anynet connections (sorted).
            logger.debug("TOPOLOGY: {0}".format(json.dumps(topology, indent=4)))

            for link in topology.get('links', []):
                link_type = link.get('type', "")

                # if an anynet link (SWI to SWI)
                if link_type in [anynet_specific_type_pub, anynet_specific_type_priv]:
                    # vpn record, check for uniqueness.
                    # 4.4.1
                    source_swi = link.get('source_wan_if_id')
                    if not source_swi:
                        # 4.3.x compatibility
                        source_swi = link.get('source_wan_path_id')
                        if source_swi:
                            link['source_wan_if_id'] = source_swi
                    # 4.4.1
                    dest_swi = link.get('target_wan_if_id')
                    if not dest_swi:
                        # 4.3.x compatibility
                        dest_swi = link.get('target_wan_path_id')
                        if dest_swi:
                            link['target_wan_if_id'] = dest_swi
                    # create anynet lookup key
                    anynet_lookup_key = "_".join(sorted([source_swi, dest_swi]))
                    if link_type in [anynet_specific_type_pub]:
                        if not all_anynets_pub.get(anynet_lookup_key, None):
                            # path is not in current anynets, add
                            all_anynets_pub[anynet_lookup_key] = link
                    elif link_type in [anynet_specific_type_priv]:
                        if not all_anynets_priv.get(anynet_lookup_key, None):
                            # path is not in current anynets, add
                            all_anynets_priv[anynet_lookup_key] = link

        # Query 2 - now need to query SWI for site, since stub-topology may not be in topology info.
        status = False
        site_wan_if_result = False

        while not status:
            resp = CGX_SESSION.get.waninterfaces(site)
            status = resp.cgx_status
            site_wan_if_result = resp.cgx_content

            if not status:
                print("API request for Site WAN Interfaces for site ID {0} failed/timed out. Retrying.".format(site))
                time.sleep(1)

        if status and site_wan_if_result:
            site_wan_if_items = site_wan_if_result.get('items', [])
            logger.debug('SITE WAN IF ITEMS ({0}): {1}'.format(len(site_wan_if_items),
                                                               json.dumps(site_wan_if_items, indent=4)))

            # iterate all the site wan interfaces
            for current_swi in site_wan_if_items:
                # get the WN bound to the SWI.
                wan_network_id = current_swi.get('network_id', "")
                swi_id = current_swi.get('id', "")

                if swi_id:
                    # update SWI -> Site xlation dict
                    swi_to_site_dict[swi_id] = site

                # get the SWIs that match the mesh_type
                if wan_network_id and swi_id and wan_network_to_type_dict.get(wan_network_id, "") in ['publicwan',
                                                                                                      'privatewan']:
                    logger.debug('SWI_ID = SITE: {0} = {1}'.format(swi_id, site))

                    # query existing wan_network_to_swi dict if entry exists.
                    existing_swi_list = wan_network_to_swi_dict.get(wan_network_id, [])

                    # update swi -> WN xlate dict
                    swi_to_wan_network_dict[swi_id] = wan_network_id

                    # update site-level SWI list.
                    if wan_network_to_type_dict.get(wan_network_id, "") == 'publicwan':
                        site_swi_list_pub.append(swi_id)
                    elif wan_network_to_type_dict.get(wan_network_id, "") == 'privatewan':
                        site_swi_list_priv.append(swi_id)

                    # update WN -> swi xlate dict
                    existing_swi_list.append(swi_id)
                    wan_network_to_swi_dict[wan_network_id] = existing_swi_list

        # add all matching mesh_type stubs to site_swi_dict
        site_swi_dict_pub[site] = site_swi_list_pub
        site_swi_dict_priv[site] = site_swi_list_priv

        # iterate bar and counter.
        site_processed += 1
        pbar.update(site_processed)

    # finish after iteration.
    pbar.finish()

    # update all_anynets with site info. Can't do this above, because xlation table not finished when needed.
    for anynet_key, link in all_anynets_pub.items():
        source_swi = link.get('source_wan_if_id')
        dest_swi = link.get('target_wan_if_id')
        link['source_site_id'] = swi_to_site_dict.get(source_swi, 'UNKNOWN (Unable to map SWI to Site ID)')
        link['target_site_id'] = swi_to_site_dict.get(dest_swi, 'UNKNOWN (Unable to map SWI to Site ID)')

    for anynet_key, link in all_anynets_priv.items():
        source_swi = link.get('source_wan_if_id')
        dest_swi = link.get('target_wan_if_id')
        link['source_site_id'] = swi_to_site_dict.get(source_swi, 'UNKNOWN (Unable to map SWI to Site ID)')
        link['target_site_id'] = swi_to_site_dict.get(dest_swi, 'UNKNOWN (Unable to map SWI to Site ID)')

    logger.debug("SWI -> WN xlate ({0}): {1}".format(len(swi_to_wan_network_dict),
                                               json.dumps(swi_to_wan_network_dict, indent=4)))
    logger.debug("All Anynets Pub ({0}): {1}".format(len(all_anynets_pub),
                                                     json.dumps(all_anynets_pub, indent=4)))
    logger.debug("All Anynets Pub ({0}): {1}".format(len(all_anynets_priv),
                                                     json.dumps(all_anynets_priv, indent=4)))
    logger.debug("SWI construct Pub ({0}): {1}".format(len(site_swi_dict_pub),
                                                       json.dumps(site_swi_dict_pub, indent=4)))
    logger.debug("SWI construct Priv ({0}): {1}".format(len(site_swi_dict_priv),
                                                        json.dumps(site_swi_dict_priv, indent=4)))
    logger.debug("WN xlate ({0}): {1}".format(len(wan_network_to_swi_dict),
                                              json.dumps(wan_network_to_swi_dict, indent=4)))
    logger.debug("SWI -> SITE xlate ({0}): {1}".format(len(swi_to_site_dict),
                                              json.dumps(swi_to_site_dict, indent=4)))

    new_anynets_pub, current_anynets_pub = vpn.no_menu_all_links(site_id_list_a,
                                                                 site_id_list_b,
                                                                 all_anynets_pub,
                                                                 site_swi_dict_pub,
                                                                 swi_to_wan_network_dict,
                                                                 wan_network_to_swi_dict,
                                                                 id_wan_network_name_dict,
                                                                 wan_network_name_id_dict,
                                                                 swi_to_site_dict,
                                                                 id_sitename_dict,
                                                                 'publicwan',
                                                                 site_id_to_role_dict,
                                                                 sdk_vars=sdk_vars, sdk_session=CGX_SESSION)

    new_anynets_priv, current_anynets_priv = vpn.no_menu_all_links(site_id_list_a,
                                                                   site_id_list_b,
                                                                   all_anynets_priv,
                                                                   site_swi_dict_priv,
                                                                   swi_to_wan_network_dict,
                                                                   wan_network_to_swi_dict,
                                                                   id_wan_network_name_dict,
                                                                   wan_network_name_id_dict,
                                                                   swi_to_site_dict,
                                                                   id_sitename_dict,
                                                                   'privatewan',
                                                                   site_id_to_role_dict,
                                                                   sdk_vars=sdk_vars, sdk_session=CGX_SESSION)

    reload_or_exit = anynets.main_anynet_nomenu_just_do(new_anynets_pub,
                                                        current_anynets_pub,
                                                        new_anynets_priv,
                                                        current_anynets_priv,
                                                        operation,
                                                        swi_to_wan_network_dict,
                                                        id_wan_network_name_dict,
                                                        id_sitename_dict,
                                                        site_id_to_role_dict,
                                                        sdk_vars, CGX_SESSION)

    return reload_or_exit


def go():
    global ARGS
    global CGX_SESSION
    """
    Stub script entry point. Authenticates CloudGenix SDK, and gathers options from command line to run do_site()
    :return: No return
    """

    # Parse arguments
    parser = argparse.ArgumentParser(description="Create or Destroy site from YAML config file.")

    # Allow Controller modification and debug level sets.
    controller_group = parser.add_argument_group('API', 'These options change how this program connects to the API.')
    controller_group.add_argument("--controller", "-C",
                                  help="Controller URI, ex. https://api.elcapitan.cloudgenix.com",
                                  default=None)

    login_group = parser.add_argument_group('Login', 'These options allow skipping of interactive login')
    login_group.add_argument("--email", "-E", help="Use this email as User Name instead of cloudgenix_settings.py "
                                                   "or prompting",
                             default=None)
    login_group.add_argument("--password", "-PW", help="Use this Password instead of cloudgenix_settings.py "
                                                       "or prompting",
                             default=None)
    login_group.add_argument("--insecure", "-I", help="Do not verify SSL certificate",
                             action='store_true',
                             default=False)
    login_group.add_argument("--noregion", "-NR", help="Ignore Region-based redirection.",
                             dest='ignore_region', action='store_true', default=False)

    debug_group = parser.add_argument_group('Debug', 'These options enable debugging output')
    debug_group.add_argument("--verbose", "-V", help="Verbosity of script output, levels 0-3", type=int,
                             default=1)
    debug_group.add_argument("--sdkdebug", "-D", help="Enable SDK Debug output, levels 0-2", type=int,
                             default=0)
    debug_group.add_argument("--version", help="Dump Version(s) of script and modules and exit.", action='version',
                             version=dump_version())
    vpn_group = parser.add_argument_group('VPN', 'These options modify starting lists/other items.')
    vpn_group.add_argument("--load-list-a", "-LA", help="JSON file containing Site List A", default=False)
    vpn_group.add_argument("--load-list-b", "-LB", help="JSON file containing Site List B", default=False)
    vpn_group.add_argument("--load-wn-list-a", "-WA", help="JSON file containing Wan Network List A", default=False)
    vpn_group.add_argument("--load-wn-list-b", "-WB", help="JSON file containing Wan Network List B", default=False)

    ARGS = vars(parser.parse_args())

    # set verbosity and SDK debug
    debuglevel = ARGS["verbose"]
    sdk_debuglevel = ARGS["sdkdebug"]

    # Build SDK Constructor
    if ARGS['controller'] and ARGS['insecure']:
        CGX_SESSION = cloudgenix.API(controller=ARGS['controller'], ssl_verify=False)
    elif ARGS['controller']:
        CGX_SESSION = cloudgenix.API(controller=ARGS['controller'])
    elif ARGS['insecure']:
        CGX_SESSION = cloudgenix.API(ssl_verify=False)
    else:
        CGX_SESSION = cloudgenix.API()

    # check for region ignore
    if ARGS['ignore_region']:
        CGX_SESSION.ignore_region = True

    # Verbosity, default = 1.
    # 0 = no output
    # 1 = print status messages
    # 2 = print info messages
    # 3 = print debug

    # SDK debug, default = 0
    # 0 = logger handlers removed, critical only
    # 1 = logger info messages
    # 2 = logger debug messages.

    if sdk_debuglevel == 1:
        # info msgs, CG SDK info
        logging.basicConfig(level=logging.INFO,
                            format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
        logger.setLevel(logging.INFO)
        CGX_SESSION.set_debug(1)
    elif sdk_debuglevel >= 2:
        # debug msgs, CG SDK debug
        logging.basicConfig(level=logging.DEBUG,
                            format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s")
        logger.setLevel(logging.DEBUG)
        CGX_SESSION.set_debug(2)

    else:
        # Remove all handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        # set logging level to default
        logger.setLevel(logging.WARNING)

    # login logic. Use cmdline if set, use AUTH_TOKEN next, finally user/pass from config file, then prompt.
    # figure out user
    if ARGS["email"]:
        user_email = ARGS["email"]
    else:
        user_email = None

    # figure out password
    if ARGS["password"]:
        user_password = ARGS["password"]
    else:
        user_password = None

    # import pdb; pdb.set_trace()
    # check for token
    if CLOUDGENIX_AUTH_TOKEN and not ARGS["email"] and not ARGS["password"]:
        CGX_SESSION.interactive.use_token(CLOUDGENIX_AUTH_TOKEN)
        if CGX_SESSION.tenant_id is None:
            CGX_SESSION.throw_error("AUTH_TOKEN login failure, please check token.")

    else:
        print("{0} v{1} ({2})\n".format(SCRIPT_NAME, SCRIPT_VERSION, CGX_SESSION.controller))
        while CGX_SESSION.tenant_id is None:
            CGX_SESSION.interactive.login(user_email, user_password)
            # clear after one failed login, force relogin.
            if not CGX_SESSION.tenant_id:
                user_email = None
                user_password = None

    # Begin meshing loop
    loop = True
    while loop:

        # Print header
        print("")

        action = [
            ("Full Mesh", 'full_mesh'),
            ("Partial/Selective Mesh", 'selective_mesh'),
            ("Hub/Spoke Links Only", 'hub_spoke')
        ]

        banner = "Choose Prisma SD-WAN Network Meshing Stance:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        list_name, selected_action = menus.quick_menu(banner, line_fmt, action)

        if selected_action == 'full_mesh':
            # do full mesh then exit.
            print("\nChecking network state before moving to Full Mesh.")
            allchange_loop_function('create_n')
            sys.exit()

        elif selected_action == 'selective_mesh':
            print("\nStarting Interactive Mesh Modification.")
            # start main loop for selective mesh
            main_loop = True
            while main_loop:
                main_loop = selective_loop_function()

        elif selected_action == "hub_spoke":
            # do Hub/Spoke then exit.
            print("\nChecking network state before moving to Hub/Spoke only.")
            allchange_loop_function('delete_c')
            sys.exit()

        else:
            CGX_SESSION.interactive.logout()
            sys.exit()


# Start
if __name__ == "__main__":
    go()
