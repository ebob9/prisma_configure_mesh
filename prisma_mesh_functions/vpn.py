#!/usr/bin/env python

import json
import copy
import re
import os
import sys
import logging
from .utils import re_pick, stat_inc
from . import menus

# Set NON-SYSLOG logging to use function name
logger = logging.getLogger(__name__)


def mesh_name(mesh_type):

    mesh_text = "<UNKNOWN>"

    if mesh_type in ["publicwan"]:
        mesh_text = "Internet VPN"
    elif mesh_type in ["privatewan"]:
        mesh_text = "Private VPN (VPN over MPLS)"

    return mesh_text


def print_selection_overview(statistics, site_a_wan_networks, site_b_wan_networks):
    """
    Function to print the VPN Stats
    :param statistics: Statistics dict returned from calculate_vpn_links()
    :param site_a_wan_networks: list of List A WAN networks
    :param site_b_wan_networks: list of LIST B WAN Networks
    :return: empty - just prints.
    """

    print('\t{:>20}  {:>20}'.format('List A', 'List B'))
    print('\tSites: {:>13}  Sites: {:>13}'.format(statistics['sites_lista'], statistics['sites_listb']))
    print('\tSite WAN Ifs: {:>6}  Site WAN Ifs: {:>6}'.format(statistics['swi_lista'], statistics['swi_listb']))
    print('\tWAN Networks: {:>6}  WAN Networks: {:>6}'.format(len(site_a_wan_networks), len(site_b_wan_networks)))
    print('')
    print('\tVPN Mesh Statistics      COUNT (ALWAYS-ON/MODIFIABLE/    OTHER))')
    print('\t Current Mesh Links: {:>9} ({:>9}/{:>10}/{:>9}))'.format(statistics['current_anynets'],
                                                                    statistics['sub_always'],
                                                                    statistics['sub_demand'],
                                                                    statistics['sub_other'],))
    print('\t                 Up: {:>9} ({:>9}/{:>10}/{:>9}))'.format(statistics['up_anynets_always'] +
                                                                    statistics['up_anynets_demand'] +
                                                                    statistics['up_anynets_other'],
                                                                    statistics['up_anynets_always'],
                                                                    statistics['up_anynets_demand'],
                                                                    statistics['up_anynets_other']))
    print('\t               Init: {:>9} ({:>9}/{:>10}/{:>9}))'.format(statistics['init_anynets_always'] +
                                                                    statistics['init_anynets_demand'] +
                                                                    statistics['init_anynets_other'],
                                                                    statistics['init_anynets_always'],
                                                                    statistics['init_anynets_demand'],
                                                                    statistics['init_anynets_other']))
    print('\t              Other: {:>9} ({:>9}/{:>10}/{:>9}))'.format(statistics['other_anynets_always'] +
                                                                    statistics['other_anynets_demand'] +
                                                                    statistics['other_anynets_other'],
                                                                    statistics['other_anynets_always'],
                                                                    statistics['other_anynets_demand'],
                                                                    statistics['other_anynets_other']))
    print('\t               Down: {:>9} ({:>9}/{:>10}/{:>9}))'.format(statistics['down_anynets_always'] +
                                                                    statistics['down_anynets_demand'] +
                                                                    statistics['down_anynets_other'],
                                                                    statistics['down_anynets_always'],
                                                                    statistics['down_anynets_demand'],
                                                                    statistics['down_anynets_other']))
    print('\t     Admin Disabled: {:>9} ({:>9}/{:>10}/{:>9}))'.format(statistics['admindown_anynets_always'] +
                                                                    statistics['admindown_anynets_demand'] +
                                                                    statistics['admindown_anynets_other'],
                                                                    statistics['admindown_anynets_always'],
                                                                    statistics['admindown_anynets_demand'],
                                                                    statistics['admindown_anynets_other']))
    print('')
    print('\tNew MODIFIABLE links needed to full Mesh: {:>5}'.format(statistics['needed_anynets']))

    return


def get_unique_wan_networks_from_swi_dict(swi_dict, swi_to_wn_dict, id_wan_network_name_dict):
    """
    Takes Site-SWI list dict and translates them to WAN network names, returns list with unique entries.
    :param swi_dict: Site-SWI list in format { '<siteid>': ['<SWI1>', '<SWI2>', ...] }
    :param swi_to_wn_dict: xlation dict of SWI ID to WN ID format { '<swi_id': '<wn_id>'}
    :param id_wan_network_name_dict: xlation dict of WN ID to Name { '<wn_id>': 'WAN Network name'}
    :return: list of unique WAN network names from swi_dict
    """

    wan_network_name_list = []

    # iterate to the SWI, map SWI to name, add to list.
    for siteid, swi_list in swi_dict.items():
        for site_wan_interface in swi_list:
            wan_network_id = swi_to_wn_dict.get(site_wan_interface, None)
            if wan_network_id:
                wan_network_name = id_wan_network_name_dict.get(wan_network_id, None)
                if wan_network_name:
                    wan_network_name_list.append(wan_network_name)

    # remove duplicates by casting to set and back to list.
    return list(set(wan_network_name_list))


