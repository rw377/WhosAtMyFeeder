import json
import multiprocessing
import sys
import time
from datetime import datetime
from io import BytesIO

import numpy as np
import paho.mqtt.client as mqtt
import requests
from PIL import Image, ImageOps

import db
import frigate
import notifier as notifier_mod

classifier = None
config = None
notifier = None
firstmessage = True

BACKGROUND_INDEX = 964  # the model's "background" class


def classify(image):
    from tflite_support.task import vision
    tensor_image = vision.TensorImage.create_from_array(image)
    categories = classifier.classify(tensor_image)
    return categories.classifications[0].categories


def threshold_for(settings, prefs):
    if prefs is not None and prefs['min_score'] is not None:
        return float(prefs['min_score'])
    t = settings['detection'].get('threshold')
    return float(t) if t is not None else float(config['classification']['threshold'])


def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print("MQTT connection refused, code %s" % rc, flush=True)
        db.set_runtime('mqtt', {'connected': False, 'error': 'connection refused (code %s)' % rc,
                                'since': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})
        return
    print("MQTT Connected", flush=True)
    client.subscribe(config['frigate']['main_topic'] + "/events")
    db.set_runtime('mqtt', {'connected': True, 'since': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})
    notifier.on_connect(db.get_settings())


def on_disconnect(client, userdata, rc):
    print("MQTT disconnected (rc=%s); paho will reconnect" % rc, flush=True)
    db.set_runtime('mqtt', {'connected': False, 'since': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})


def on_message(client, userdata, message):
    global firstmessage
    if firstmessage:
        firstmessage = False
        print("skipping first message", flush=True)
        return
    try:
        handle_event(json.loads(message.payload))
    except Exception as e:  # never let one bad event kill the MQTT loop
        print("Error handling event: %r" % e, flush=True)


