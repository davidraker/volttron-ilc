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
import abc
import logging

import gevent

from importlib.metadata import version

if int(version('volttron').split('.')[0]) >= 10:
    from volttron.client.messaging import headers as headers_mod
    from volttron.client.vip.agent import Agent
    from volttron.utils import setup_logging, format_timestamp, get_aware_utc_now
    from volttron.utils.jsonrpc import RemoteError
else:
    from volttron.platform.vip.agent import Agent
    from volttron.platform.messaging import headers as headers_mod
    from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now, setup_logging
    from volttron.platform.jsonrpc import RemoteError

from ilc.utils import parse_sympy, sympy_evaluate, create_device_topic_map, fix_up_point_name

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
            control_manager = ControlManager(device_name, device_config, logging_topic, parent, actuator)
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
        device_status_args = device_status_args if device_status_args else []

        self.device_topic_map, self.device_topics = create_device_topic_map(device_status_args, default_device)

        _log.debug("Device topic map: {}".format(self.device_topic_map))
        
        # self.device_status_args = device_status_args
        self.condition = parse_sympy(condition)
        self.expr = self.condition
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
            conditional_value = sympy_evaluate(self.expr, conditional_points)
        try:
            self.command_status = bool(conditional_value)
        except TypeError:
            self.command_status = False
        message = self.current_device_values
        message["Status"] = self.command_status
        topic = "/".join([self.logging_topic, self.default_device, "DeviceStatus"])
        # publish_data(time_stamp, message, topic, self.parent.vip.pubsub.publish)


