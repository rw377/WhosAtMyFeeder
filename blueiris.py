"""Blue Iris as the event source (instead of Frigate).

Blue Iris publishes an MQTT message when a camera alert is confirmed by its AI
(CodeProject.AI). The alert action is set up to send:

    topic:   BlueIris/&CAM/alert
    payload: {"id":"&ALERT_DB","path":"&ALERT_PATH","camera":"&CAM","detections":&JSON}

&ALERT_DB is the alert's database id (used as the event id). The alert image is
served at /alerts/&ALERT_PATH; /alerts/&ALERT_DB is tried too, for payloads
without "path".

for example (camera names are case-sensitive):

    {"id":"@406413738801416","camera":"BirdFeeder","detections":[{"api":"objects",
     "found":{"predictions":[{"confidence":0.91,"label":"bird","x_min":685,"y_min":359,
     "x_max":1704,"y_max":1067}],"timestampUTC":"Sat, 31 Oct 2026 15:16:20 GMT",...}}]}

Test alerts (id "@-1") and alerts with no "bird" prediction are ignored. Boxes are
in main-stream pixels; they are scaled to the alert image if its size differs.

This module turns that message into the same event the Frigate path produces:
an event id, the camera, a time, the bird crop (what gets classified) and the
full frame. There is no "end" message, so presence relies on expiry.

Pictures come from Blue Iris's web server. Logging in uses Blue Iris's JSON API
(a session key, so the password never goes in a URL); if that fails, HTTP Basic
auth is tried.
"""
import hashlib
import re
import threading
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from urllib.parse import quote

import requests
from PIL import Image

TIMEOUT = 10
BIRD = 'bird'
PAD = 0.12          # grow the bird box by this fraction of its size on each side
MIN_PAD_PX = 12

ALERT_RE = re.compile(r'^@?[A-Za-z0-9][A-Za-z0-9._-]{0,70}$')
PATH_RE = re.compile(r'^@?[A-Za-z0-9][A-Za-z0-9@._-]{0,200}$')   # a file name, no slashes
RETRY_AFTER = 1.5   # the alert image can lag the MQTT message slightly


def bi_config(config):
    return config.get('blueiris') or {}


# ------------------------------------------------------------------ ids

def event_id(alert_id):
    """Blue Iris alert id (e.g. "@1234567") -> an id frigate.valid_event() accepts
    ("bi-1234567"). Returns None if nothing usable is left."""
    s = re.sub(r'[^A-Za-z0-9_-]', '', str(alert_id or ''))
    if not s:
        return None
    return ('bi-' + s)[:80]


def valid_alert(alert_id):
    return bool(alert_id) and ALERT_RE.match(alert_id) is not None


# ------------------------------------------------------------------ HTTP / auth

