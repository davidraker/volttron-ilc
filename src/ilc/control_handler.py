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

import logging

from sympy import symbols
from sympy.parsing.sympy_parser import parse_expr

from volttron.client.messaging import headers as headers_mod
from volttron.utils import setup_logging, format_timestamp, get_aware_utc_now

from ilc.utils import parse_sympy, create_device_topic_map, fix_up_point_name

setup_logging()
_log = logging.getLogger(__name__)


def publish_data(time_stamp, message, topic, publish_method):
    headers = {headers_mod.DATE: format_timestamp(get_aware_utc_now())}
    message["TimeStamp"] = format_timestamp(time_stamp)
    publish_method("pubsub", topic, headers, message).get()


class ControlCluster(object):
    def __init__(self, cluster_config, actuator, logging_topic, parent):
        self.devices = {}
        self.device_topics = set()
        for device_name, device_config in cluster_config.items():
            control_manager = ControlManager(device_config, logging_topic, parent)
            self.devices[device_name, actuator] = control_manager
            self.device_topics |= control_manager.device_topics

    def get_all_devices_status(self, state):
        results = []
        for device_info, device in self.devices.items():
            for device_id in device.get_device_status(state):
                results.append((device_info[0], device_id, device_info[1]))
        return results


class ControlContainer(object):
    def __init__(self):
        self.clusters = []
        self.devices = {}
        self.device_topics = set()
        self.topics_per_device = {}
        self.control_topics = {}

    def add_control_cluster(self, cluster):
        self.clusters.append(cluster)
        self.devices.update(cluster.devices)
        self.device_topics |= cluster.device_topics

    def get_device_name_list(self):
        return self.devices.keys()

    def get_device(self, device_name):
        return self.devices[device_name]

    def get_device_topic_set(self):
        return self.device_topics

    def get_devices_status(self, state):
        all_on_devices = []
        for cluster in self.clusters:
            on_device = cluster.get_all_devices_status(state)
            all_on_devices.extend(on_device)
        return all_on_devices

    def ingest_data(self, time_stamp, data):
        for device in self.devices.values():
            device.ingest_data(time_stamp, data)

    def get_ingest_topic_dict(self):
        for device in self.devices.values():
            for cls in device.controls.values():
                self.control_topics[cls] = cls.get_topic_maps()
        return self.control_topics


class DeviceStatus(object):
    def __init__(self, logging_topic, parent, device_status_args=None, condition="", default_device=""):
        self.current_device_values = {}
        #device_status_args = parse_sympy(device_status_args)
        device_status_args = device_status_args if device_status_args else []

        self.device_topic_map, self.device_topics = create_device_topic_map(device_status_args, default_device)

        _log.debug("Device topic map: {}".format(self.device_topic_map))
        
        # self.device_status_args = device_status_args
        self.condition = parse_sympy(condition, condition=True)
        self.expr = parse_expr(self.condition)
        self.command_status = False
        self.default_device = default_device
        self.parent = parent
        self.logging_topic = logging_topic

    def ingest_data(self, time_stamp, data):
        for topic, point in self.device_topic_map.items():
            if topic in data:
                self.current_device_values[point] = data[topic]
                _log.debug("DEVICE_STATUS: {} - {} current device values: {}".format(topic,
                                                                                     self.condition,
                                                                                     self.current_device_values))
        # bail if we are missing values.
        if len(self.current_device_values) < len(self.device_topic_map):
            return

        conditional_points = self.current_device_values.items()
        conditional_value = False
        if conditional_points:
            conditional_value = self.expr.subs(conditional_points)
        try:
            self.command_status = bool(conditional_value)
        except TypeError:
            self.command_status = False
        message = self.current_device_values
        message["Status"] = self.command_status
        topic = "/".join([self.logging_topic, self.default_device, "DeviceStatus"])
        # publish_data(time_stamp, message, topic, self.parent.vip.pubsub.publish)