class Controls(object):
    def __init__(self, device_id, control_config, logging_topic, agent, manager, default_device="",
                 device_actuator='platform.actuator'):
        self.id = device_id
        self.device_topics = set()
        self.manager = manager

        device_topic = control_config.pop("device_topic", default_device)
        self.device_topics.add(device_topic)
        self.device_status = {}
        self.conditional_curtailments = []

        curtailment_settings = control_config.pop('curtail_settings', [])
        if isinstance(curtailment_settings, dict):
            curtailment_settings = [curtailment_settings]

        for settings in curtailment_settings:
            conditional_curtailment = ControlSetting.make_setting(logging_topic=logging_topic, agent=agent,
                                                                  controls_object=self, default_device=device_topic,
                                                                  device_actuator=device_actuator, **settings)
            self.device_topics |= conditional_curtailment.device_topics
            self.conditional_curtailments.append(conditional_curtailment)

        self.conditional_augments = []
        augment_settings = control_config.pop('augment_settings', [])
        if isinstance(augment_settings, dict):
            augment_settings = [augment_settings]

        for settings in augment_settings:
            conditional_augment = ControlSetting.make_setting(logging_topic=logging_topic, agent=agent,
                                                              controls_object=self, default_device=device_topic,
                                                              device_actuator=device_actuator, **settings)
            self.device_topics |= conditional_augment.device_topics
            self.conditional_augments.append(conditional_augment)
        device_status_dict = control_config.pop('device_status')
        if "curtail" not in device_status_dict and "augment" not in device_status_dict:
            self.device_status["curtail"] = DeviceStatus(logging_topic, agent, default_device=device_topic,
                                                         **device_status_dict)
            self.device_topics |= self.device_status["curtail"].device_topics
        else:
            for state, device_status_params in device_status_dict.items():
                self.device_status[state] = DeviceStatus(logging_topic, agent, default_device=device_topic,
                                                         **device_status_params)
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

    def get_control_setting(self, state):
        settings = self.conditional_curtailments if state == 'curtail' else self.conditional_augments
        for setting in settings:
            if setting.check_condition():
                return setting
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
    def __init__(self, name, device_config, logging_topic, agent, default_device="",
                 device_actuator='platform.actuator'):
        self.name = name
        self.device_topics = set()
        self.controls = {}
        self.topics_per_device = {}

        for device_id, control_config in device_config.items():
            controls = Controls(device_id, control_config, logging_topic, agent, manager=self,
                                default_device=default_device, device_actuator=device_actuator)
            self.controls[device_id] = controls
            self.device_topics |= controls.device_topics

    def ingest_data(self, time_stamp, data):
        for control in self.controls.values():
            control.ingest_data(time_stamp, data)

    def get_control_info(self, device_id, state):
        return self.controls[device_id].get_control_info(state)

    def get_control_setting(self, device_id, state):
        return self.controls[device_id].get_control_setting(state)

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
    def __init__(self, logging_topic, agent, controls_object, point=None, load=None, maximum=None, minimum=None,
                 revert_priority=None, control_mode="comfort", condition="", conditional_args=None, default_device="",
                 device_actuator='platform.actuator'):
        if point is None:
            raise ValueError("Missing device control 'point' configuration parameter!")
        if load is None:
            raise ValueError("Missing device 'load' estimation configuration parameter!")

        self.agent: Agent = agent
        self.controls_object = controls_object
        self.default_device = default_device
        self.device_actuator = device_actuator
        self.point, self.point_device = fix_up_point_name(point, default_device)
        self.control_mode = control_mode
        self.revert_priority = revert_priority
        self.maximum = maximum
        self.minimum = minimum
        self.logging_topic = logging_topic

        if isinstance(load, dict):
            args = load['equation_args']
            self.load = {
                'load_equation': load['operation'],
                'load_equation_args': self._setup_equation_args(default_device, args),
                'actuator_args': args
            }
        else:
            self.load = load

        self.control_point_topic = self.agent.base_rpc_path(path=self.point)

        self.conditional_control = None
        self.device_topic_map, self.device_topics = {}, set()
        self.current_device_values = {}

        if conditional_args and condition:
            self.conditional_control = parse_sympy(condition)

            self.device_topic_map, self.device_topics = create_device_topic_map(conditional_args, default_device)
        self.device_topics.add(self.point_device)
        self.conditional_points = []

        #### State ####
        self.control_load = 0.0
        self.control_time = None
        self.control_value = None
        self.revert_value = None

    @property
    def device_id(self):
        return self.controls_object.id

    @property
    def device_name(self):
        return self.controls_object.manager.name

    def clear_state(self):
        """Reset all state variables (for use after the setting has been released)."""
        self.control_load = 0.0
        self.control_time = None
        self.control_value = None
        self.revert_value = None

    def modify_load(self):
        # TODO: This block regarding the dictionary does not always successfully find a scalar value.
        if isinstance(self.load, dict):
            load_equation = self.load["load_equation"]
            load_point_values = []
            for load_arg in self.load["load_equation_args"]:
                point_to_get = self.agent.base_rpc_path(path=load_arg[1])
                try:
                    # TODO: This should be a get_multiple outside the loop that calls this function or a subscription.
                   value = self.agent.vip.rpc.call(self.device_actuator, "get_point", point_to_get).get(timeout=30)
                except RemoteError as ex:
                    _log.warning("Failed get point for load calculation {point_to_get} (RemoteError): {str(ex)}")
                    self.control_load = 0.0
                    break
                load_point_values.append((load_arg[0], value))
                try:
                    self.control_load = sympy_evaluate(load_equation, load_point_values)
                except:
                    _log.debug(f"Could not convert expression for load estimation: {load_equation} --"
                               f" {load_point_values}")
                    self.control_load = 0.0
        error = False
        if self.revert_value is None:
            try:
                    self.revert_value = self.agent.vip.rpc.call(self.device_actuator, "get_point",
                                                                self.control_point_topic).get(timeout=30)
            except (RemoteError, gevent.Timeout) as ex:
                error = True
                _log.warning(f"Failed get point for revert value storage {self.control_point_topic}"
                             f" (RemoteError): {str(ex)}")
                self.control_value = None  # TODO: Should control_value be altered here?
                return error

        self._determine_control_value()
        self._actuate()
        self.control_time = get_aware_utc_now()
        return error

    @abc.abstractmethod
    def _determine_control_value(self):
        # Implementations should typically call super when finished with their own logic to run this:
        if None not in [self.minimum, self.maximum]:
            self.control_value = max(self.minimum, min(self.control_value, self.maximum))
        elif self.minimum is not None and self.maximum is None:
            self.control_value = max(self.minimum, self.control_value)
        elif self.maximum is not None and self.minimum is None:
            self.control_value = min(self.maximum, self.control_value)

    @abc.abstractmethod
    def _actuate(self):
        # Implementations may just call super if this is sufficient, or may override this.
        _log.debug("***** ENTER SET POINT *****************")
        self.agent.vip.rpc.call(self.device_actuator, "set_point", "ilc_agent", self.control_point_topic,
                                self.control_value).get(timeout=30)
        prefix = self.agent.update_base_topic.split("/")[0]
        topic = "/".join([prefix, self.control_point_topic, "Actuate"])
        message = {"Value": self.control_value, "PreviousValue": self.revert_value}
        self.agent.publish_record(topic, message)

    @staticmethod
    def _setup_equation_args(default_device, equation_args):
        arg_list = []
        for arg in equation_args:
            point, point_device = fix_up_point_name(arg, default_device)
            if isinstance(arg, list):
                token = arg[0]
            else:
                token = arg
            arg_list.append([token, point])
        return arg_list

    def get_point_device(self):
        return self.point_device

    def get_control_info(self):
        return {
            'point': self.point,
            'load': self.load,
            'revert_priority': self.revert_priority,
            'maximum': self.maximum,
            'minimum': self.minimum,
            'control_mode': self.control_mode
        }

    def check_condition(self):
        # If we don't have a condition then we are always true.
        if self.conditional_control is None:
            return True

        if self.conditional_points:
            value = sympy_evaluate(self.conditional_control, self.conditional_points)
            _log.debug('{} (conditional_control) evaluated to {}'.format(self.conditional_control, value))
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

    @classmethod
    def make_setting(cls, control_method, **kwargs):
        if control_method.lower() == "equation":
            return EquationControlSetting(**kwargs)
        elif control_method.lower() == "offset":
            return OffsetControlSetting(**kwargs)
        elif control_method.lower() == "ramp":
            return RampControlSetting(**kwargs)
        elif control_method.lower() == "value":
            return ValueControlSetting(**kwargs)
        else:
            raise ValueError(f"Missing valid 'control_method' configuration parameter! Received: '{control_method}'")