class Client(object):
    """Talks to the Blue Iris web server, keeping one login session."""

    def __init__(self, url, username='', password=''):
        self.url = (url or '').rstrip('/')
        self.username = username or ''
        self.password = password or ''
        self._session = None
        self._basic = False
        self._lock = threading.Lock()
        self._http = requests.Session()
        self._cam_size = {}       # camera -> (width, height), from camlist
        self._cam_size_at = 0.0

    def _login(self):
        """JSON API login: ask for a session, answer with md5(user:session:password)."""
        self._session, self._basic = None, False
        if not self.username:
            return  # Blue Iris configured without authentication for this client
        try:
            r = self._http.post(self.url + '/json', json={'cmd': 'login'}, timeout=TIMEOUT)
            sess = r.json().get('session')
            resp = hashlib.md5(('%s:%s:%s' % (self.username, sess, self.password)).encode()).hexdigest()
            r = self._http.post(self.url + '/json', json={'cmd': 'login', 'session': sess, 'response': resp},
                                timeout=TIMEOUT)
            data = r.json()
            if data.get('result') == 'success':
                self._session = data.get('session') or sess
                return
            print('Blue Iris login refused (%s); trying HTTP Basic auth' % (data.get('data') or {}).get('reason', data.get('result')),
                  flush=True)
        except (requests.RequestException, ValueError, AttributeError) as e:
            print('Blue Iris JSON login failed (%s); trying HTTP Basic auth' % e, flush=True)
        self._basic = True

    def _get(self, path, params=None):
        params = dict(params or {})
        auth = None
        with self._lock:
            if self.username and self._session is None and not self._basic:
                self._login()
            if self._session:
                params['session'] = self._session
            elif self._basic:
                auth = (self.username, self.password)
        return self._http.get(self.url + path, params=params, auth=auth, timeout=TIMEOUT)

    def _json(self, cmd, **kw):
        with self._lock:
            if self.username and self._session is None and not self._basic:
                self._login()
            body = dict(kw, cmd=cmd)
            if self._session:
                body['session'] = self._session
        r = self._http.post(self.url + '/json', json=body, timeout=TIMEOUT)
        return r.json()

    def image(self, path, params=None, quiet=False, with_status=False):
        """GET an image. Logs in again once if the session expired. Returns bytes or None
        (or (bytes, status) with with_status)."""
        status = None
        for attempt in (1, 2):
            try:
                r = self._get(path, params)
            except requests.RequestException as e:
                print('Blue Iris request %s failed: %s' % (path, e), flush=True)
                return (None, None) if with_status else None
            status = r.status_code
            if r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image/'):
                return (r.content, 200) if with_status else r.content
            # An expired session comes back as the login page (200 text/html) or 401/403;
            # a 404 is a real "not found", so don't log in again for it.
            if attempt == 1 and self.username and r.status_code != 404:
                with self._lock:
                    self._session, self._basic = None, False
                continue
            if not quiet:
                print('Blue Iris %s returned %s %s' % (path, r.status_code, r.headers.get('Content-Type', '')), flush=True)
            break
        return (None, status) if with_status else None

    def alert_image(self, alert_id, alert_path=None):
        """The alert's full-resolution JPEG: /alerts/<&ALERT_PATH>, else /alerts/<&ALERT_DB>,
        each with ?fulljpeg then without. If everything is 404, try once more after a
        moment in case the image isn't written yet."""
        names = []
        if alert_path:
            if PATH_RE.match(alert_path):
                names.append(alert_path)
            else:
                print('Blue Iris alert path %r looks wrong; not using it' % alert_path, flush=True)
        if valid_alert(alert_id):
            names.append(alert_id)
        tried = []
        for round_ in (1, 2):
            only_404 = True
            for name in names:
                for params in ({'fulljpeg': ''}, None):
                    path = '/alerts/%s' % quote(name, safe='@')
                    data, status = self.image(path, params, quiet=True, with_status=True)
                    if data:
                        if round_ > 1 or name != names[0] or params is None:
                            print('Blue Iris alert image came from %s%s%s' %
                                  (path, '?fulljpeg' if params else '', ' (after a retry)' if round_ > 1 else ''), flush=True)
                        return data
                    tried.append('%s%s -> %s' % (path, '?fulljpeg' if params else '', status))
                    only_404 = only_404 and status == 404
            if not only_404 or not names:
                break
            time.sleep(RETRY_AFTER)
        print('Blue Iris alert image not found. Tried: %s' % '; '.join(tried), flush=True)
        if not alert_path:
            print('Add "path":"&ALERT_PATH" to the Blue Iris alert payload: the image is served by its path, '
                  'not its database id.', flush=True)
        return None

    def live_image(self, camera, height=720):
        return self.image('/image/%s' % quote(camera, safe=''), {'h': int(height), 'q': 80})

    def camera_size(self, camera):
        """Native (main stream) resolution of a camera from camlist, or None.
        Refreshed at most every 10 minutes."""
        if time.time() - self._cam_size_at > 600:
            self._cam_size_at = time.time()
            try:
                data = self._json('camlist')
                sizes = {}
                for c in data.get('data') or []:
                    w, h = c.get('width'), c.get('height')
                    if c.get('optionValue') and w and h:
                        sizes[c['optionValue']] = (int(w), int(h))
                self._cam_size = sizes
            except (requests.RequestException, ValueError, TypeError, AttributeError) as e:
                print('Blue Iris camlist failed: %s' % e, flush=True)
        return self._cam_size.get(camera)


_client = None


def client(config):
    global _client
    c = bi_config(config)
    if _client is None or _client.url != (c.get('url') or '').rstrip('/'):
        _client = Client(c.get('url'), c.get('username'), c.get('password'))
    return _client


# ------------------------------------------------------------------ detections → crop

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _utc_to_local(stamp):
    """"Sat, 31 Oct 2026 15:16:20 GMT" -> naive local datetime, or None."""
    try:
        dt = parsedate_to_datetime(str(stamp))
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None or dt.tzinfo is None:
        return None
    return dt.astimezone().replace(tzinfo=None)


def predictions(detections):
    """Every box in Blue Iris's &JSON (CodeProject.AI results):
    detections[*].found.predictions[*], each with the found block's timestampUTC."""
    out = []
    for d in detections if isinstance(detections, list) else [detections]:
        found = d.get('found') if isinstance(d, dict) else None
        if not isinstance(found, dict):
            continue
        for p in found.get('predictions') or []:
            if not isinstance(p, dict) or 'label' not in p:
                continue
            box = [_num(p.get(k)) for k in ('x_min', 'y_min', 'x_max', 'y_max')]
            if None in box:
                continue
            out.append({'label': str(p['label']), 'confidence': _num(p.get('confidence')) or 0.0, 'box': box,
                        'timestamp': found.get('timestampUTC')})
    return out


def best_bird(detections):
    birds = [p for p in predictions(detections) if p['label'] == BIRD]
    return max(birds, key=lambda p: p['confidence']) if birds else None


