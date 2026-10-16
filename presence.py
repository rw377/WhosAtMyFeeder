"""Which birds are at the feeder right now.

Frigate sends a "new" event when it starts tracking a bird, "update" events while
it's there, and an "end" event when it leaves. Each tracked bird is kept here from
its first event until its "end" (or until it goes quiet for too long, in case an
"end" is missed), with the best species identification made for it so far.
"""
import threading
from datetime import datetime, timedelta

STALE_AFTER = timedelta(minutes=5)   # no news from Frigate for this long = gone
UNKNOWN = 'Unknown bird'   # a bird is there but hasn't been identified (yet)
NO_BIRD = 'No bird'        # nothing at the feeder. Not "None": Home Assistant reads a
                           # literal "None" from MQTT as no value and shows "Unknown".


class Presence(object):
    def __init__(self, publish):
        """publish(state_dict) is called whenever the answer changes."""
        self._publish = publish
        self._birds = {}          # frigate event id -> dict
        self._lock = threading.Lock()
        self._last = None

    # ------------------------------------------------------------- events

    def seen(self, event_id, camera, now=None):
        """A bird is being tracked (Frigate "new"/"update" event)."""
        now = now or datetime.now()
        with self._lock:
            b = self._birds.get(event_id)
            if b is None:
                b = self._birds[event_id] = {'camera': camera, 'since': now, 'scientific_name': None,
                                             'common_name': None, 'confidence': 0.0}
            b['updated'] = now
        self._changed(now)

    def identified(self, event_id, camera, scientific_name, common_name, confidence, now=None):
        """The classifier named this bird with enough confidence."""
        now = now or datetime.now()
        with self._lock:
            b = self._birds.get(event_id)
            if b is None:  # identification arrived before/without a tracking message
                b = self._birds[event_id] = {'camera': camera, 'since': now, 'confidence': 0.0}
            if confidence >= b.get('confidence', 0.0) or not b.get('scientific_name'):
                b.update(scientific_name=scientific_name, common_name=common_name, confidence=float(confidence))
            b['updated'] = now
        self._changed(now)

    def left(self, event_id, now=None):
        """Frigate's "end" event."""
        now = now or datetime.now()
        with self._lock:
            self._birds.pop(event_id, None)
        self._changed(now)

    def expire(self, now=None):
        """Drop birds Frigate hasn't mentioned for STALE_AFTER (a missed "end")."""
        now = now or datetime.now()
        with self._lock:
            for k in [k for k, b in self._birds.items() if now - b['updated'] > STALE_AFTER]:
                self._birds.pop(k)
        self._changed(now)

    def clear(self):
        with self._lock:
            self._birds.clear()
        self._last = None
        self._changed(datetime.now(), force=True)

    # ------------------------------------------------------------- state

    def state(self):
        with self._lock:
            birds = list(self._birds.values())
        if not birds:
            return {'present': False, 'status': 'none', 'common_name': NO_BIRD, 'scientific_name': None,
                    'confidence': None, 'camera': None, 'since': None, 'count': 0, 'species': []}
        named = [b for b in birds if b.get('scientific_name')]
        # Headline bird: the most confident identification; else the earliest arrival.
        lead = max(named, key=lambda b: b['confidence']) if named else min(birds, key=lambda b: b['since'])
        species = sorted({b['common_name'] for b in named})
        return {
            'present': True,
            'status': 'identified' if named else 'unidentified',
            'common_name': lead.get('common_name') or UNKNOWN,
            'scientific_name': lead.get('scientific_name'),
            'confidence': round(lead['confidence'], 3) if lead.get('scientific_name') else None,
            'camera': lead['camera'],
            'since': min(b['since'] for b in birds).strftime('%Y-%m-%dT%H:%M:%S'),
            'count': len(birds),
            'species': species,
        }

    def _changed(self, now, force=False):
        st = self.state()
        # Compare without 'since' churn: only publish when what HA shows would change.
        key = (st['present'], st['status'], st['common_name'], st['confidence'], st['count'], tuple(st['species']), st['camera'])
        if force or key != self._last:
            self._last = key
            self._publish(st)
