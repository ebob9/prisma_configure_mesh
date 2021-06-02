#!/usr/bin/env python

import json
import os
import re
import logging
import sys

from . import menus
from .utils import re_pick, stat_inc

# Set NON-SYSLOG logging to use function name
logger = logging.getLogger(__name__)


def print_selection_overview(site_list_a, site_list_b, sitename_id_dict, site_id_to_role_dict):
    """
    Print site list overview
    :param site_list_a: list of site names a
    :param site_list_b: list of site names b
    :param sitename_id_dict: site name to site ID xlation dict
    :param site_id_to_role_dict: site ID to role xlation dict
    :return: empty
    """

    statistics = {
        'hub_a': 0,
        'hub_b': 0,
        'spoke_a': 0,
        'spoke_b': 0,
        'other_a': 0,
        'other_b': 0,
        'all_a': 0,
        'all_b': 0
    }

    if site_list_a is None:
        site_list_a = []
    if site_list_b is None:
        site_list_b = []

    # get some stats
    for site in site_list_a:
        role = site_id_to_role_dict.get(sitename_id_dict.get(site, 'OTHER',), 'OTHER')
        if role in ['HUB']:
            stat_inc(statistics, 'hub_a')
            stat_inc(statistics, 'all_a')
        elif role in ['SPOKE']:
            stat_inc(statistics, 'spoke_a')
            stat_inc(statistics, 'all_a')
        else:
            print("Got OTHER type: ", role)
            stat_inc(statistics, 'other_a')
            stat_inc(statistics, 'all_a')
    for site in site_list_b:
        role = site_id_to_role_dict.get(sitename_id_dict.get(site, 'OTHER',), 'OTHER')
        if role in ['HUB']:
            stat_inc(statistics, 'hub_b')
            stat_inc(statistics, 'all_b')
        elif role in ['SPOKE']:
            stat_inc(statistics, 'spoke_b')
            stat_inc(statistics, 'all_b')
        else:
            print("Got OTHER type: ", role)
            stat_inc(statistics, 'other_b')
            stat_inc(statistics, 'all_b')

    print('\t    Site List A      Site List B')
    print('\tSelected: {:>5}  Selected: {:>5}'\
        .format(statistics['all_a'],
                statistics['all_b']))
    print('\t      DC: {:>5}        DC: {:>5}'.format(statistics['hub_a'], statistics['hub_b']))
    print('\t  Branch: {:>5}    Branch: {:>5}'.format(statistics['spoke_a'], statistics['spoke_b']))
    print('\t   Other: {:>5}     Other: {:>5}'.format(statistics['other_a'], statistics['other_b']))

    return


def load_save_list(item_list, list_name, all_values, tenant_file_name):
    """
    Load/save list JSON
    :param item_list: list of values
    :param list_name: name of list
    :param all_values: all possible list values in item_list
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
                if menus.quick_confirm("File exists, overwrite? ", "N") == 'y':
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


def add_to_list(item_list, list_name, all_values, tags=None):
    """
    Add to list
    :param item_list: list of values
    :param list_name: name of list
    :param all_values: all possible list values in item_list
    :return: shallow copy of item_list.
    """
    return_list = []
    loop = True

    while loop:

        action = [
            ("Add all sites", 'addall'),
            ("Add via site name pattern / regex", 'addre'),
            ("Add via site TAG", 'addtag'),
            ("Go Back", 'back')
        ]

        banner = "\nSelect Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        selected_action = menus.quick_menu(banner, line_fmt, action)[1]

        if selected_action == 'addall':
            print("\nAdding all {1} site(s) to {0}.".format(list_name, len(all_values)))
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

        elif selected_action == 'addtag':
            if not tags:
                print("Tag list is empty")
            tag = menus.quick_str_input("Enter site tag: ", 'TAG')
            temp_item_list = []
            #           print(tags)
            for name in all_values:
                #                print(all_values)
                if tag in tags[name]:
                    #                    print(name)
                    if name not in item_list:
                        temp_item_list.append(name)
            # shallow copy dict to item_list
            print("\nAdding {0} items to {1}.".format(len(temp_item_list), list_name))
            item_list += temp_item_list[:]
            loop = False

        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]


def remove_from_list(item_list, list_name, all_values, tags=None):
    """
    Remove from list
    :param item_list: list of values
    :param list_name: name of list
    :param all_values: all possible list values in item_list
    :param tags: list of tags
    :return: shallow copy of item_list.
    """
    return_list = []
    loop = True

    while loop:

        action = [
            ("Remove all sites", 'removeall'),
            ("Remove via site name pattern / regex", 'removere'),
            ("Remove all with a site TAG", 'removewtag'),
            ("Go Back", 'back')
        ]

        banner = "\nSelect Action:"
        line_fmt = "{0}: {1}"

        # just pull 2nd value
        selected_action = menus.quick_menu(banner, line_fmt, action)[1]

        if selected_action == 'removeall':
            print("\nRemoving all {1} site(s) from {0}.".format(list_name, len(item_list)))
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

        elif selected_action == 'removewtag':
            if not tags:
                print("Tag list is empty")
            tag = menus.quick_str_input("Enter site tag: ", 'TAG')
            temp_item_list = []
            #            print(tags)
            for name in all_values:
                if tag in tags[name]:
                    temp_item_list.append(name)
            orig_size = len(item_list)
            print(
                "\nAttempting to remove {0} items from {1} (if they exist).".format(len(temp_item_list), list_name))
            item_list = [x for x in item_list if x not in temp_item_list]
            removed_items = orig_size - len(item_list)
            if removed_items > 0:
                print("Actually removed {0} items.".format(removed_items))
            else:
                print("\nNo items matched, list unchanged.")

        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]


def edit_site_list(item_list, list_name, all_values, tenant_file_name, site_tags=None):
    """
    main site list edit menu
    :param item_list: list of values
    :param list_name: name of list
    :param all_values: all possible list values in item_list
    :param tenant_file_name: file compatable tenant name
    :param site_tags: site tags list
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
            item_list = add_to_list(item_list, list_name, all_values, site_tags)
        elif selected_action == 'remove':
            item_list = remove_from_list(item_list, list_name, all_values, site_tags)
        elif selected_action == 'file':
            item_list = load_save_list(item_list, list_name, all_values, tenant_file_name)
        elif selected_action == 'back':
            loop = False
        else:
            sys.exit()

    # return a shallow copy of site list
    return item_list[:]

