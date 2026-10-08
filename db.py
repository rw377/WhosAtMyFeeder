"""Database access shared by the detector and the web UI.

Both processes open their own short-lived connections. WAL mode lets the web
UI read while the detector writes.
"""
import json
import os
import sqlite3
import threading

DATA_DIR = os.environ.get('WAMF_DATA_DIR', './data')
DBPATH = os.path.join(DATA_DIR, 'speciesid.db')
NAMEDBPATH = os.environ.get('WAMF_NAMES_DB', './birdnames.db')
CONFIG_PATH = os.environ.get('WAMF_CONFIG', './config/config.yml')

# Joined name expression used throughout queries.
COMMON = "COALESCE(n.common_name, d.display_name)"
NAMES_JOIN = "LEFT JOIN names.birdnames n ON n.scientific_name = d.display_name"

SETTINGS_DEFAULTS = {
    'mqtt': {
        'topic_prefix': 'whosatmyfeeder',
        'discovery': True,
        'legacy_topic': True,  # plain common name to whosatmyfeeder/detections (original behaviour)
    },
    'publish_all': {
        'enabled': False,
        'min_score': None,     # None = use detection threshold
        'skip_flagged': True,
    },
    'alerts': {
        'enabled': True,
        'new_species': True,
        'returning': True,
        'returning_days': 30,
    },
    'quiet': {
        'enabled': False,
        'start': '21:00',
        'end': '06:30',
        'allow_new_species': True,
    },
    'detection': {
        'threshold': None,         # None = use config.yml classification.threshold
        'review_below': 0.80,      # flag detections under this score for review
        'flag_first_sighting': True,
    },
    'snapshots': {
        'cache': True,
        'base_url': '',            # external URL used in MQTT payload snapshot links
    },
    'ui': {
        'group_minutes': 10,
    },
}

_local = threading.local()


def connect():
    conn = sqlite3.connect(DBPATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ATTACH DATABASE ? AS names", (NAMEDBPATH,))
    return conn


def load_config():
    import yaml
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def _column_names(conn, table):
    return {r[1] for r in conn.execute("PRAGMA main.table_info(%s)" % table)}


def migrate():
    """Create or upgrade the schema. Safe to run on every start."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DBPATH, timeout=15)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detection_time TIMESTAMP NOT NULL,
                detection_index INTEGER NOT NULL,
                score REAL NOT NULL,
                display_name TEXT NOT NULL,
                category_name TEXT NOT NULL,
                frigate_event TEXT NOT NULL UNIQUE,
                camera_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                scientific_name TEXT PRIMARY KEY,
                min_score REAL NOT NULL DEFAULT 0.8,
                cooldown_min INTEGER NOT NULL DEFAULT 15,
                enabled INTEGER NOT NULL DEFAULT 1,
                note TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scientific_name TEXT NOT NULL,
                frigate_event TEXT,
                reason TEXT NOT NULL,
                sent_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS species_prefs (
                scientific_name TEXT PRIMARY KEY,
                min_score REAL,
                hidden INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS runtime (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        cols = _column_names(conn, 'detections')
        if 'flagged' not in cols:
            conn.execute("ALTER TABLE detections ADD COLUMN flagged INTEGER NOT NULL DEFAULT 0")
        if 'reviewed' not in cols:
            conn.execute("ALTER TABLE detections ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0")
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_det_time ON detections(detection_time);
            CREATE INDEX IF NOT EXISTS idx_det_name_time ON detections(display_name, detection_time);
            CREATE INDEX IF NOT EXISTS idx_alert_name_time ON alert_log(scientific_name, sent_at);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- settings

def _merge(defaults, stored):
    out = {}
    for k, v in defaults.items():
        if isinstance(v, dict):
            out[k] = _merge(v, stored.get(k, {}) if isinstance(stored.get(k), dict) else {})
        else:
            out[k] = stored.get(k, v) if k in stored else v
    return out


def get_settings(conn=None):
    own = conn is None
    conn = conn or connect()
    try:
        stored = {}
        for row in conn.execute("SELECT key, value FROM settings"):
            try:
                stored[row['key']] = json.loads(row['value'])
            except ValueError:
                pass
        return _merge(SETTINGS_DEFAULTS, stored)
    finally:
        if own:
            conn.close()


def update_settings(patch):
    """Merge a partial settings dict (only known sections/keys are kept)."""
    conn = connect()
    try:
        current = get_settings(conn)
        for section, values in (patch or {}).items():
            if section not in SETTINGS_DEFAULTS or not isinstance(values, dict):
                continue
            for k, v in values.items():
                if k in SETTINGS_DEFAULTS[section]:
                    current[section][k] = v
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (section, json.dumps(current[section])))
        conn.commit()
        return current
    finally:
        conn.close()


# ---------------------------------------------------------------- runtime state

def set_runtime(key, value):
    conn = connect()
    try:
        conn.execute("INSERT INTO runtime(key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, json.dumps(value)))
        conn.commit()
    finally:
        conn.close()


def get_runtime(conn=None):
    own = conn is None
    conn = conn or connect()
    try:
        return {r['key']: json.loads(r['value']) for r in conn.execute("SELECT key, value FROM runtime")}
    finally:
        if own:
            conn.close()


def common_name(conn, scientific_name):
    row = conn.execute("SELECT common_name FROM names.birdnames WHERE scientific_name = ?",
                       (scientific_name,)).fetchone()
    return row[0] if row and row[0] else scientific_name
