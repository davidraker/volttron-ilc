import gevent
import json

from pathlib import Path

from volttron.client.known_identities import CONFIGURATION_STORE


def test_install_and_start_agent(volttron_instance):

    a = volttron_instance.build_agent()
    gevent.sleep(1)
    capabilities = {"edit_config_store": {"identity": 'ilc.agent'}}
    volttron_instance.add_capabilities(a.core.publickey, capabilities)
    gevent.sleep(1)

    with open(Path(__file__).parent.parent.resolve() / 'sample_configs/ilc_config') as f:
        agent_config = json.load(f)
    a.vip.rpc.call(CONFIGURATION_STORE, 'manage_store', 'ilc.agent', 'config', agent_config).get(timeout=10)
    with open(Path(__file__).parent.parent.resolve() / 'sample_configs/control_config') as f:
        control_config = json.load(f)
    a.vip.rpc.call(CONFIGURATION_STORE, 'manage_store', 'ilc.agent', 'control_config', control_config).get(timeout=10)
    with open(Path(__file__).parent.parent.resolve() / 'sample_configs/criteria_config') as f:
        criteria_config = json.load(f)
    a.vip.rpc.call(CONFIGURATION_STORE, 'manage_store', 'ilc.agent', 'fake.csv', criteria_config).get(timeout=10)
    with open(Path(__file__).parent.parent.resolve() / 'sample_configs/pairwise_criteria.json') as f:
        pairwise_config = json.load(f)
    a.vip.rpc.call(CONFIGURATION_STORE, 'manage_store', 'ilc.agent', 'fake.csv', pairwise_config).get(timeout=10)

    ilc_uuid = volttron_instance.install_agent(
        agent_dir=str(Path(__file__).parent.parent.resolve()),
        vip_identity='ilc.agent',
        start=True)

    assert volttron_instance.is_agent_running(ilc_uuid)

