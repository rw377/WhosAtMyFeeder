"""Web UI: a JSON API plus the single-page app in static/app.

All URLs the page uses are relative, so it works both on its own port and
behind Home Assistant ingress (which serves it under a long path prefix).
"""
import csv
import io
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

import db
import frigate
import notifier
import queries

VERSION = '2.0.0'
APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'app')

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024  # database import

_config = None


def config():
    global _config
    if _config is None:
        _config = db.load_config()
    return _config


def frigate_url():
    return config()['frigate']['frigate_url']


def base_threshold(settings=None):
    settings = settings or db.get_settings()
    t = settings['detection'].get('threshold')
    return float(t) if t is not None else float(config()['classification']['threshold'])


def body():
    if request.method in ('POST', 'PUT', 'PATCH') and not request.is_json:
        abort(415)  # JSON only: keeps plain cross-site form posts out
    return request.get_json(silent=True) or {}


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(415)
def _err(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': getattr(e, 'description', str(e))}), e.code
    return e


@app.after_request
def _headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    if request.path.startswith('/api/'):
        resp.headers['Cache-Control'] = 'no-store'
    return resp


# ------------------------------------------------------------------ app shell

@app.route('/')
def index():
    return send_from_directory(APP_DIR, 'index.html')


@app.route('/assets/<path:name>')
def assets(name):
    return send_from_directory(APP_DIR, name, max_age=3600)


# ------------------------------------------------------------------ pictures and clips

PLACEHOLDER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 48"><rect width="64" height="48" fill="#22302A"/>'
               '<path fill="#3E5249" transform="translate(16 8) scale(.5)" d="M44 14c-5 0-9 4-9 9v2c-9-1-17 3-22 '
               '10l-7 2 6 3c4 8 12 12 21 12 13 0 22-9 22-21v-6l6-3-7-2c-2-4-6-6-10-6z"/></svg>')


def _picture(event_id, kind):
    if not frigate.valid_event(event_id):
        abort(404)
    cache = db.get_settings()['snapshots'].get('cache', True)
    path = frigate.get_snapshot(frigate_url(), event_id, kind, cache=cache)
    if not path:
        return Response(PLACEHOLDER, mimetype='image/svg+xml', headers={'Cache-Control': 'max-age=300'})
    return send_file(path, mimetype='image/jpeg', max_age=86400)


@app.route('/thumb/<event_id>.jpg')
def thumb(event_id):
    return _picture(event_id, 'crop')


@app.route('/snap/<event_id>.jpg')
def snap(event_id):
    return _picture(event_id, 'full')


@app.route('/clip/<event_id>.mp4')
def clip(event_id):
    r = frigate.clip_response(frigate_url(), event_id)
    if r is None:
        abort(404)
    return Response(r.iter_content(64 * 1024), mimetype=r.headers.get('Content-Type', 'video/mp4'))


# Old URLs from the original UI.
@app.route('/frigate/<event_id>/thumbnail.jpg')
def legacy_thumb(event_id):
    return thumb(event_id)


@app.route('/frigate/<event_id>/snapshot.jpg')
def legacy_snap(event_id):
    return snap(event_id)


@app.route('/frigate/<event_id>/clip.mp4')
def legacy_clip(event_id):
    return clip(event_id)


# ------------------------------------------------------------------ read API

@app.route('/api/status')
def api_status():
    conn = db.connect()
    try:
        rt = db.get_runtime(conn)
        cfg = config()
        f = cfg['frigate']
        cams = f.get('camera') or []
        return jsonify({
            'version': VERSION,
            'now': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'earliest_date': queries.earliest_date(conn),
            'mqtt': rt.get('mqtt', {'connected': False}),
            'broker': '%s:%s' % (f.get('mqtt_server'), notifier.mqtt_port(cfg)),
            'frigate_url': f.get('frigate_url'),
            'cameras': cams if isinstance(cams, list) else [cams],
            'threshold': base_threshold(),
            'config_threshold': float(cfg['classification']['threshold']),
            'cache': frigate.cache_usage(),
            'last_detection': rt.get('last_detection'),
        })
    finally:
        conn.close()


