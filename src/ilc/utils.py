# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Installable Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2022 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}

import re
import logging
from sympy.parsing.sympy_parser import parse_expr
from sympy.logic.boolalg import Boolean

from volttron.utils import setup_logging

setup_logging()
_log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s   %(levelname)-8s %(message)s',
                    datefmt='%m-%d-%y %H:%M:%S')


def clean_text(text, rep=None):
    rep = rep if rep else {".": "_", "-": "_", "+": "_", "/": "_", ":": "_"}
    rep = dict((re.escape(k), v) for k, v in rep.items())
    pattern = re.compile("|".join(rep.keys()))
    new_key = pattern.sub(lambda m: rep[re.escape(m.group(0))], text)
    return new_key


def sympy_helper(condition, points):
    cleaned_points = []
    cleaned_condition = ""
    for point, value in points:
        cleaned = clean_text(point)
        cleaned_condition = condition.replace(point, cleaned)
        cleaned_points.append((cleaned, value))
    _log.debug(f"Sympy debug condition: {condition} -- {cleaned_condition}")
    _log.debug(f"Sympy debug points: {points} -- {cleaned_points}")
    equation = parse_expr(cleaned_condition)
    return_value = equation.subs(cleaned_points)
    if isinstance(return_value, Boolean):
        return bool(return_value)
    else:
        return float(return_value)


def parse_sympy(data, condition=False):
    """
    :param condition:
    :param data:
    :return:
    """
    if isinstance(data, dict):
        return_data = {}
        for key, value in data.items():
            new_key = clean_text(key)
            return_data[new_key] = value

    elif isinstance(data, list):
        if condition:
            return_data = ""
            for item in data:
                parsed_string = "(" + item + ")" if item not in ("&", "|") else item
                return_data += parsed_string
        else:
            return_data = []
            for item in data:
                return_data.append(item)
    else:
        return_data = data
    return return_data

def create_device_topic_map(arg_list, default_topic=""):
    result = {}
    topics = set()
    for item in arg_list:
        if isinstance(item, str):
            point = clean_text(item)
            result[default_topic + '/' + point] = point
            topics.add(default_topic)
        elif isinstance(item, (list, tuple)):
            device, point = item
            point = clean_text(point)
            result[device+'/'+point] = point
            topics.add(device)


    return result, topics

def fix_up_point_name(point, default_topic=""):
    if isinstance(point, list):
        device, point = point
        point = clean_text(point)
        return device + '/' + point, device
    elif isinstance(point, str):
        point = clean_text(point)
        return default_topic + '/' + point, default_topic