class Controls(object):
    def __init__(self, control_config, logging_topic, parent, default_device=""):
        self.device_topics = set()

        device_topic = control_config.pop("device_topic", default_device)
        self.device_topics.add(device_topic)
        self.device_status = {}
        self.conditional_curtailments = []

        curtailment_settings = control_config.pop('curtail_settings', [])
        if isinstance(curtailment_settings, dict):
            curtailment_settings = [curtailment_settings]

        for settings in curtailment_settings:
            conditional_curtailment = ControlSetting(logging_topic, parent, default_device=device_topic, **settings)
            self.device_topics |= conditional_curtailment.device_topics
            self.conditional_curtailments.append(conditional_curtailment)

        self.conditional_augments = []
        augment_settings = control_config.pop('augment_settings', [])
        if isinstance(augment_settings, dict):
            augment_settings = [augment_settings]

        for settings in augment_settings:
            conditional_augment = ControlSetting(logging_topic, parent, default_device=device_topic, **settings)
            self.device_topics |= conditional_augment.device_topics
            self.conditional_augments.append(conditional_augment)
        device_status_dict = control_config.pop('device_status')
        if "curtail" not in device_status_dict and "augment" not in device_status_dict:
            self.device_status["curtail"] = DeviceStatus(logging_topic, parent, default_device=device_topic, **device_status_dict)
            self.device_topics |= self.device_status["curtail"].device_topics
        else:
            for state, device_status_parms in device_status_dict.items():
                self.device_status[state] = DeviceStatus(logging_topic, parent, default_device=device_topic, **device_status_parms)
                self.device_topics |= self.device_status[state].device_topics
        self.currently_controlled = False
        _log.debug("CONTROL_TOPIC: {}".format(self.device_topics))

    def ingest_data(self, time_stamp, data):
        for conditional_curtailment in self.conditional_curtailments:
            conditional_curtailment.ingest_data(time_stamp, data)
        for conditional_augment in self.conditional_augments:
            conditional_augment.ingest_data(time_stamp, data)
        for state in self.device_status:
            self.device_status[state].ingest_data(time_stamp, data)

    def get_control_info(self, state):
        settings = self.conditional_curtailments if state == 'curtail' else self.conditional_augments
        for setting in settings:
            if setting.check_condition():
                return setting.get_control_info()

        return None

    def get_point_device(self, state):
        settings = self.conditional_curtailments if state == 'curtail' else self.conditional_augments
        for setting in settings:
            if setting.check_condition():
                return setting.get_point_device()

        return None

    def increment_control(self):
        self.currently_controlled = True

    def reset_control_status(self):
        self.currently_controlled = False

    def get_topic_maps(self):
        topics = []
        for cls in self.conditional_augments:
            topics.extend(list(cls.device_topic_map.keys()))
        for cls in self.conditional_curtailments:
            topics.extend(list(cls.device_topic_map.keys()))
        for state, cls in self.device_status.items():
            topics.extend(list(cls.device_topic_map.keys()))
        return topics


class ControlManager(object):
    def __init__(self, device_config, logging_topic, parent, default_device=""):
        self.device_topics = set()
        self.controls = {}
        self.topics_per_device = {}

        for device_id, control_config in device_config.items():
            controls = Controls(control_config, logging_topic, parent, default_device)
            self.controls[device_id] = controls
            self.device_topics |= controls.device_topics

    def ingest_data(self, time_stamp, data):
        for control in self.controls.values():
            control.ingest_data(time_stamp, data)

    def get_control_info(self, device_id, state):
        return self.controls[device_id].get_control_info(state)

    def get_point_device(self, device_id, state):
        return self.controls[device_id].get_point_device(state)

    def increment_control(self, device_id):
        self.controls[device_id].increment_control()

    def reset_control_status(self, device_id):
        self.controls[device_id].reset_control_status()

    def get_device_status(self, state):
        return [command for command, control in self.controls.items() if (state in control.device_status and control.device_status[state].command_status)]

    def get_control_topics(self):
        pass

    def get_topics(self, time_stamp, data):
        self.topics_per_device = {}
        for control in self.controls.values():
            self.topics_per_device[control] = control.get_topic_maps()