def site_swi_dicts(siteid_list_a, siteid_list_b, site_swi_all_dict):
    """
    Two list of sites, return site-swi dict for each with site-swi only matching those lists.
    :param siteid_list_a: List A of site ids.
    :param siteid_list_b: List B of site ids
    :param site_swi_all_dict: Dict of siteid -> SWI mapping that contains ALL sites in siteid_list_a and
                              siteid_list_b, in format { '<siteid>': ['<SWI1>', '<SWI2>', ...] }
    :return: site-swi dict for list a, site-swi dict for list b
    """

    a_dict = {}
    b_dict = {}

    for siteid in siteid_list_a:
        entry = site_swi_all_dict.get(siteid, None)
        if entry:
            a_dict[siteid] = entry

    for siteid in siteid_list_b:
        entry = site_swi_all_dict.get(siteid, None)
        if entry:
            b_dict[siteid] = entry

    return a_dict, b_dict


def calculate_vpn_links(site_a_swi_dict, site_b_swi_dict, all_anynets, swi_to_site_dict, site_id_to_role_dict):
    """
    Function to take site swi dicts, current anynets, and calculate stats and new anynets needed.
    :param site_a_swi_dict: Site-SWI dict for list A format { '<siteid>': ['<SWI1>', '<SWI2>', ...] }
    :param site_b_swi_dict: Site-SWI dict for list B format { '<siteid>': ['<SWI1>', '<SWI2>', ...] }
    :param all_anynets: Current Anynet list (with standard topology info + SITE id fields added)
    :param swi_to_site_dict: xlation SWI to SiteID mapping format { '<swi_id>': '<siteid>' }
    :return: tuple with - new_anynets: new anynets list in similar format to all_anynets.
                           statistics: Dict with statistics on VPN Mesn/Anynets
    """

    calculated_anynets = {}
    current_anynets = {}
    counted_sitea = {}
    counted_siteb = {}
    counted_swia = {}
    counted_swib = {}

    new_anynets = {}
    statistics = {
        'current_anynets': 0,
        'needed_anynets': 0,
        'sub_always': 0,
        'sub_demand': 0,
        'sub_other': 0,
        'up_anynets_always': 0,
        'down_anynets_always': 0,
        'admindown_anynets_always': 0,
        'init_anynets_always': 0,
        'other_anynets_always': 0,
        'up_anynets_demand': 0,
        'down_anynets_demand': 0,
        'admindown_anynets_demand': 0,
        'init_anynets_demand': 0,
        'other_anynets_demand': 0,
        'up_anynets_other': 0,
        'down_anynets_other': 0,
        'admindown_anynets_other': 0,
        'init_anynets_other': 0,
        'other_anynets_other': 0,
        'sites_lista': 0,
        'swi_lista': 0,
        'sites_listb': 0,
        'swi_listb': 0
    }

    # recurse every possible site a swi -> site b swi relationship
    for siteid_a, swi_list_a in site_a_swi_dict.items():
        logger.info("SITEID A: {0}".format(siteid_a))
        if not counted_sitea.get(siteid_a, False):
            logger.info("NEW SITEA: {0}".format(siteid_a))
            stat_inc(statistics, 'sites_lista')
            counted_sitea[siteid_a] = True

        for swi_a in swi_list_a:
            if not counted_swia.get(swi_a, False):
                logger.info("NEW SWIA: {0}".format(swi_a))
                stat_inc(statistics, 'swi_lista')
                counted_swia[swi_a] = True

            for siteid_b, swi_list_b in site_b_swi_dict.items():
                logger.info("SITEID B: {0}".format(siteid_b))
                if not counted_siteb.get(siteid_b, False):
                    logger.info("NEW SITEB: {0}".format(siteid_b))
                    stat_inc(statistics, 'sites_listb')
                    counted_siteb[siteid_b] = True

                for swi_b in swi_list_b:
                    if not counted_swib.get(swi_b, False):
                        logger.info("NEW SWIB: {0}".format(swi_b))
                        stat_inc(statistics, 'swi_listb')
                        counted_swib[swi_b] = True

                    # create anynet lookup key
                    anynet_lookup_key = "_".join(sorted([swi_a, swi_b]))

                    # fastpath - have we already calculated this anynet?
                    already_calculated = calculated_anynets.get(anynet_lookup_key, False)

                    # is SWI source same as dest?
                    same_swi = (swi_a == swi_b)
                    logger.debug("SAME SWI: {0}".format(same_swi))

                    # is this a DC <-> DC  Link?
                    siteid_a_role = site_id_to_role_dict.get(siteid_a, "UNKNOWN")
                    siteid_b_role = site_id_to_role_dict.get(siteid_b, "UNKNOWN")
                    dc_dc = ((siteid_a_role in ['HUB']) and (siteid_b_role in ['HUB']))
                    logger.debug("DC <-> DC: {0}".format(dc_dc))

                    # is this a site1:swia <-> site1:swib relationship?
                    same_site = (siteid_a == siteid_b)
                    logger.debug("SAME SITE: {0}".format(same_site))

                    if (not already_calculated) and (not same_swi) and (not dc_dc) and (not same_site):
                        # new anynet relationship, lets iterate.

                        # Does this Anynet currently exist in the topology?
                        already_exists = all_anynets.get(anynet_lookup_key, False)

                        if already_exists:
                            # anynet exists, lets populate stats.
                            stat_inc(statistics, 'current_anynets')
                            status = already_exists.get('status', 'other')
                            sub_type = already_exists.get('sub_type', 'other')
                            adminstate_query = already_exists.get('admin_up')
                            if adminstate_query == None:
                                admin_state = 'na'
                            elif adminstate_query == True:
                                admin_state = 'enabled'
                            else:
                                admin_state = 'disabled'

                            logger.debug("{0}: \n\t{1}\n\t{2}".format(anynet_lookup_key, status, sub_type))
                            if status == 'up':
                                status_txt = 'up'
                            elif status == 'down':
                                if admin_state in ['enabled', 'na']:
                                    status_txt = 'down'
                                else:
                                    status_txt = 'admindown'
                            elif status == 'init':
                                if admin_state in ['enabled', 'na']:
                                    status_txt = 'init'
                                else:
                                    status_txt = 'admindown'
                            else:
                                status_txt = 'other'
                                # debug
                                print("Got OTHER type: ", status)

                            if sub_type in ['always-on', 'auto']:
                                sub_txt = 'always'
                                stat_inc(statistics, 'sub_always')
                            elif sub_type == 'on-demand':
                                sub_txt = 'demand'
                                stat_inc(statistics, 'sub_demand')
                            else:
                                sub_txt = 'other'
                                stat_inc(statistics, 'sub_other')
                                # debug
                                print("Got OTHER sub-type: ", sub_type)

                            stat_inc(statistics, status_txt + '_anynets_' + sub_txt)

                            # Add the anynet to the "current_anynets" object which has filtered anynets from all
                            current_anynets[anynet_lookup_key] = already_exists

                        else:
                            # this is a never seen SWI SWI relationship, anynet will need to be added.
                            logger.debug("{0}: \n\t{1}\n\t{2}".format(anynet_lookup_key,
                                                                      'new',
                                                                      siteid_a + "(" + swi_a + ")" +
                                                                      " <-> " + siteid_b + "(" + swi_b + ")"))
                            new_anynets[anynet_lookup_key] = {
                                'status': 'new',
                                'source_wan_if_id': swi_a,
                                'target_wan_if_id': swi_b,
                                'source_site_id': swi_to_site_dict.get(swi_a, None),
                                'target_site_id': swi_to_site_dict.get(swi_b, None)
                            }
                            statistics['needed_anynets'] = statistics.get('needed_anynets', 0) + 1

                        # now that the anynet is handled, mark it as done in fastpath dict so we don't calc for it again
                        calculated_anynets[anynet_lookup_key] = True

    # return the calculated data.
    return new_anynets, current_anynets, statistics


