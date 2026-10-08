"""MQTT publishing: per-detection topics, species alerts, status and HA discovery.

Topics (prefix defaults to "whosatmyfeeder"):
  <prefix>/status      online/offline (retained, MQTT last will)
  <prefix>/last        JSON of the most recent detection (retained) -> "Last bird" sensor
  <prefix>/snapshot    JPEG of the most recent detection (retained) -> "Last bird" camera
  <prefix>/detection   every detection, when "Publish every detection" is on
  <prefix>/alert       watchlist matches, life-list firsts and returning species
  whosatmyfeeder/detections   plain common name, the original app's topic (optional)
"""
import json
import time
from datetime import datetime, timedelta

import db

LEGACY_TOPIC = 'whosatmyfeeder/detections'


def _hm(s):
    h, m = s.split(':')[:2]
    return int(h) * 60 + int(m)


def in_quiet_hours(quiet, now):
    if not quiet.get('enabled'):
        return False
    try:
        start, end = _hm(quiet['start']), _hm(quiet['end'])
    except (KeyError, ValueError):
        return False
    t = now.hour * 60 + now.minute
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end  # wraps past midnight


def alert_reasons(settings, det, watch, prev_seen, last_alert, now):
    """Decide whether a detection should raise an alert.

    det:        dict with score, flagged, first_ever
    watch:      watchlist row (dict) for this species, or None
    prev_seen:  datetime of the previous detection of this species, or None
    last_alert: datetime of the last watchlist alert for this species, or None
    Returns (reasons, suppressed_reason_or_None).
    """
    a = settings['alerts']
    if not a.get('enabled'):
        return [], 'alerts off'
    reasons = []
    if a.get('new_species') and det.get('first_ever'):
        reasons.append('new_species')
    if (a.get('returning') and prev_seen is not None and
            now - prev_seen >= timedelta(days=int(a.get('returning_days') or 30))):
        reasons.append('returning')
    if watch and watch.get('enabled') and det['score'] >= float(watch.get('min_score') or 0):
        cooldown = timedelta(minutes=int(watch.get('cooldown_min') or 0))
        if last_alert is None or now - last_alert >= cooldown:
            reasons.append('watchlist')
    if not reasons:
        return [], None
    if in_quiet_hours(settings['quiet'], now):
        if 'new_species' in reasons and settings['quiet'].get('allow_new_species'):
            return ['new_species'], None
        return [], 'quiet hours'
    return reasons, None


def build_payload(settings, det, reason=None, first_of_season=False):
    base = (settings['snapshots'].get('base_url') or '').rstrip('/')
    p = {
        'common_name': det['common_name'],
        'scientific_name': det['scientific_name'],
        'confidence': round(float(det['score']), 3),
        'camera': det['camera'],
        'time': det['time'],
        'frigate_event': det['frigate_event'],
        'snapshot_url': '%s/snap/%s.jpg' % (base, det['frigate_event']) if base else None,
        'first_ever': bool(det.get('first_ever')),
        'first_of_season': bool(first_of_season),
        'flagged': bool(det.get('flagged')),
    }
    if reason:
        p['reason'] = reason
    return p