class ControlSetting(object):
    def __init__(self, logging_topic, parent, point=None, value=None, load=None, offset=None, maximum=None, minimum=None,
                 revert_priority=None, equation=None, control_method=None, control_mode="comfort",
                 condition="", conditional_args=None, default_device=""):
        if control_method is None:
            raise ValueError("Missing 'control_method' configuration parameter!")
        if point is None:
            raise ValueError("Missing device control 'point' configuration parameter!")
        if load is None:
            raise ValueError("Missing device 'load' estimation configuration parameter!")

        self.point, self.point_device = fix_up_point_name(point, default_device)
        self.control_method = control_method
        self.value = value

        self.offset = offset
        self.control_mode = control_mode
        self.revert_priority = revert_priority
        self.maximum = maximum
        self.minimum = minimum
        self.logging_topic = logging_topic
        self.parent = parent
        self.default_device = default_device

        if self.control_method.lower() == 'equation':
            self.equation_args = []
            # equation_args = parse_sympy(equation['equation_args'])
            equation_args = equation['equation_args']
            for arg in equation_args:
                point, point_device = fix_up_point_name(arg, default_device)
                if isinstance(arg, list):
                    token = arg[0]
                else:
                    token = arg
                self.equation_args.append([token, point])

            self.control_value_formula = parse_expr(parse_sympy(equation['operation']))
            self.maximum = equation['maximum']
            self.minimum = equation['minimum']

        if isinstance(load, dict):
            #args = parse_sympy(load['equation_args'])
            args = load['equation_args']
            load_args = []
            for arg in args:
                point, point_device = fix_up_point_name(arg, default_device)
                if isinstance(arg, list):
                    token = arg[1]
                else:
                    token = arg
                load_args.append([token, point])
            actuator_args = load['equation_args']
            self.load_points = symbols(load_args)
            load_expr = parse_expr(parse_sympy(load['operation']))
            self.load = {
                'load_equation': load_expr,
                'load_equation_args': load_args,
                'actuator_args': actuator_args
            }
        else:
            self.load = load

        self.conditional_expr = None
        self.conditional_control = None
        self.device_topic_map, self.device_topics = {}, set()
        self.current_device_values = {}

        if conditional_args and condition:
            self.conditional_expr = parse_sympy(condition, condition=True)
            self.conditional_control = parse_expr(self.conditional_expr)

            self.device_topic_map, self.device_topics = create_device_topic_map(conditional_args, default_device)
        self.device_topics.add(self.point_device)
        self.conditional_points = []

    def get_point_device(self):
        return self.point_device

    def get_control_info(self):
        if self.control_method.lower() == 'equation':
            return {
                'point': self.point,
                'load': self.load,
                'revert_priority': self.revert_priority,
                'control_equation': self.control_value_formula,
                'equation_args': self.equation_args,
                'control_method': self.control_method,
                'maximum': self.maximum,
                'minimum': self.minimum,
                'control_mode': self.control_mode
            }
        elif self.control_method.lower() == 'offset':
            return {
                'point': self.point,
                'load': self.load,
                'offset': self.offset,
                'revert_priority': self.revert_priority,
                'control_method': self.control_method,
                'maximum': self.maximum,
                'minimum': self.minimum,
                'control_mode': self.control_mode
            }
        elif self.control_method.lower() == 'value':
            return {
                'point': self.point,
                'load': self.load,
                'value': self.value,
                'revert_priority': self.revert_priority,
                'control_method': self.control_method,
                'maximum': self.maximum,
                'minimum': self.minimum,
                'control_mode': self.control_mode
            }

    def check_condition(self):
        # If we don't have a condition then we are always true.
        if self.conditional_expr is None:
            return True

        if self.conditional_points:
            value = self.conditional_control.subs(self.conditional_points)
            _log.debug('{} (conditional_control) evaluated to {}'.format(self.conditional_expr, value))
        else:
            value = False
        return value

    def ingest_data(self, time_stamp, data):
        for topic, point in self.device_topic_map.items():
            if topic in data:
                self.current_device_values[point] = data[topic]

        # bail if we are missing values.
        if len(self.current_device_values) < len(self.device_topic_map):
            return

        self.conditional_points = self.current_device_values.items()