def load_save_list(item_list, list_name, all_values, tenant_file_name):
    """
    Load/save JSON menu for WAN Networks.
    :param item_list: Item list to save
    :param list_name: Name of List
    :param all_values: All values
    :return: shallow copy of item_list.
    """
    return_list = []
    loop = True

    while loop:

        action = [
            ("Load List", 'load'),
            ("Save List", 'save'),
            ("Go Back", 'back')
        ]

        banner = "\nSelect Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        selected_action = menus.quick_menu(banner, line_fmt, action)[1]

        default_filename = tenant_file_name + "_" + list_name.replace(" ", "_").lower() + ".json"
        cwd = os.getcwd()

        if selected_action == 'load':

            print("Current directory is {0}".format(cwd))
            filename = menus.quick_str_input("Enter file name to load", default_filename)
            try:
                with open(filename) as data_file:
                    data = json.load(data_file)
                item_list = data[:]
                print("\n Successfully loaded {0} entries from {1}.".format(len(data), filename))
                loop = False
            except (ValueError, IOError) as e:
                print("ERROR, could not load {0}: {1}.".format(filename, e))

        elif selected_action == 'save':
            writefile = False
            print("Current directory is {0}".format(cwd))
            filename = menus.quick_str_input("Enter file name to save", default_filename)

            # check if exists.
            if os.path.exists(filename):
                if menus.quick_confirm("File exists, overwrite? ", "N"):
                    writefile = True
                else:
                    writefile = False
            else:
                writefile = True

            if writefile:
                try:
                    with open(filename, 'w') as outfile:
                        json.dump(item_list, outfile, indent=4)
                    print("\n Successfully save {0} entries out to {1}.".format(len(item_list), filename))
                    loop = False
                except (ValueError, IOError) as e:
                    print("ERROR, could not save {0}: {1}.".format(filename, e))

        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]


def remove_from_list(item_list, list_name, all_values):
    """
    Remove items from list
    :param item_list: Item list to save
    :param list_name: Name of List
    :param all_values: All values
    :return: shallow copy of item_list.
    :return:
    """

    return_list = []
    loop = True

    while loop:

        action = [
            ("Remove all", 'removeall'),
            ("Remove via pattern / regex", 'removere'),
            ("Go Back", 'back')
        ]

        banner = "\nSelect Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        selected_action = menus.quick_menu(banner, line_fmt, action)[1]

        if selected_action == 'removeall':
            print("\nRemoving all {1} WAN Network(s) from {0}.".format(list_name, len(item_list)))
            # shallow copy list.
            item_list = []
            loop = False
        elif selected_action == 'removere':
            regex_pattern = menus.quick_str_input("Enter regular expression pattern", '^.*$')
            try:
                temp_item_list = re_pick(all_values, regex_pattern)
                orig_size = len(item_list)
                print("\nAttempting to remove {0} items from {1} (if they exist).".format(len(temp_item_list), list_name))
                item_list = [x for x in item_list if x not in temp_item_list]
                removed_items = orig_size - len(item_list)
                if removed_items > 0:
                    print("Actually removed {0} items.".format(removed_items))
                else:
                    print("\nNo items matched, list unchanged.")
                loop = False

            except re.error as e:
                print("\nERROR: Invalid regular expression / pattern: {0}.".format(e))

        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]