def handle_event(payload_dict):
    after_data = payload_dict.get('after', {})
    cameras = config['frigate']['camera']
    if isinstance(cameras, str):
        cameras = [cameras]
    if after_data.get('camera') not in cameras or after_data.get('label') != 'bird':
        return

    frigate_event = after_data['id']
    frigate_url = config['frigate']['frigate_url']
    if not frigate.valid_event(frigate_event):
        print("Ignoring event with unexpected id: %r" % frigate_event, flush=True)
        return

    response = requests.get(frigate_url + "/api/events/" + frigate_event + "/snapshot.jpg",
                            params={"crop": 1, "quality": 95}, timeout=15)
    if response.status_code != 200:
        print("Error: Could not retrieve the image. Status code: %s" % response.status_code, flush=True)
        return

    image = Image.open(BytesIO(response.content)).convert('RGB')
    max_size = (224, 224)
    image.thumbnail(max_size)
    padded_image = ImageOps.expand(image, border=((max_size[0] - image.size[0]) // 2,
                                                  (max_size[1] - image.size[1]) // 2), fill='black')
    category = classify(np.array(padded_image))[0]
    index, score = category.index, category.score
    display_name, category_name = category.display_name, category.category_name

    start_time = datetime.fromtimestamp(after_data['start_time'])
    formatted_start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
    print("%s %s" % (formatted_start_time, category), flush=True)

    if index == BACKGROUND_INDEX:
        return

    settings = db.get_settings()
    conn = db.connect()
    try:
        prefs = conn.execute("SELECT * FROM species_prefs WHERE scientific_name = ?", (display_name,)).fetchone()
        if prefs is not None and prefs['hidden']:
            print("%s is hidden; ignoring" % display_name, flush=True)
            return
        if score <= threshold_for(settings, prefs):
            return

        existing = conn.execute("SELECT * FROM detections WHERE frigate_event = ?", (frigate_event,)).fetchone()
        if existing is not None and score <= existing['score']:
            print("Already have a better score for this event.", flush=True)
            return

        species_changed = existing is None or existing['display_name'] != display_name
        prev = conn.execute("SELECT MAX(detection_time) FROM detections WHERE display_name = ? AND frigate_event != ?",
                            (display_name, frigate_event)).fetchone()[0]
        prev_seen = datetime.strptime(prev[:19], '%Y-%m-%d %H:%M:%S') if prev else None
        first_ever = prev_seen is None
        det_settings = settings['detection']
        flagged = int(score < float(det_settings.get('review_below') or 0) or
                      (bool(det_settings.get('flag_first_sighting')) and first_ever))

        if existing is None:
            print("No record yet for this event. Storing.", flush=True)
            conn.execute("""INSERT INTO detections (detection_time, detection_index, score, display_name,
                            category_name, frigate_event, camera_name, flagged) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                         (formatted_start_time, index, score, display_name, category_name, frigate_event,
                          after_data['camera'], flagged))
        else:
            print("New score is higher. Updating record.", flush=True)
            conn.execute("""UPDATE detections SET detection_time = ?, detection_index = ?, score = ?, display_name = ?,
                            category_name = ?, flagged = CASE WHEN reviewed = 1 THEN flagged ELSE ? END
                            WHERE frigate_event = ?""",
                         (formatted_start_time, index, score, display_name, category_name, flagged, frigate_event))
        conn.commit()

        common = db.common_name(conn, display_name)
        frigate.set_sublabel(frigate_url, frigate_event, common)
        if settings['snapshots'].get('cache', True):
            frigate.save_snapshot(frigate_event, 'crop', response.content)
            full = frigate.fetch_snapshot(frigate_url, frigate_event, 'full')
            if full:
                frigate.save_snapshot(frigate_event, 'full', full)

        det = {'common_name': common, 'scientific_name': display_name, 'score': score,
               'camera': after_data['camera'], 'time': start_time.strftime('%Y-%m-%dT%H:%M:%S'),
               'frigate_event': frigate_event, 'first_ever': first_ever, 'flagged': bool(flagged)}
        db.set_runtime('last_detection', {'common_name': common, 'time': det['time']})
        if species_changed:
            notifier.on_detection(conn, settings, det, prev_seen, snapshot_bytes=response.content)
    finally:
        conn.close()


def run_webui():
    from waitress import serve
    from webui import app
    print("Starting web UI on %s:%s" % (config['webui']['host'], config['webui']['port']), flush=True)
    serve(app, host=config['webui']['host'], port=config['webui']['port'], threads=6)


def run_mqtt_client():
    global notifier
    server = config['frigate']['mqtt_server']
    port = notifier_mod.mqtt_port(config)
    print("Starting MQTT client. Connecting to: %s:%s" % (server, port), flush=True)
    client = notifier_mod.mqtt_client_from_config(config, "birdspeciesid" + datetime.now().strftime("%Y%m%d%H%M%S"))
    notifier = notifier_mod.Notifier(client)
    prefix = db.get_settings()['mqtt']['topic_prefix']
    client.will_set(prefix + '/status', 'offline', qos=1, retain=True)
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_connect = on_connect
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(server, port)
    client.loop_forever(retry_first_connection=True)


def load_config():
    global config
    config = db.load_config()


def main():
    print("Time: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), flush=True)
    print("Python " + sys.version, flush=True)

    load_config()
    db.migrate()

    # Load the model before starting anything. If it fails, still serve the web
    # UI (history, settings, import) and say why detection is off.
    global classifier
    try:
        from tflite_support.task import core, processor, vision
        base_options = core.BaseOptions(file_name=config['classification']['model'], use_coral=False, num_threads=4)
        classification_options = processor.ClassificationOptions(max_results=1, score_threshold=0)
        options = vision.ImageClassifierOptions(base_options=base_options, classification_options=classification_options)
        classifier = vision.ImageClassifier.create_from_options(options)
        db.set_runtime('detector_error', None)
        db.set_runtime('mqtt', {'connected': False, 'since': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})
    except Exception as e:
        print("Bird classifier failed to load, detection is OFF: %r" % e, flush=True)
        db.set_runtime('detector_error', str(e))
        db.set_runtime('mqtt', {'connected': False, 'error': 'detector not running',
                                'since': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')})

    print("Starting processes for the web UI and MQTT", flush=True)
    flask_process = multiprocessing.Process(target=run_webui)
    flask_process.start()
    if classifier is not None:
        mqtt_process = multiprocessing.Process(target=run_mqtt_client)
        mqtt_process.start()
        mqtt_process.join()
    flask_process.join()


if __name__ == '__main__':
    main()