class Notifier(object):
    def __init__(self, client):
        self.client = client
        self.sent = []  # (topic, payload) of recent publishes, handy for tests/logs

    def _pub(self, topic, payload, retain=False, qos=1):
        if not isinstance(payload, (bytes, bytearray)) and not isinstance(payload, str):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, qos=qos, retain=retain)
        self.sent.append((topic, payload))
        self.sent = self.sent[-50:]

    # -------------------------------------------------------------- connection

    def on_connect(self, settings):
        prefix = settings['mqtt']['topic_prefix']
        self._pub(prefix + '/status', 'online', retain=True)
        if settings['mqtt'].get('discovery'):
            self.publish_discovery(prefix)

    def publish_discovery(self, prefix):
        device = {'identifiers': ['whosatmyfeeder'], 'name': "Who's At My Feeder",
                  'manufacturer': 'WhosAtMyFeeder', 'model': 'Bird species ID'}
        avail = {'availability_topic': prefix + '/status'}
        configs = {
            'homeassistant/sensor/whosatmyfeeder/last_bird/config': dict(avail, **{
                'name': 'Last bird', 'unique_id': 'whosatmyfeeder_last_bird', 'object_id': 'whosatmyfeeder_last_bird',
                'state_topic': prefix + '/last', 'value_template': '{{ value_json.common_name }}',
                'json_attributes_topic': prefix + '/last', 'icon': 'mdi:bird', 'device': device}),
            'homeassistant/camera/whosatmyfeeder/last_bird/config': dict(avail, **{
                'name': 'Last bird snapshot', 'unique_id': 'whosatmyfeeder_last_bird_snapshot',
                'object_id': 'whosatmyfeeder_last_bird_snapshot', 'topic': prefix + '/snapshot', 'device': device}),
            'homeassistant/binary_sensor/whosatmyfeeder/status/config': {
                'name': 'Online', 'unique_id': 'whosatmyfeeder_online', 'object_id': 'whosatmyfeeder_online',
                'state_topic': prefix + '/status', 'payload_on': 'online', 'payload_off': 'offline',
                'device_class': 'connectivity', 'device': device},
        }
        for topic, cfg in configs.items():
            self._pub(topic, cfg, retain=True)

    # -------------------------------------------------------------- detections

    def on_detection(self, conn, settings, det, prev_seen, snapshot_bytes=None, now=None):
        """Called once per new detection (or when a detection's species changes)."""
        now = now or datetime.now()
        prefix = settings['mqtt']['topic_prefix']
        returning_days = int(settings['alerts'].get('returning_days') or 30)
        first_of_season = prev_seen is not None and now - prev_seen >= timedelta(days=returning_days)

        if settings['mqtt'].get('legacy_topic'):
            self._pub(LEGACY_TOPIC, det['common_name'], qos=0)

        payload = build_payload(settings, det, first_of_season=first_of_season)
        if snapshot_bytes:
            self._pub(prefix + '/snapshot', snapshot_bytes, retain=True)
        self._pub(prefix + '/last', payload, retain=True)

        pa = settings['publish_all']
        if pa.get('enabled'):
            min_score = pa.get('min_score')
            if not (pa.get('skip_flagged') and det.get('flagged')) and (min_score is None or det['score'] >= float(min_score)):
                self._pub(prefix + '/detection', payload)

        watch = conn.execute("SELECT * FROM watchlist WHERE scientific_name = ?",
                             (det['scientific_name'],)).fetchone()
        watch = dict(watch) if watch else None
        last = conn.execute("""SELECT MAX(sent_at) FROM alert_log WHERE scientific_name = ? AND reason LIKE '%watchlist%'""",
                            (det['scientific_name'],)).fetchone()[0]
        last_alert = datetime.strptime(last[:19], '%Y-%m-%d %H:%M:%S') if last else None
        reasons, suppressed = alert_reasons(settings, det, watch, prev_seen, last_alert, now)
        if suppressed:
            print('Alert for %s suppressed: %s' % (det['common_name'], suppressed), flush=True)
        if not reasons:
            return []
        reason = ','.join(reasons)
        self._pub(prefix + '/alert', build_payload(settings, det, reason=reason, first_of_season=first_of_season))
        conn.execute("INSERT INTO alert_log(scientific_name, frigate_event, reason, sent_at) VALUES (?, ?, ?, ?)",
                     (det['scientific_name'], det['frigate_event'], reason, now.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        print('Alert published for %s (%s)' % (det['common_name'], reason), flush=True)
        return reasons


# ------------------------------------------------------------------ one-off client for the web UI

def mqtt_client_from_config(config, client_id):
    import paho.mqtt.client as mqtt
    f = config['frigate']
    client = mqtt.Client(client_id)
    if f.get('mqtt_auth'):
        client.username_pw_set(f.get('mqtt_username'), f.get('mqtt_password'))
    return client


def mqtt_port(config):
    return int(config['frigate'].get('mqtt_port') or 1883)


def send_test(config, settings):
    """Publish a sample alert from the web process. Returns (ok, message)."""
    prefix = settings['mqtt']['topic_prefix']
    try:
        client = mqtt_client_from_config(config, 'whosatmyfeeder-test-%d' % int(time.time()))
        client.connect(config['frigate']['mqtt_server'], mqtt_port(config), keepalive=10)
        client.loop_start()
        det = {'common_name': 'Test bird', 'scientific_name': 'Testus birdus', 'score': 0.99,
               'camera': 'test', 'time': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
               'frigate_event': 'test', 'first_ever': False, 'flagged': False}
        info = client.publish(prefix + '/alert', json.dumps(build_payload(settings, det, reason='test')), qos=1)
        deadline = time.time() + 5
        while not info.is_published() and time.time() < deadline:
            time.sleep(0.1)
        ok = info.is_published()
        client.loop_stop()
        client.disconnect()
        return (True, 'Published to %s/alert' % prefix) if ok else (False, 'Broker did not acknowledge the message')
    except Exception as e:  # connection refused, DNS, auth...
        return False, 'Could not reach the broker: %s' % e