def add_to_list(item_list, list_name, all_values):
    """
    Add WAN Networks to list
    :param item_list: Item list to save
    :param list_name: Name of List
    :param all_values: All values
    :return: shallow copy of item_list.
    """
    return_list = []
    loop = True

    while loop:

        action = [
            ("Add all", 'addall'),
            ("Add via pattern / regex", 'addre'),
            ("Go Back", 'back')
        ]

        banner = "\nSelect Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        selected_action = menus.quick_menu(banner, line_fmt, action)[1]

        if selected_action == 'addall':
            print("\nAdding all {1} WAN Network(s) to {0}.".format(list_name, len(all_values)))
            # shallow copy list.
            item_list = all_values[:]
            loop = False
        elif selected_action == 'addre':
            regex_pattern = menus.quick_str_input("Enter regular expression pattern", '^.*$')
            try:
                temp_item_list = re_pick(all_values, regex_pattern)
                # shallow copy dict to item_list
                print("\nAdding {0} items to {1}.".format(len(temp_item_list), list_name))
                item_list += temp_item_list[:]
                loop = False

            except re.error as e:
                print("\nERROR: Invalid regular expression / pattern: {0}.".format(e))

        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]


def edit_wn_list(item_list, list_name, all_values, tenant_file_name):
    """
    Edit WAN network list
    :param item_list: Item list to save
    :param list_name: Name of List
    :param all_values: All values
    :param tenant_file_name: File-system friendly tenant_name
    :return: shallow copy of item_list.
    """
    loop = True

    while loop:

        action = [
            ("View list", 'view'),
            ("Add to list", 'add'),
            ("Remove items from list", 'remove'),
            ("Load/Save list", 'file'),
            ("Go Back", 'back')
        ]

        banner = "\nSelect Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        selected_action = menus.quick_menu(banner, line_fmt, action)[1]

        if selected_action == 'view':
            print("\n{0} ({1} entries):".format(list_name, len(item_list)))
            for item in item_list:
                print("\t{0}".format(item))
        elif selected_action == 'add':
            item_list = add_to_list(item_list, list_name, all_values)
        elif selected_action == 'remove':
            item_list = remove_from_list(item_list, list_name, all_values)
        elif selected_action == 'file':
            item_list = load_save_list(item_list, list_name, all_values, tenant_file_name)
        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]


def save_script_to_text(new_anynets, current_anynets, tenantid, mesh_type,
                        id_sitename_dict, site_id_to_role, id_wan_network_name_dict, swi_to_wn_dict):
    """
    Save mesh_map.txt file
    :param new_anynets: list of anynet objects that are not created
    :param current_anynets: list of anynet objects that are currently created.
    :param tenantid: Customer tenant-ID
    :return: empty
    """

    role_xlate = {
        'HUB': 'DC',
        'SPOKE': 'Branch'
    }
    type_xlate = {
        'always-on': 'Always On',
        # always-on is auto in 4.4.1+
        'auto': 'Always On',
        'on-demand': 'Modifiable'
    }

    default_filename = 'mesh_map.txt'
    cwd = os.getcwd()
    writefile = False
    print("This menu will write a .txt file with create/delete statements for new/existing Mesh links.")
    print("Current directory is {0}".format(cwd))
    filename = menus.quick_str_input("Enter file name to save", default_filename)

    # check if exists.
    if os.path.exists(filename):
        if menus.quick_confirm("File exists, overwrite? ", "N") == 'y':
            writefile = True
        else:
            writefile = False
    else:
        writefile = True

    if writefile:
        write_list = ['# ' + mesh_name(mesh_type) + ' Create Commands (All new possible "MODIFIABLE" VPNs):']
        for key, value in new_anynets.items():
            anynet_text = "[{1}] {0} ({2}) <-> [{4}] {3} ({5}) - {6}" \
                .format(id_sitename_dict.get(value['source_site_id'], 'UNKNOWN'),
                        role_xlate.get(site_id_to_role.get(value['source_site_id'], 'Other'), 'Other'),
                        id_wan_network_name_dict.get(swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'),
                                                     'UNKNOWN'),
                        id_sitename_dict.get(value['target_site_id'], 'UNKNOWN'),
                        role_xlate.get(site_id_to_role.get(value['target_site_id'], 'Other'), 'Other'),
                        id_wan_network_name_dict.get(swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'),
                                                     'UNKNOWN'),
                        'New')

            write_list.append('  # ' + anynet_text)
            write_list.append('  net create --tenant-id {0} --spoke-site1 {1} --wan-if1 {2} --spoke-site2 {3}'
                              ' --wan-if2 {4} --force'.format(
                                tenantid,
                                value['source_site_id'],
                                value['source_wan_if_id'],
                                value['target_site_id'],
                                value['target_wan_if_id']))

        write_list.append('')
        write_list.append('# ' + mesh_name(mesh_type) + ' Disable Commands (for all existing VPNs, if desired):')
        for key, value in current_anynets.items():
            anynet_text = "[{1}] {0} ({2}) <-> [{4}] {3} ({5}) - {6}" \
                .format(id_sitename_dict.get(value['source_site_id'], 'UNKNOWN'),
                        role_xlate.get(site_id_to_role.get(value['source_site_id'], 'Other'), 'Other'),
                        id_wan_network_name_dict.get(swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'),
                                                     'UNKNOWN'),
                        id_sitename_dict.get(value['target_site_id'], 'UNKNOWN'),
                        role_xlate.get(site_id_to_role.get(value['target_site_id'], 'Other'), 'Other'),
                        id_wan_network_name_dict.get(swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'),
                                                     'UNKNOWN'),
                        type_xlate.get(value['sub_type'], 'other'))

            write_list.append('  # ' + anynet_text)
            write_list.append('  net update --tenant-id {0} --anynet-id {1} --admin-state false'.format(
                              tenantid,
                              value['path_id']))

        write_list.append('')
        write_list.append('# ' + mesh_name(mesh_type) + ' Enable Commands (for all existing VPNs, if desired):')
        for key, value in current_anynets.items():
            anynet_text = "[{1}] {0} ({2}) <-> [{4}] {3} ({5}) - {6}" \
                .format(id_sitename_dict.get(value['source_site_id'], 'UNKNOWN'),
                        role_xlate.get(site_id_to_role.get(value['source_site_id'], 'Other'), 'Other'),
                        id_wan_network_name_dict.get(swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'),
                                                     'UNKNOWN'),
                        id_sitename_dict.get(value['target_site_id'], 'UNKNOWN'),
                        role_xlate.get(site_id_to_role.get(value['target_site_id'], 'Other'), 'Other'),
                        id_wan_network_name_dict.get(swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'),
                                                     'UNKNOWN'),
                        type_xlate.get(value['sub_type'], 'other'))

            write_list.append('  # ' + anynet_text)
            write_list.append('  net update --tenant-id {0} --anynet-id {1} --admin-state true'.format(
                              tenantid,
                              value['path_id']))

        write_list.append('')
        write_list.append('# ' + mesh_name(mesh_type) + ' Delete Commands (for existing "MODIFIABLE" VPNs, if desired):')
        for key, value in current_anynets.items():
            if value['sub_type'] not in ["always-on", "auto"]:
                anynet_text = "[{1}] {0} ({2}) <-> [{4}] {3} ({5}) - {6}" \
                    .format(id_sitename_dict.get(value['source_site_id'], 'UNKNOWN'),
                            role_xlate.get(site_id_to_role.get(value['source_site_id'], 'Other'), 'Other'),
                            id_wan_network_name_dict.get(swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'),
                                                         'UNKNOWN'),
                            id_sitename_dict.get(value['target_site_id'], 'UNKNOWN'),
                            role_xlate.get(site_id_to_role.get(value['target_site_id'], 'Other'), 'Other'),
                            id_wan_network_name_dict.get(swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'),
                                                         'UNKNOWN'),
                            type_xlate.get(value['sub_type'], 'other'))

                write_list.append('  # ' + anynet_text)
                write_list.append('  net delete --tenant-id {0} --anynet-id {1}'.format(
                                  tenantid,
                                  value['path_id']))

        try:
            with open(filename, 'w') as outfile:
                outfile.write("\n".join(write_list))
            print("\n Successfully save {0} entries out to {1}.".format(len(write_list), filename))
        except (ValueError, IOError) as e:
            print("ERROR, could not save {0}: {1}.".format(filename, e))

    return