class EquationControlSetting(ControlSetting):
    def __init__(self, default_device, equation, **kwargs):
        super(EquationControlSetting, self).__init__(**kwargs)
        equation_args = equation['equation_args']
        self.equation_args = self._setup_equation_args(default_device, equation_args)
        self.control_value_formula = equation['operation']
        self.maximum = equation['maximum']
        self.minimum = equation['minimum']

    def get_control_info(self):
        control_info = super(EquationControlSetting, self).get_control_info()
        control_info.update({
            'control_equation': self.control_value_formula,
            'control_method': 'equation',
            'equation_args': self.equation_args,
        })

    def _determine_control_value(self):
        equation = self.control_value_formula
        equation_point_values = []

        for eq_arg in self.equation_args:
            point_get = self.agent.base_rpc_path(path=eq_arg[1])
            value = self.agent.vip.rpc.call(self.device_actuator, "get_point", point_get).get(timeout=30)
            equation_point_values.append((eq_arg[0], value))

        self.control_value = sympy_evaluate(equation, equation_point_values)
        super(EquationControlSetting, self)._determine_control_value()

    def _actuate(self):
        super(EquationControlSetting, self)._actuate()

class OffsetControlSetting(ControlSetting):
    def __init__(self, offset, **kwargs):
        super(OffsetControlSetting, self).__init__(**kwargs)
        self.offset = offset

    def get_control_info(self):
        control_info = super(OffsetControlSetting, self).get_control_info()
        control_info.update({ 'control_method': 'offset', 'offset': self.offset})
        return control_info

    def _determine_control_value(self):
        self.control_value = self.revert_value + self.offset
        super(OffsetControlSetting, self)._determine_control_value()

    def _actuate(self):
        super(OffsetControlSetting, self)._actuate()


class RampControlSetting(ControlSetting):
    def __init__(self, destination_value, increment_time, increment_value, **kwargs):
        super(RampControlSetting, self).__init__(**kwargs)
        self.control_method = 'ramp'
        self.control_value = destination_value
        self.increment_time = increment_time
        self.increment_value = increment_value

        self.greenlet = None

    def get_control_info(self):
        control_info = super(RampControlSetting, self).get_control_info()
        control_info.update({'control_method': 'ramp',
                             'increment_time': self.increment_time,
                             'increment_value': self.increment_value
                             })
        return control_info

    def _determine_control_value(self):
        super(RampControlSetting, self)._determine_control_value()

    def _actuate(self):
        if self.greenlet:
            self.greenlet.kill()
        start_value = self.agent.vip.rpc.call(self.device_actuator, "get_point", self.control_point_topic
                                              ).get(timeout=30)
        steps = (start_value - self.control_value) / self.increment_value
        def ramp(current_value):
            for _ in range(steps):
                previous_value = current_value
                current_value -= self.increment_value
                self.agent.vip.rpc.call(self.device_actuator, "set_point", "ilc_agent", self.control_point_topic,
                                        current_value).get(timeout=30)
                prefix = self.agent.update_base_topic.split("/")[0]
                topic = "/".join([prefix, self.control_point_topic, "Actuate"])
                message = {"Value": current_value, "PreviousValue": previous_value}
                self.agent.publish_record(topic, message)
                gevent.sleep(self.increment_time)
            if current_value != self.control_value:
                self.agent.vip.rpc.call(self.device_actuator, "set_point", "ilc_agent", self.control_point_topic,
                                        self.control_value).get(timeout=30)
        self.greenlet = gevent.spawn(ramp, start_value)

class ValueControlSetting(ControlSetting):
    def __init__(self, value, **kwargs):
        super(ValueControlSetting, self).__init__(**kwargs)
        self.value = value

    def get_control_info(self):
        control_info = super(ValueControlSetting, self).get_control_info()
        control_info.update({'control_method': 'value', 'value': self.value})

    def _determine_control_value(self):
        self.control_value = self.value
        super(ValueControlSetting, self)._determine_control_value()

    def _actuate(self):
        super(ValueControlSetting, self)._actuate()
