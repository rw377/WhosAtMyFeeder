"""Frigate API helpers and the local snapshot cache.

Snapshots are copied to <data>/snapshots when a bird is detected, so pictures
outlive Frigate's own retention. Event ids are validated before they are used
in a URL or a file path.
"""
import json
import os
import re
import time

import requests

from db import DATA_DIR

SNAP_DIR = os.path.join(DATA_DIR, 'snapshots')
EVENT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*$')
TIMEOUT = 10
_down_until = 0.0   # after a connection error, don't ask Frigate again for a while


def valid_event(event_id):
    return bool(event_id) and len(event_id) <= 80 and EVENT_RE.match(event_id) is not None


def snapshot_path(event_id, kind):
    """kind: 'crop' (bird crop used for thumbnails) or 'full' (whole frame)."""
    if not valid_event(event_id) or kind not in ('crop', 'full'):
        raise ValueError('bad event id')
    return os.path.join(SNAP_DIR, '%s.%s.jpg' % (event_id, kind))


def save_snapshot(event_id, kind, content):
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = snapshot_path(event_id, kind)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(content)
    os.replace(tmp, path)
    return path


def fetch_snapshot(frigate_url, event_id, kind, with_status=False):
    """Download from Frigate. Returns bytes or None (or (bytes, gone) with with_status,
    where gone means Frigate answered and no longer has the event)."""
    global _down_until
    content, gone = None, False
    if frigate_url and valid_event(event_id) and time.time() >= _down_until:
        params = {'crop': 1, 'quality': 90} if kind == 'crop' else {'quality': 90}
        try:
            r = requests.get('%s/api/events/%s/snapshot.jpg' % (frigate_url.rstrip('/'), event_id),
                             params=params, timeout=TIMEOUT)
            if r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image/'):
                content = r.content
            elif r.status_code in (404, 410):
                gone = True
        except requests.RequestException as e:
            _down_until = time.time() + 300  # e.g. Frigate removed: don't stall every thumbnail
            print('Frigate snapshot fetch failed for %s: %s (not retrying for 5 minutes)' % (event_id, e), flush=True)
    return (content, gone) if with_status else content


def _missing_marker(event_id):
    return os.path.join(SNAP_DIR, 'missing', event_id)


def cached_events():
    """Event ids that have a cached picture."""
    if not os.path.isdir(SNAP_DIR):
        return set()
    return {n[:-len('.crop.jpg')] for n in os.listdir(SNAP_DIR) if n.endswith('.crop.jpg')}


def missing_events():
    """Event ids Frigate has told us it no longer has."""
    d = os.path.join(SNAP_DIR, 'missing')
    return set(os.listdir(d)) if os.path.isdir(d) else set()