def save_to_csv(new_anynets, current_anynets, tenantid, id_sitename_dict, swi_to_wn_dict,
                id_wan_network_name_dict, site_id_to_role, mesh_type):
    """
    Save mesh_map.csv file
    :param new_anynets: list of anynet objects that are not created
    :param current_anynets: list of anynet objects that are currently created.
    :param tenantid: Customer tenant-ID
    :param id_sitename_dict: xlation dict of site id to site name format { '<siteid>': 'Site Name' }
    :param swi_to_wn_dict: xlation dict of swi id to wan network id format  { '<swi_id>': '<wn_id>' }
    :param id_wan_network_name_dict: xlation dict of wan net id to wan net name format { '<wn_id>': 'WAN Network Name' }
    :return: empty
    """
    default_filename = 'mesh_info.csv'
    type_xlate = {
        'always-on': 'Always On',
        # always-on is auto in 4.4.1+
        'auto': 'Always On',
        'on-demand': 'Modifiable'
    }

    role_xlate = {
        'HUB': 'DC',
        'SPOKE': 'Branch'
    }


    cwd = os.getcwd()
    writefile = False
    print("Current directory is {0}".format(cwd))
    filename = menus.quick_str_input("Enter file name to save", default_filename)

    # check if exists.
    if os.path.exists(filename):
        if menus.quick_confirm("File exists, overwrite? ", "N") == 'y':
            writefile = True
        else:
            writefile = False
    else:
        writefile = True

    if writefile:
        write_list = ['Mesh Type,Site 1,Site 1 Role,Site 1 WAN Network,Site 2,Site 2 Role,Site 2 WAN Network,Status,'
                      'Admin State,VPN Type,Site 1 ID,Site 1 WAN Interface ID,Site 1 WAN Network ID,Site 2 ID,'
                      'Site 2 WAN Interface ID,Site 2 WAN Network ID,Path ID']

        for key, value in current_anynets.items():
            adminstate_test = value.get('admin_up')
            if adminstate_test == None:
                admin_state = "N/A"
            elif adminstate_test == True:
                admin_state = "Enabled"
            else:
                admin_state = "Disabled"
            path_id = value.get('path_id')
            write_list.append('"{0}","{1}","{2}","{3}","{4}","{5}","{6}","{7}","{8}"'
                              ',"{9}",="{10}",="{11}",="{12}",="{13}",="{14}",="{15}",="{16}"'.format(
                mesh_name(mesh_type),
                id_sitename_dict.get(value['source_site_id'], 'UNKNOWN'),
                role_xlate.get(site_id_to_role.get(value['source_site_id'], 'Other'), 'Other'),
                id_wan_network_name_dict.get(swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'), 'UNKNOWN'),
                id_sitename_dict.get(value['target_site_id'], 'UNKNOWN'),
                role_xlate.get(site_id_to_role.get(value['target_site_id'], 'Other'), 'Other'),
                id_wan_network_name_dict.get(swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'), 'UNKNOWN'),
                value['status'],
                admin_state,
                type_xlate.get(value['sub_type'], 'other'),
                value['source_site_id'],
                value['source_wan_if_id'],
                swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'),
                value['target_site_id'],
                value['target_wan_if_id'],
                swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'),
                value['path_id']))
        for key, value in new_anynets.items():
            admin_state = "N/A"
            path_id = "N/A"
            write_list.append('"{0}","{1}","{2}","{3}","{4}","{5}","{6}","{7}","{8}"'
                              ',"{9}",="{10}",="{11}",="{12}",="{13}",="{14}",="{15}",="{16}"'.format(
                mesh_name(mesh_type),
                id_sitename_dict.get(value['source_site_id'], 'UNKNOWN'),
                role_xlate.get(site_id_to_role.get(value['source_site_id'], 'Other'), 'Other'),
                id_wan_network_name_dict.get(swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'), 'UNKNOWN'),
                id_sitename_dict.get(value['target_site_id'], 'UNKNOWN'),
                role_xlate.get(site_id_to_role.get(value['target_site_id'], 'Other'), 'Other'),
                id_wan_network_name_dict.get(swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'), 'UNKNOWN'),
                value['status'],
                admin_state,
                type_xlate.get('on-demand', 'other'),
                value['source_site_id'],
                value['source_wan_if_id'],
                swi_to_wn_dict.get(value['source_wan_if_id'], 'UNKNOWN'),
                value['target_site_id'],
                value['target_wan_if_id'],
                swi_to_wn_dict.get(value['target_wan_if_id'], 'UNKNOWN'),
                path_id))
        try:
            with open(filename, 'w') as outfile:
                outfile.write("\n".join(write_list))
            print("\n Successfully save {0} entries out to {1}.".format(len(write_list), filename))
        except (ValueError, IOError) as e:
            print("ERROR, could not save {0}: {1}.".format(filename, e))

    return


def update_calculations(site_a_wan_networks, site_b_wan_networks, site_a_swi_dict, site_b_swi_dict,
                        wn_to_swi_dict, wan_network_name_id_dict):
    """
    Takes an updated WN Name list for List A/List B, returns updated Site-SWI dicts only containing WAN Networks
    In lists given
    :param site_a_wan_networks: List A list of WAN Network Names
    :param site_b_wan_networks: List B list of WAN Network Names
    :param site_a_swi_dict: Original List A Site-SWI dict (containing all sites/all WAN Networks)
    :param site_b_swi_dict: Original List B Site-SWI dict (containing all sites/all WAN Networks)
    :param wn_to_swi_dict: xlation Wan network ID to SWI dict, format { '<wn_id>': [ '<swi_id1>', '<swi_id2>', ... ] }
    :param wan_network_name_id_dict: xlation WAN network name to ID dict
    :return: Tuple with two Site->SWI dicts, only containing Sites-SWIs that are members of WN Name lists sent.
    """
    return_site_a_swi_dict = {}
    return_site_b_swi_dict = {}
    swi_lista = []
    swi_listb = []

    # Convert WN names to swi IDs
    for wn_name_a in site_a_wan_networks:
        # get WN ID from Name
        wn_id_a = wan_network_name_id_dict.get(wn_name_a, None)
        if wn_id_a:
            # Get SWI list from WN to SWI mapping
            cur_swi_list_a = wn_to_swi_dict.get(wn_id_a, [])
            if cur_swi_list_a:
                # Combine the lists
                swi_lista += cur_swi_list_a

    for wn_name_b in site_b_wan_networks:
        # get WN ID from Name
        wn_id_b = wan_network_name_id_dict.get(wn_name_b, None)
        if wn_id_b:
            # Get SWI list from WN to SWI mapping
            cur_swi_list_b = wn_to_swi_dict.get(wn_id_b, [])
            if cur_swi_list_b:
                # Combine the lists
                swi_listb += cur_swi_list_b

    # iterate through the key/value pair of the site/swi dict. update return dict if matches filter previous.
    for key_a, listval_a in site_a_swi_dict.items():
        newlistval_a = []
        for cur_swi_a in listval_a:
            if cur_swi_a in swi_lista:
                # swi is in allowed SWI list. Add to new list container.
                newlistval_a.append(cur_swi_a)

        # if newlistval_a is not empty, add key_a: newlistval_a to return dict.
        if newlistval_a:
            return_site_a_swi_dict[key_a] = newlistval_a

    for key_b, listval_b in site_b_swi_dict.items():
        newlistval_b = []
        for cur_swi_b in listval_b:
            if cur_swi_b in swi_listb:
                # swi is in allowed SWI list. Add to new list container.
                newlistval_b.append(cur_swi_b)

        # if newlistval_b is not empty, add key_b: newlistval_b to return dict.
        if newlistval_b:
            return_site_b_swi_dict[key_b] = newlistval_b

    return return_site_a_swi_dict, return_site_b_swi_dict


def main_vpn_menu(siteid_list_a, siteid_list_b, all_anynets,
                  site_swi_all_dict, swi_to_wn_dict, wn_to_swi_dict,
                  id_wan_network_name_dict, wan_network_name_id_dict,
                  swi_to_site_dict, id_sitename_dict, mesh_type, site_id_to_role_dict,
                  sdk_vars, sdk_session):
    """
    Main menu for VPN manipulation
    :param siteid_list_a: List A of site IDs
    :param siteid_list_b: List B of site IDs
    :param current_anynets: List of current anynet objects
    :param site_swi_all_dict: Site-SWI dict for ALL sites selected.
    :param swi_to_wn_dict: xlation dict for SWI to Wan Network ID
    :param wn_to_swi_dict: xlation dict for WAN Network ID to SWI
    :param id_wan_network_name_dict: xlation dict for WAN Network ID to WAN Network Name
    :param wan_network_name_id_dict: xlation dict for WAN Network Name to WAN Network ID
    :param swi_to_site_dict: xlation dict for SWI to Site ID
    :param id_sitename_dict: xlation dict for site ID to site Name
    :param mesh_type: 'internet-stub' or 'priv-wan-stub'
    :param site_id_to_role_dict: site ID to Site Role text.
    :param sdk_vars: SDK global value dictionary
    :return: tuple with: action (string or true/false)
             site_a_action_dict (Site-SWI dict for list A)
             site_b_action_dict (Site-SWI dict for list B)
    """

    tenantid = sdk_session.tenant_id
    action = False
    site_a_action_dict = {}
    site_b_action_dict = {}

    logger.debug("ID_WN: {0}".format(json.dumps(id_wan_network_name_dict, indent=4)))

    # Build {siteid: [swia, swib]} dict based on siteid lists.
    site_a_swi_dict, site_b_swi_dict = site_swi_dicts(siteid_list_a, siteid_list_b, site_swi_all_dict)

    # get a unique WAN Network name list for each site-swi dict.
    site_a_wan_networks = get_unique_wan_networks_from_swi_dict(site_a_swi_dict,
                                                                swi_to_wn_dict,
                                                                id_wan_network_name_dict)
    site_b_wan_networks = get_unique_wan_networks_from_swi_dict(site_b_swi_dict,
                                                                swi_to_wn_dict,
                                                                id_wan_network_name_dict)

    # discover new anynets needed to complete mesh, and calculate statistics.
    new_anynets, current_anynets, statistics = calculate_vpn_links(site_a_swi_dict, site_b_swi_dict, all_anynets,
                                                  swi_to_site_dict, site_id_to_role_dict)

    # save original dicts/lists
    original_site_a_swi_dict = copy.deepcopy(site_a_swi_dict)
    original_site_b_swi_dict = copy.deepcopy(site_b_swi_dict)
    original_site_a_wan_networks = site_a_wan_networks[:]
    original_site_b_wan_networks = site_b_wan_networks[:]

    logger.debug("SITE A SWI ({0}): {1}".format(len(site_a_swi_dict), json.dumps(site_a_swi_dict, indent=4)))
    logger.debug("SITE B SWI ({0}): {1}".format(len(site_b_swi_dict), json.dumps(site_b_swi_dict, indent=4)))
    logger.debug("SITE A WN ({0}): {1}".format(len(site_a_wan_networks), json.dumps(site_a_wan_networks, indent=4)))
    logger.debug("SITE B WN ({0}): {1}".format(len(site_b_wan_networks), json.dumps(site_b_wan_networks, indent=4)))
    logger.debug("NEW AN ({0}): {1}".format(len(new_anynets), json.dumps(new_anynets, indent=4)))
    logger.debug("CURRENT AN ({0}): {1}".format(len(all_anynets),
                                                    json.dumps(all_anynets, indent=4)))
    logger.debug("STATS ({0}): {1}".format(len(statistics), json.dumps(statistics, indent=4)))
    logger.debug("WN to SWI ({0}): {1}".format(len(wn_to_swi_dict.keys()), json.dumps(wn_to_swi_dict, indent=4)))

    if sdk_vars["reload_wn_list_a"]:
        # re-loop, or initial values - pull previous list out of sdk_vars dict.
        matching_wan_nets = [x for x in site_a_wan_networks if x in sdk_vars["reload_wn_list_a"]]
        # if any match filter - otherwise leave all.
        if matching_wan_nets:
            site_a_wan_networks = matching_wan_nets

    if sdk_vars["reload_wn_list_b"]:
        # re-loop, or initial values - pull previous list out of sdk_vars dict.
        matching_wan_nets = [x for x in site_b_wan_networks if x in sdk_vars["reload_wn_list_b"]]
        # if any match filter - otherwise leave all.
        if matching_wan_nets:
            site_b_wan_networks = matching_wan_nets


    loop = True
    while loop:

        # Print header
        print("")
        print_selection_overview(statistics, site_a_wan_networks, site_b_wan_networks)
        print("")

        action = [
            ("Edit WAN Networks in List A", 'edit_wna'),
            ("Edit WAN Networks in List B", 'edit_wnb'),
            ("Save detailed mesh info to CSV", 'savecsv'),
            ("View and Directly modify VPN Mesh Links that match the above WAN Networks", 'godoit')
        ]

        banner = "Select Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        list_name, selected_action = menus.quick_menu(banner, line_fmt, action)

        if selected_action == 'edit_wna':
            # edit WAN network list
            site_a_wan_networks = edit_wn_list(site_a_wan_networks,
                                               "WAN Networks A", original_site_a_wan_networks, sdk_vars["tenant_str"])
            # recalculate site-swi info based on WAN Network edits
            site_a_swi_dict, site_b_swi_dict = update_calculations(site_a_wan_networks, site_b_wan_networks,
                                                                   original_site_a_swi_dict, original_site_b_swi_dict,
                                                                   wn_to_swi_dict, wan_network_name_id_dict)
            # recalculate anynet topo changes.
            new_anynets, current_anynets, statistics = calculate_vpn_links(site_a_swi_dict, site_b_swi_dict, all_anynets,
                                                          swi_to_site_dict, site_id_to_role_dict)

        elif selected_action == 'edit_wnb':
            # edit WAN network list
            site_b_wan_networks = edit_wn_list(site_b_wan_networks,
                                               "WAN Networks B", original_site_b_wan_networks, sdk_vars["tenant_str"])
            # recalculate site-swi info based on WAN Network edits
            site_a_swi_dict, site_b_swi_dict = update_calculations(site_a_wan_networks, site_b_wan_networks,
                                                                   original_site_a_swi_dict, original_site_b_swi_dict,
                                                                   wn_to_swi_dict, wan_network_name_id_dict)
            # recalculate anynet topo changes.
            new_anynets, current_anynets, statistics = calculate_vpn_links(site_a_swi_dict, site_b_swi_dict, all_anynets,
                                                          swi_to_site_dict, site_id_to_role_dict)
        elif selected_action == 'savecsv':
            save_to_csv(new_anynets, current_anynets, tenantid, id_sitename_dict, swi_to_wn_dict,
                        id_wan_network_name_dict, site_id_to_role_dict, mesh_type)
        elif selected_action == 'savetxt':
            save_script_to_text(new_anynets, current_anynets, tenantid, mesh_type, id_sitename_dict,
                                site_id_to_role_dict, id_wan_network_name_dict, swi_to_wn_dict)
        elif selected_action == "godoit":
            if (len(site_a_wan_networks) < 1) or (len(site_b_wan_networks) < 1):
                print("\nERROR, must select at least one WAN Network in each list.")
            else:
                # Good to go, continue.
                loop = False
        else:
            sys.exit()

    # return the new anynet objects

    # save data for future loops
    sdk_vars["reload_wn_list_a"] = site_a_wan_networks
    sdk_vars["reload_wn_list_b"] = site_b_wan_networks

    return new_anynets, current_anynets


def no_menu_all_links(siteid_list_a, siteid_list_b, all_anynets,
                      site_swi_all_dict, swi_to_wn_dict, wn_to_swi_dict,
                      id_wan_network_name_dict, wan_network_name_id_dict,
                      swi_to_site_dict, id_sitename_dict, mesh_type, site_id_to_role_dict,
                      sdk_vars, sdk_session):
    """
    Bypass interactive menu for full mesh / hub spoke.
    :param siteid_list_a: List A of site IDs
    :param siteid_list_b: List B of site IDs
    :param all_anynets: List of current anynet objects
    :param site_swi_all_dict: Site-SWI dict for ALL sites selected.
    :param swi_to_wn_dict: xlation dict for SWI to Wan Network ID
    :param wn_to_swi_dict: xlation dict for WAN Network ID to SWI
    :param id_wan_network_name_dict: xlation dict for WAN Network ID to WAN Network Name
    :param wan_network_name_id_dict: xlation dict for WAN Network Name to WAN Network ID
    :param swi_to_site_dict: xlation dict for SWI to Site ID
    :param id_sitename_dict: xlation dict for site ID to site Name
    :param mesh_type: 'internet-stub' or 'priv-wan-stub'
    :param site_id_to_role_dict: site ID to Site Role text.
    :param sdk_vars: SDK global value dictionary
    :return: tuple with: action (string or true/false)
             site_a_action_dict (Site-SWI dict for list A)
             site_b_action_dict (Site-SWI dict for list B)
    """
    logger.debug("ID_WN: {0}".format(json.dumps(id_wan_network_name_dict, indent=4)))

    # Build {siteid: [swia, swib]} dict based on siteid lists.
    site_a_swi_dict, site_b_swi_dict = site_swi_dicts(siteid_list_a, siteid_list_b, site_swi_all_dict)

    # get a unique WAN Network name list for each site-swi dict.
    site_a_wan_networks = get_unique_wan_networks_from_swi_dict(site_a_swi_dict,
                                                                swi_to_wn_dict,
                                                                id_wan_network_name_dict)
    site_b_wan_networks = get_unique_wan_networks_from_swi_dict(site_b_swi_dict,
                                                                swi_to_wn_dict,
                                                                id_wan_network_name_dict)

    # discover new anynets needed to complete mesh, and calculate statistics.
    new_anynets, current_anynets, statistics = calculate_vpn_links(site_a_swi_dict, site_b_swi_dict, all_anynets,
                                                                   swi_to_site_dict, site_id_to_role_dict)

    logger.debug("SITE A SWI ({0}): {1}".format(len(site_a_swi_dict), json.dumps(site_a_swi_dict, indent=4)))
    logger.debug("SITE B SWI ({0}): {1}".format(len(site_b_swi_dict), json.dumps(site_b_swi_dict, indent=4)))
    logger.debug("SITE A WN ({0}): {1}".format(len(site_a_wan_networks), json.dumps(site_a_wan_networks, indent=4)))
    logger.debug("SITE B WN ({0}): {1}".format(len(site_b_wan_networks), json.dumps(site_b_wan_networks, indent=4)))
    logger.debug("NEW AN ({0}): {1}".format(len(new_anynets), json.dumps(new_anynets, indent=4)))
    logger.debug("CURRENT AN ({0}): {1}".format(len(all_anynets),
                                                json.dumps(all_anynets, indent=4)))
    logger.debug("STATS ({0}): {1}".format(len(statistics), json.dumps(statistics, indent=4)))
    logger.debug("WN to SWI ({0}): {1}".format(len(wn_to_swi_dict.keys()), json.dumps(wn_to_swi_dict, indent=4)))

    logger.info("NEW AN Count: ({0})".format(len(new_anynets)))

    return new_anynets, current_anynets