@app.route('/api/today')
def api_today():
    day = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    try:
        datetime.strptime(day, '%Y-%m-%d')
    except ValueError:
        abort(400, 'date must be YYYY-MM-DD')
    settings = db.get_settings()
    conn = db.connect()
    try:
        summary = queries.day_summary(conn, day)
        summary['weekday_average'] = queries.weekday_average(conn, day)
        rd = int(settings['alerts'].get('returning_days') or 30)
        summary['arrivals'] = queries.season_arrivals(conn, day, rd)
        summary['life_list_size'] = len(queries.species_first_seen(conn))
        now = datetime.now()
        summary['top_week'] = queries.top_species(
            conn, (now - timedelta(days=6)).strftime('%Y-%m-%d'), None, 6)
        summary['visits'] = queries.recent_visits(conn, int(request.args.get('limit', 12)),
                                                  int(settings['ui'].get('group_minutes') or 10), rd,
                                                  until=day + ' 23:59:59')
        return jsonify(summary)
    finally:
        conn.close()


@app.route('/api/detections')
def api_detections():
    a = request.args
    settings = db.get_settings()
    conn = db.connect()
    try:
        res = queries.history(
            conn, q=a.get('q', '').strip(), date_from=a.get('from') or None, date_to=a.get('to') or None,
            camera=a.get('camera') or None, min_score=a.get('min_score') or None,
            hide_flagged=a.get('hide_flagged') == '1', flagged_only=a.get('flagged') == '1',
            first_of_season=a.get('first_of_season') == '1',
            returning_days=int(settings['alerts'].get('returning_days') or 30),
            species=a.get('species') or None, sort=a.get('sort', 'newest'),
            page=a.get('page', 1), page_size=a.get('page_size', 25), hour=a.get('hour'))
        res['cameras'] = queries.cameras(conn)
        return jsonify(res)
    finally:
        conn.close()


@app.route('/api/detections.csv')
def api_detections_csv():
    a = request.args
    conn = db.connect()
    try:
        rows = queries.history(conn, q=a.get('q', '').strip(), date_from=a.get('from') or None,
                               date_to=a.get('to') or None, camera=a.get('camera') or None,
                               min_score=a.get('min_score') or None, hide_flagged=a.get('hide_flagged') == '1',
                               species=a.get('species') or None, sort='oldest', export=True)
    finally:
        conn.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['time', 'common_name', 'scientific_name', 'confidence', 'camera', 'frigate_event', 'needs_review'])
    for r in rows:
        w.writerow([r['time'], r['common_name'], r['scientific_name'], r['score'], r['camera'],
                    r['frigate_event'], 'yes' if r['flagged'] else ''])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="feeder-detections.csv"'})


@app.route('/api/species')
def api_species():
    conn = db.connect()
    try:
        return jsonify(queries.species_list(conn))
    finally:
        conn.close()


@app.route('/api/species/<path:sci>')
def api_species_detail(sci):
    conn = db.connect()
    try:
        return jsonify(queries.species_detail(conn, sci))
    finally:
        conn.close()


@app.route('/api/stats')
def api_stats():
    key = request.args.get('range', '30d')
    if key not in ('7d', '30d', 'season', 'year', 'all'):
        abort(400, 'unknown range')
    settings = db.get_settings()
    conn = db.connect()
    try:
        s = queries.stats(conn, key, returning_days=int(settings['alerts'].get('returning_days') or 30))
        s['life_list'] = queries.life_list(conn)
        return jsonify(s)
    finally:
        conn.close()


@app.route('/api/names')
def api_names():
    conn = db.connect()
    try:
        return jsonify(queries.name_search(conn, request.args.get('q', '')))
    finally:
        conn.close()


# ------------------------------------------------------------------ edits

