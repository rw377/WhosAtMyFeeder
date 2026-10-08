"""Home Assistant add-on entry point.

Turns the add-on options into the app's config.yml, filling in the MQTT broker
from the Supervisor (the Mosquitto add-on) when none is set, then starts the app.
"""
import json
import os
import sys
import urllib.request

import yaml

OPTIONS = '/data/options.json'
CONFIG = '/data/config.yml'


def supervisor_mqtt():
    token = os.environ.get('SUPERVISOR_TOKEN')
    if not token:
        return None
    try:
        req = urllib.request.Request('http://supervisor/services/mqtt',
                                     headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r).get('data') or None
    except Exception as e:
        print('Could not read MQTT details from the Supervisor: %s' % e, flush=True)
        return None


def main():
    with open(OPTIONS) as f:
        opts = json.load(f)

    server, port = opts.get('mqtt_server'), opts.get('mqtt_port')
    user, password = opts.get('mqtt_username'), opts.get('mqtt_password')
    if not server:
        svc = supervisor_mqtt()
        if svc:
            server, port = svc.get('host'), port or svc.get('port')
            user, password = user or svc.get('username'), password or svc.get('password')
            print('Using the MQTT broker from Home Assistant: %s:%s' % (server, port), flush=True)
    if not server:
        print('No MQTT broker configured. Set mqtt_server in the add-on configuration, '
              'or install the Mosquitto broker add-on.', flush=True)
        sys.exit(1)

    config = {
        'frigate': {
            'frigate_url': opts['frigate_url'].rstrip('/'),
            'mqtt_server': server,
            'mqtt_port': int(port or 1883),
            'mqtt_auth': bool(user),
            'mqtt_username': user or '',
            'mqtt_password': password or '',
            'main_topic': opts.get('frigate_topic') or 'frigate',
            'camera': opts.get('cameras') or ['birdcam'],
            'object': 'bird',
        },
        'classification': {'model': '/app/model.tflite', 'threshold': float(opts.get('threshold', 0.7))},
        'webui': {'port': 7766, 'host': '0.0.0.0'},
    }
    with open(CONFIG, 'w') as f:
        yaml.safe_dump(config, f)
    os.chmod(CONFIG, 0o600)

    env = dict(os.environ, WAMF_DATA_DIR='/data', WAMF_CONFIG=CONFIG, WAMF_NAMES_DB='/app/birdnames.db')
    os.chdir('/app')
    os.execve(sys.executable, [sys.executable, '/app/speciesid.py'], env)


if __name__ == '__main__':
    main()
