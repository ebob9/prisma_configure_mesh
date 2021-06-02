#!/usr/bin/env python

import re
import sys
import cloudgenix
import json
import progressbar
from .versions import SCRIPT_NAME, SCRIPT_VERSION


def stat_inc(dictionary, key):
    """
    Incrament key stat in dictionary by 1
    :param dictionary: dictionary with keys with INT values
    :param key: key to be incremented by 1, or created with 1
    :return: empty
    """
    dictionary[key] = dictionary.get(key, 0) + 1
    return


def re_pick(item_list, regex_str):
    """
    Search list, return list with items that match regex.
    :param item_list: list of items
    :param regex_str: regex string
    :return: list of items in item_list that match regex_str
    """
    # compile regex
    str_search = re.compile(regex_str)
    result = []
    # iterate list
    for item_str in item_list:
        # look for match
        match = str_search.search(item_str)
        # when match, add to return queue
        if match:
            result.append(item_str)
    return result


def dump_version():
    """
    Dump version info to string and exit.
    :return: Multiline String.
    """
    # Got request for versions. Dump and exit
    try:
        python_ver = sys.version
    except NameError:
        python_ver = "Unknown"
    try:
        cloudgenix_ver = cloudgenix.version
    except NameError:
        cloudgenix_ver = "Unknown"
    try:
        json_ver = json.__version__
    except NameError:
        json_ver = "Unknown"
    try:
        pb2_ver = progressbar.__version__
    except NameError:
        pb2_ver = "Unknown"

    output = ""
    output += "**PROGRAM VERSIONS**, "
    output += "Python version: {0}, ".format(python_ver)
    output += "'{0}' version: {1}, ".format(SCRIPT_NAME, SCRIPT_VERSION)
    output += "'cloudgenix' version: {0}, ".format(cloudgenix_ver)
    output += "'json' version: {0}, ".format(json_ver)
    output += "'Progressbar2 version: {0}".format(pb2_ver)
    return output