def _bump_removed(conn, n=1):
    row = conn.execute("SELECT value FROM runtime WHERE key = 'removed_count'").fetchone()
    total = (int(row[0]) if row else 0) + n
    conn.execute("INSERT INTO runtime(key, value) VALUES ('removed_count', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(total),))


@app.route('/api/detections/<int:det_id>', methods=['PATCH'])
def api_detection_update(det_id):
    data = body()
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM detections WHERE id = ?", (det_id,)).fetchone()
        if not row:
            abort(404)
        if data.get('scientific_name'):
            sci = data['scientific_name'].strip()
            if not conn.execute("SELECT 1 FROM names.birdnames WHERE scientific_name = ?", (sci,)).fetchone():
                abort(400, 'unknown species')
            conn.execute("UPDATE detections SET display_name = ?, category_name = ?, reviewed = 1, flagged = 0 WHERE id = ?",
                         (sci, sci, det_id))
            frigate.set_sublabel(frigate_url(), row['frigate_event'], db.common_name(conn, sci))
        if data.get('reviewed'):
            conn.execute("UPDATE detections SET reviewed = 1 WHERE id = ?", (det_id,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/detections/<int:det_id>', methods=['DELETE'])
def api_detection_delete(det_id):
    conn = db.connect()
    try:
        row = conn.execute("SELECT frigate_event FROM detections WHERE id = ?", (det_id,)).fetchone()
        if not row:
            abort(404)
        conn.execute("DELETE FROM detections WHERE id = ?", (det_id,))
        _bump_removed(conn)
        conn.commit()
        frigate.delete_snapshots(row['frigate_event'])
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/species/<path:sci>/prefs', methods=['PUT'])
def api_species_prefs(sci):
    data = body()
    min_score = data.get('min_score')
    if min_score is not None:
        min_score = float(min_score)
        if not 0 < min_score <= 1:
            abort(400, 'min_score must be between 0 and 1')
    conn = db.connect()
    try:
        conn.execute("""INSERT INTO species_prefs(scientific_name, min_score, hidden) VALUES (?, ?, ?)
                        ON CONFLICT(scientific_name) DO UPDATE SET min_score = excluded.min_score, hidden = excluded.hidden""",
                     (sci, min_score, 1 if data.get('hidden') else 0))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


# ------------------------------------------------------------------ settings & alerts

def _clean_settings(patch):
    """Coerce types so bad input can't break the detector."""
    out = {}
    for section, values in (patch or {}).items():
        if section not in db.SETTINGS_DEFAULTS or not isinstance(values, dict):
            continue
        out[section] = {}
        for k, v in values.items():
            default = db.SETTINGS_DEFAULTS[section].get(k, '__missing__')
            if default == '__missing__':
                continue
            if isinstance(default, bool):
                v = bool(v)
            elif isinstance(default, int) and not isinstance(default, bool):
                v = max(0, int(v))
            elif k in ('min_score', 'threshold', 'review_below'):
                v = None if v in (None, '') else min(1.0, max(0.0, float(v)))
            elif isinstance(default, str):
                v = str(v)[:200]
                if k in ('start', 'end'):
                    datetime.strptime(v, '%H:%M')
                if k == 'topic_prefix':
                    v = v.strip().strip('/') or 'whosatmyfeeder'
                    if any(c in v for c in '#+'):
                        abort(400, 'topic prefix cannot contain # or +')
            out[section][k] = v
    return out


@app.route('/api/settings', methods=['GET', 'PUT'])
def api_settings():
    if request.method == 'PUT':
        try:
            patch = _clean_settings(body())
        except (TypeError, ValueError):
            abort(400, 'invalid setting value')
        return jsonify(db.update_settings(patch))
    return jsonify(db.get_settings())


@app.route('/api/watchlist', methods=['GET', 'POST'])
def api_watchlist():
    conn = db.connect()
    try:
        if request.method == 'POST':
            data = body()
            sci = (data.get('scientific_name') or '').strip()
            if not conn.execute("SELECT 1 FROM names.birdnames WHERE scientific_name = ?", (sci,)).fetchone():
                abort(400, 'unknown species')
            conn.execute("""INSERT INTO watchlist(scientific_name, min_score, cooldown_min, enabled, note)
                            VALUES (?, ?, ?, 1, ?)
                            ON CONFLICT(scientific_name) DO UPDATE SET min_score = excluded.min_score,
                                cooldown_min = excluded.cooldown_min, enabled = 1""",
                         (sci, float(data.get('min_score', 0.8)), int(data.get('cooldown_min', 15)),
                          str(data.get('note', ''))[:120]))
            conn.commit()
        rows = conn.execute("""
            SELECT w.*, COALESCE(n.common_name, w.scientific_name) AS common_name,
                   (SELECT MAX(sent_at) FROM alert_log a WHERE a.scientific_name = w.scientific_name) AS last_alert,
                   (SELECT COUNT(*) FROM detections d WHERE d.display_name = w.scientific_name) AS seen
            FROM watchlist w LEFT JOIN names.birdnames n ON n.scientific_name = w.scientific_name
            ORDER BY w.created_at DESC""").fetchall()
        return jsonify([{
            'scientific_name': r['scientific_name'], 'common_name': r['common_name'],
            'min_score': r['min_score'], 'cooldown_min': r['cooldown_min'], 'enabled': bool(r['enabled']),
            'note': r['note'], 'seen': r['seen'],
            'last_alert': r['last_alert'].replace(' ', 'T') if r['last_alert'] else None} for r in rows])
    finally:
        conn.close()


@app.route('/api/watchlist/<path:sci>', methods=['PUT', 'DELETE'])
def api_watch_item(sci):
    conn = db.connect()
    try:
        if request.method == 'DELETE':
            conn.execute("DELETE FROM watchlist WHERE scientific_name = ?", (sci,))
        else:
            data = body()
            row = conn.execute("SELECT * FROM watchlist WHERE scientific_name = ?", (sci,)).fetchone()
            if not row:
                abort(404)
            conn.execute("UPDATE watchlist SET min_score = ?, cooldown_min = ?, enabled = ?, note = ? WHERE scientific_name = ?",
                         (float(data.get('min_score', row['min_score'])), int(data.get('cooldown_min', row['cooldown_min'])),
                          1 if data.get('enabled', bool(row['enabled'])) else 0, str(data.get('note', row['note']))[:120], sci))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/alerts/recent')
def api_alerts_recent():
    conn = db.connect()
    try:
        rows = conn.execute("""SELECT a.*, COALESCE(n.common_name, a.scientific_name) AS common_name FROM alert_log a
                               LEFT JOIN names.birdnames n ON n.scientific_name = a.scientific_name
                               ORDER BY a.sent_at DESC LIMIT 20""").fetchall()
        return jsonify([{'common_name': r['common_name'], 'reason': r['reason'],
                         'sent_at': r['sent_at'].replace(' ', 'T')} for r in rows])
    finally:
        conn.close()


@app.route('/api/mqtt/test', methods=['POST'])
def api_mqtt_test():
    body()
    ok, msg = notifier.send_test(config(), db.get_settings())
    return jsonify({'ok': ok, 'message': msg}), (200 if ok else 502)


# ------------------------------------------------------------------ import from another install

@app.route('/api/import', methods=['POST'])
def api_import():
    if request.headers.get('X-Requested-With') != 'wamf':
        abort(415)
    f = request.files.get('file')
    if not f:
        abort(400, 'no file uploaded')
    fd, tmp = tempfile.mkstemp(suffix='.db', dir=db.DATA_DIR)
    os.close(fd)
    try:
        f.save(tmp)
        try:
            src = sqlite3.connect('file:%s?mode=ro' % tmp, uri=True)
            src.execute("SELECT detection_time, detection_index, score, display_name, category_name, "
                        "frigate_event, camera_name FROM detections LIMIT 1")
            src.close()
        except sqlite3.DatabaseError:
            abort(400, 'that file is not a WhosAtMyFeeder database')
        conn = db.connect()
        try:
            before = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
            conn.execute("ATTACH DATABASE ? AS src", (tmp,))
            conn.execute("""INSERT OR IGNORE INTO detections
                            (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name)
                            SELECT detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name
                            FROM src.detections""")
            conn.commit()
            conn.execute("DETACH DATABASE src")
            after = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        finally:
            conn.close()
        return jsonify({'ok': True, 'imported': after - before})
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.route('/api/export.db')
def api_export_db():
    """Consistent copy of the database, for backups or moving installs."""
    fd, tmp = tempfile.mkstemp(suffix='.db', dir=db.DATA_DIR)
    os.close(fd)
    src = sqlite3.connect(db.DBPATH)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    src.close()
    dst.close()
    data = open(tmp, 'rb').read()
    os.remove(tmp)
    return Response(data, mimetype='application/octet-stream',
                    headers={'Content-Disposition': 'attachment; filename="speciesid.db"'})