def crop_box(box, image_size, ref_size=None, pad=PAD):
    """Scale a box from main-stream pixels (ref_size) to the alert image's real size
    when they differ, clamp it to the image, pad it, and clamp again."""
    W, H = image_size
    x1, y1, x2, y2 = box
    if ref_size and tuple(ref_size) != (W, H):
        sx, sy = W / float(ref_size[0]), H / float(ref_size[1])
    else:
        sx = sy = 1.0
    x1, x2 = sorted((min(max(x1 * sx, 0), W), min(max(x2 * sx, 0), W)))
    y1, y2 = sorted((min(max(y1 * sy, 0), H), min(max(y2 * sy, 0), H)))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    px = max(MIN_PAD_PX, (x2 - x1) * pad)
    py = max(MIN_PAD_PX, (y2 - y1) * pad)
    x1, y1 = max(0, int(x1 - px)), max(0, int(y1 - py))
    x2, y2 = min(W, int(round(x2 + px))), min(H, int(round(y2 + py)))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return x1, y1, x2, y2


def crop(full_bytes, box, ref_size=None):
    """JPEG bytes of the padded bird crop, or None."""
    im = Image.open(BytesIO(full_bytes)).convert('RGB')
    area = crop_box(box, im.size, ref_size)
    if area is None:
        return None
    out = BytesIO()
    im.crop(area).save(out, 'JPEG', quality=92)
    return out.getvalue()


# ------------------------------------------------------------------ MQTT message → event

def parse_alert(payload, topic=None, now=None):
    """Cheap part (no HTTP): the ids, camera and bird box from a Blue Iris message.
    Returns a dict, or None if this message isn't something to process."""
    if not isinstance(payload, dict):
        return None
    alert_id = str(payload.get('id') or '').strip()
    cam = str(payload.get('camera') or '').strip()  # Blue Iris short name, case-sensitive
    if not cam and topic:
        parts = topic.split('/')
        cam = parts[-2] if len(parts) >= 2 else ''
    if alert_id == '@-1':
        print('Blue Iris test alert from %s; ignoring' % cam, flush=True)
        return None
    if not valid_alert(alert_id):
        print('Blue Iris alert with unexpected id %r; ignoring' % alert_id, flush=True)
        return None
    bird = best_bird(payload.get('detections'))
    if bird is None:
        # Not logged here: other cameras' alerts often share the topic. The caller
        # logs it for cameras it watches.
        labels = sorted({p['label'] for p in predictions(payload.get('detections'))})
        return {'id': event_id(alert_id), 'alert_id': alert_id, 'camera': cam, 'box': None, 'labels': labels}
    return {
        'id': event_id(alert_id),
        'alert_id': alert_id,
        'path': str(payload.get('path') or '').strip() or None,
        'camera': cam,
        # When CodeProject.AI analysed the frame; else when the message arrived.
        'time': _utc_to_local(bird.get('timestamp')) or now or datetime.now(),
        'box': bird['box'],
        'ai_confidence': bird['confidence'],
    }


_logged_scale = set()


def fetch_images(config, ev):
    """Download the alert frame and cut out the bird. Returns (crop, full) bytes or (None, None)."""
    c = client(config)
    full = c.alert_image(ev['alert_id'], ev.get('path'))
    if full is None:
        print('Could not get the alert image for %s from Blue Iris' % ev['alert_id'], flush=True)
        return None, None
    ref = c.camera_size(ev['camera'])
    if ev['camera'] not in _logged_scale:
        _logged_scale.add(ev['camera'])
        size = Image.open(BytesIO(full)).size
        print('Blue Iris %s: alert image %sx%s, camera resolution %s, first bird box %s' %
              (ev['camera'], size[0], size[1], '%sx%s' % ref if ref else 'unknown (using image size)',
               [round(v) for v in ev['box']]), flush=True)
    if ref is None:
        size = Image.open(BytesIO(full)).size
        if ev['box'][2] > size[0] * 1.02 or ev['box'][3] > size[1] * 1.02:
            print('Bird box %s is outside the %sx%s alert image and the main-stream size is unknown '
                  '(Blue Iris camlist failed), so the crop will be wrong. Check the Blue Iris user can list cameras.'
                  % ([round(v) for v in ev['box']], size[0], size[1]), flush=True)
    try:
        cropped = crop(full, ev['box'], ref)
    except (OSError, ValueError) as e:
        print('Could not crop the alert image for %s: %s' % (ev['alert_id'], e), flush=True)
        return None, None
    if cropped is None:
        print('Bird box %s is empty after scaling; skipping %s' % (ev['box'], ev['alert_id']), flush=True)
        return None, None
    return cropped, full


# ------------------------------------------------------------------ web UI helpers

def list_cameras(config, watched=()):
    """Blue Iris mode: the configured cameras (Blue Iris decides what is a bird)."""
    cams = (config.get('frigate') or {}).get('camera') or []
    cams = [cams] if isinstance(cams, str) else list(cams)
    names = sorted(set(cams) | set(watched or ()))
    return [{'name': n, 'enabled': True, 'tracks_bird': None, 'snapshots': None} for n in names], None


def latest_frame(config, camera, height=720):
    return client(config).live_image(camera, height)


def ui_link(config):
    url = bi_config(config).get('url') or ''
    return {'url': url, 'ingress': False, 'label': 'Blue Iris'} if url else None
