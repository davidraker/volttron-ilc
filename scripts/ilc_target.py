from argparse import ArgumentParser
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from importlib.metadata import distribution, PackageNotFoundError
try:
    distribution('volttron-core')
	# TODO: Need to have a standalone agent for modular.
except PackageNotFoundError:
	from volttron.platform.vip.agent.utils import build_agent


def make_target(target, start=None, end=None, target_id=None, tz_name='US/Pacific'):
	start = datetime.isoformat(start) if start else datetime.now().isoformat()
	target_id = target_id if target_id else uuid4().hex
	target_message = [
		{
			"value": {
				"start": start,
				"target": target,
				"id": target_id
			}
		},
		{
			"value": {
				"tz": tz_name
			}
		}
	]
	if end is not None:
		target_message[0]['value']['end'] = datetime.isoformat(end)
	return target_message

def main():
	parser = ArgumentParser()
	parser.add_argument('target', help='The target power for ILC.')
	parser.add_argument('--start', default=None, help='Start time for the target in ISO format.')
	parser.add_argument('--end', default=None, help='End time for the target in ISO format.')
	parser.add_argument('--target-id', default=None, help='Unique identifier for the target.')
	parser.add_argument('--tz-name', default='US/Pacific', help='Timezone name for the target.')
	args = parser.parse_args()
	a = build_agent()
	target_message = make_target(target=args.target, start=args.start, end=args.end,
								 target_id=args.target_id, tz_name=args.tz_name)
	print(f'Sending target_message to ILC: {target_message}')
	a.vip.pubsub.publish("pubsub", "record/target_agent", headers={}, message=target_message).get(timeout=30.0)

if __name__ == '__main__':
	main()