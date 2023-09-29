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


def clean_text(text, rep=None):
    rep = rep if rep else {" ": ""}
    rep = dict((re.escape(k), v) for k, v in rep.items())
    pattern = re.compile("|".join(rep.keys()))
    new_key = pattern.sub(lambda m: rep[re.escape(m.group(0))], text)
    return new_key


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
                parsed_string = clean_text(item)
                parsed_string = "(" + clean_text(item) + ")" if parsed_string not in ("&", "|") else parsed_string
                return_data += parsed_string
        else:
            return_data = []
            for item in data:
                return_data.append(clean_text(item))
    else:
        return_data = clean_text(data)
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
        #point = clean_text(point)
        return device + '/' + point, device
    elif isinstance(point, str):
        #point = clean_text(point)
        return default_topic + '/' + point, default_topic