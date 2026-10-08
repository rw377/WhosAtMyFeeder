"""Frigate API helpers and the local snapshot cache.

Snapshots are copied to <data>/snapshots when a bird is detected, so pictures
outlive Frigate's own retention. Event ids are validated before they are used
in a URL or a file path.
"""
import json
import os
import re

import requests

from db import DATA_DIR

SNAP_DIR = os.path.join(DATA_DIR, 'snapshots')
EVENT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*$')
TIMEOUT = 10


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


def fetch_snapshot(frigate_url, event_id, kind):
    """Download from Frigate. Returns bytes or None."""
    if not valid_event(event_id):
        return None
    params = {'crop': 1, 'quality': 90} if kind == 'crop' else {'quality': 90}
    try:
        r = requests.get('%s/api/events/%s/snapshot.jpg' % (frigate_url.rstrip('/'), event_id),
                         params=params, timeout=TIMEOUT)
        if r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image/'):
            return r.content
    except requests.RequestException as e:
        print('Frigate snapshot fetch failed for %s: %s' % (event_id, e), flush=True)
    return None


def get_snapshot(frigate_url, event_id, kind, cache=True):
    """Return a local path for the snapshot, fetching and caching it if needed."""
    path = snapshot_path(event_id, kind)
    if os.path.exists(path):
        return path
    content = fetch_snapshot(frigate_url, event_id, kind)
    if content is None:
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
    if not valid_event(event_id):
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
    if not valid_event(event_id):
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