def get_snapshot(frigate_url, event_id, kind, cache=True):
    """Return a local path for the snapshot, fetching and caching it if needed."""
    path = snapshot_path(event_id, kind)
    if os.path.exists(path):
        return path
    if not frigate_url or event_id.startswith('bi-'):
        return None  # only the cache has these (Blue Iris events, or Frigate is gone)
    marker = _missing_marker(event_id)
    if os.path.exists(marker):
        return None  # Frigate already said it's gone; don't ask again on every page view
    content, gone = fetch_snapshot(frigate_url, event_id, kind, with_status=True)
    if content is None:
        if gone:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            open(marker, 'w').close()
        return None
    if cache:
        return save_snapshot(event_id, kind, content)
    tmp_dir = os.path.join(SNAP_DIR, 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    p = os.path.join(tmp_dir, os.path.basename(path))
    with open(p, 'wb') as f:
        f.write(content)
    return p


def delete_snapshots(event_id):
    for kind in ('crop', 'full'):
        try:
            os.remove(snapshot_path(event_id, kind))
        except (OSError, ValueError):
            pass


def cache_usage():
    total, count = 0, 0
    if os.path.isdir(SNAP_DIR):
        for name in os.listdir(SNAP_DIR):
            p = os.path.join(SNAP_DIR, name)
            if os.path.isfile(p):
                total += os.path.getsize(p)
                count += 1
    return {'bytes': total, 'files': count}


def clip_response(frigate_url, event_id):
    if not frigate_url or not valid_event(event_id):
        return None
    try:
        r = requests.get('%s/api/events/%s/clip.mp4' % (frigate_url.rstrip('/'), event_id),
                         stream=True, timeout=TIMEOUT)
        if r.status_code == 200:
            return r
    except requests.RequestException as e:
        print('Frigate clip fetch failed for %s: %s' % (event_id, e), flush=True)
    return None


def set_sublabel(frigate_url, event_id, sublabel):
    if not frigate_url or not valid_event(event_id):
        return False
    sublabel = sublabel[:20]  # Frigate limits sub labels to 20 characters
    try:
        r = requests.post('%s/api/events/%s/sub_label' % (frigate_url.rstrip('/'), event_id),
                          data=json.dumps({'subLabel': sublabel}),
                          headers={'Content-Type': 'application/json'}, timeout=TIMEOUT)
        ok = r.status_code == 200
        print(('Sublabel set to: %s' % sublabel) if ok else ('Failed to set sublabel: %s' % r.status_code), flush=True)
        return ok
    except requests.RequestException as e:
        print('Failed to set sublabel: %s' % e, flush=True)
        return False


CAMERA_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def valid_camera(name):
    return bool(name) and CAMERA_RE.match(name) is not None


def list_cameras(frigate_url):
    """Cameras defined in Frigate, with whether each one tracks birds.
    Returns (cameras, error)."""
    try:
        r = requests.get('%s/api/config' % frigate_url.rstrip('/'), timeout=TIMEOUT)
        r.raise_for_status()
        cfg = r.json()
    except (requests.RequestException, ValueError) as e:
        return [], 'Could not read cameras from Frigate at %s: %s' % (frigate_url, e)
    global_track = ((cfg.get('objects') or {}).get('track')) or ['person']
    out = []
    for name, cam in sorted((cfg.get('cameras') or {}).items()):
        track = ((cam.get('objects') or {}).get('track')) or global_track
        out.append({
            'name': name,
            'enabled': cam.get('enabled', True) is not False,
            'tracks_bird': 'bird' in track,
            'snapshots': bool((cam.get('snapshots') or {}).get('enabled', (cfg.get('snapshots') or {}).get('enabled'))),
        })
    return out, None


def latest_frame(frigate_url, camera, height=720):
    """Current frame from a Frigate camera as JPEG bytes, or None."""
    if not valid_camera(camera):
        return None
    try:
        r = requests.get('%s/api/%s/latest.jpg' % (frigate_url.rstrip('/'), camera),
                         params={'h': int(height), 'quality': 80}, timeout=TIMEOUT)
        if r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image/'):
            return r.content
    except requests.RequestException as e:
        print('Frigate live frame failed for %s: %s' % (camera, e), flush=True)
    return None


def backfill(frigate_url, event_ids, progress=None):
    """Copy Frigate's pictures for these events into the cache (both crop and full),
    skipping ones already cached or known gone. progress(dict) is called as it goes.
    Run this before removing Frigate so old detections keep their pictures."""
    global _down_until
    _down_until = 0.0
    have, gone = cached_events(), missing_events()
    todo = [e for e in event_ids if valid_event(e) and not e.startswith('bi-') and e not in have and e not in gone]
    st = {'total': len(todo), 'done': 0, 'saved': 0, 'gone': 0, 'failed': 0}
    for ev in todo:
        got = 0
        for kind in ('crop', 'full'):
            if os.path.exists(snapshot_path(ev, kind)):
                got += 1
                continue
            content, is_gone = fetch_snapshot(frigate_url, ev, kind, with_status=True)
            if content:
                save_snapshot(ev, kind, content)
                got += 1
            elif is_gone:
                m = _missing_marker(ev)
                os.makedirs(os.path.dirname(m), exist_ok=True)
                open(m, 'w').close()
                st['gone'] += 1
                break
            else:
                st['failed'] += 1
                break
        st['saved'] += 1 if got == 2 else 0
        st['done'] += 1
        if progress:
            progress(dict(st))
        if time.time() < _down_until:
            st['error'] = 'Frigate stopped answering at %s' % frigate_url
            break
    return st


def frigate_ui_link(frigate_url):
    """Where the browser can open Frigate's own UI. Inside Home Assistant, Frigate's
    add-on host name (e.g. ccab4aaf-frigate) maps to its ingress path."""
    from urllib.parse import urlparse
    if not frigate_url:
        return None
    host = urlparse(frigate_url).hostname or ''
    m = re.match(r'^([0-9a-f]{8})-(frigate[a-z0-9_-]*)$', host)
    if m:
        return {'url': '/hassio/ingress/%s_%s' % (m.group(1), m.group(2).replace('-', '_')), 'ingress': True}
    return {'url': frigate_url, 'ingress': False}
