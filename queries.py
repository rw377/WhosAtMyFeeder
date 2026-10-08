"""Read queries for the web UI. Every function takes an open connection from db.connect()."""
from datetime import datetime, timedelta, date

from db import COMMON, NAMES_JOIN

VISIBLE = "d.display_name NOT IN (SELECT scientific_name FROM species_prefs WHERE hidden = 1)"
TIME = "substr(d.detection_time, 1, 19)"

DET_COLUMNS = ("d.id, %s AS t, d.score, d.display_name, %s AS common_name, d.frigate_event, "
               "d.camera_name, d.flagged, d.reviewed" % (TIME, COMMON))


def det_dict(row):
    return {
        'id': row['id'],
        'time': row['t'].replace(' ', 'T'),
        'score': round(row['score'], 4),
        'scientific_name': row['display_name'],
        'common_name': row['common_name'],
        'frigate_event': row['frigate_event'],
        'camera': row['camera_name'],
        'flagged': bool(row['flagged']) and not bool(row['reviewed']),
    }


def _parse(ts):
    return datetime.strptime(ts[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')


def earliest_date(conn):
    row = conn.execute("SELECT MIN(date(detection_time)) FROM detections").fetchone()
    return row[0]


# ------------------------------------------------------------------ today / day

def day_summary(conn, day):
    """Per-species hourly counts for one day (YYYY-MM-DD), sorted by daily total."""
    rows = conn.execute("""
        SELECT d.display_name, %s AS common_name,
               CAST(strftime('%%H', d.detection_time) AS INTEGER) AS hour, COUNT(*) AS n
        FROM detections d %s
        WHERE date(d.detection_time) = ? AND %s
        GROUP BY d.display_name, hour
    """ % (COMMON, NAMES_JOIN, VISIBLE), (day,)).fetchall()
    species = {}
    per_hour = [0] * 24
    for r in rows:
        s = species.setdefault(r['display_name'], {
            'scientific_name': r['display_name'], 'common_name': r['common_name'],
            'total': 0, 'hours': [0] * 24})
        s['hours'][r['hour']] = r['n']
        s['total'] += r['n']
        per_hour[r['hour']] += r['n']
    ordered = sorted(species.values(), key=lambda s: (-s['total'], s['common_name']))
    first = conn.execute("""
        SELECT %s AS t, %s AS common_name FROM detections d %s
        WHERE date(d.detection_time) = ? AND %s ORDER BY d.detection_time LIMIT 1
    """ % (TIME, COMMON, NAMES_JOIN, VISIBLE), (day,)).fetchone()
    total = sum(per_hour)
    peak_hour = max(range(24), key=lambda h: per_hour[h]) if total else None
    return {
        'date': day,
        'total': total,
        'species_count': len(ordered),
        'first': {'time': first['t'].replace(' ', 'T'), 'common_name': first['common_name']} if first else None,
        'peak_hour': peak_hour,
        'peak_count': per_hour[peak_hour] if peak_hour is not None else 0,
        'per_hour': per_hour,
        'species': ordered,
    }


def weekday_average(conn, day, weeks=8):
    """Average visit count on the same weekday over the previous N weeks that had any data."""
    d = datetime.strptime(day, '%Y-%m-%d').date()
    days = [(d - timedelta(weeks=i)).isoformat() for i in range(1, weeks + 1)]
    q = "SELECT date(detection_time) AS dd, COUNT(*) AS n FROM detections d WHERE date(detection_time) IN (%s) AND %s GROUP BY dd" % (
        ','.join('?' * len(days)), VISIBLE)
    counts = [r['n'] for r in conn.execute(q, days)]
    return round(sum(counts) / len(counts)) if counts else None


def species_first_seen(conn):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT display_name, MIN(%s) FROM detections d GROUP BY display_name" % TIME)}


def recent_visits(conn, limit=8, group_minutes=10, returning_days=30, until=None):
    """Latest detections grouped into visits: same species, gaps <= group_minutes."""
    rows = conn.execute("""
        SELECT %s FROM detections d %s WHERE %s AND d.detection_time <= ?
        ORDER BY d.detection_time DESC LIMIT ?
    """ % (DET_COLUMNS, NAMES_JOIN, VISIBLE), (until or '9999-12-31', limit * 6)).fetchall()
    groups = []
    for r in rows:
        det = det_dict(r)
        g = groups[-1] if groups else None
        if (g and g['scientific_name'] == det['scientific_name'] and
                (_parse(g['_earliest']) - _parse(det['time'])) <= timedelta(minutes=group_minutes)):
            g['detections'].append(det)
            g['_earliest'] = det['time']
            g['flagged'] = g['flagged'] or det['flagged']
            if det['score'] > g['best']['score']:
                g['best'] = det
            continue
        if len(groups) == limit:
            break
        groups.append({'scientific_name': det['scientific_name'], 'common_name': det['common_name'],
                       'latest': det, 'best': det, 'detections': [det], '_earliest': det['time'],
                       'flagged': det['flagged']})
    first_seen = species_first_seen(conn)
    for g in groups:
        g['count'] = len(g['detections'])
        g['span_minutes'] = int((_parse(g['latest']['time']) - _parse(g['_earliest'])).total_seconds() // 60)
        earliest = g.pop('_earliest')
        prev = conn.execute("""
            SELECT MAX(%s) FROM detections d WHERE d.display_name = ? AND d.detection_time < ?
        """ % TIME, (g['scientific_name'], earliest.replace('T', ' '))).fetchone()[0]
        g['first_ever'] = first_seen.get(g['scientific_name'], '')[:19].replace(' ', 'T') == earliest
        g['first_of_season'] = bool(prev) and (_parse(earliest) - _parse(prev)).days >= returning_days
        g['new_this_season'] = g['first_ever'] or g['first_of_season']
        g['detections'] = g['detections'][:12]
    return groups


def season_arrivals(conn, since, returning_days=30):
    """Species whose first sighting, or return after a long absence, happened since `since`."""
    rows = conn.execute("""
        WITH x AS (
            SELECT d.display_name, %s AS t,
                   LAG(%s) OVER (PARTITION BY d.display_name ORDER BY d.detection_time) AS prev
            FROM detections d WHERE %s
        )
        SELECT x.display_name, %s AS common_name, MIN(x.t) AS t
        FROM x LEFT JOIN names.birdnames n ON n.scientific_name = x.display_name
        WHERE x.t >= ? AND (x.prev IS NULL OR julianday(x.t) - julianday(x.prev) >= ?)
        GROUP BY x.display_name ORDER BY t DESC
    """ % (TIME, TIME, VISIBLE, "COALESCE(n.common_name, x.display_name)"), (since, returning_days)).fetchall()
    return [{'scientific_name': r['display_name'], 'common_name': r['common_name'],
             'time': r['t'].replace(' ', 'T')} for r in rows]


def top_species(conn, start=None, end=None, limit=8):
    where, args = [VISIBLE], []
    if start:
        where.append("d.detection_time >= ?"); args.append(start)
    if end:
        where.append("d.detection_time < ?"); args.append(end)
    rows = conn.execute("""
        SELECT d.display_name, %s AS common_name, COUNT(*) AS n FROM detections d %s
        WHERE %s GROUP BY d.display_name ORDER BY n DESC LIMIT ?
    """ % (COMMON, NAMES_JOIN, ' AND '.join(where)), args + [limit]).fetchall()
    return [{'scientific_name': r['display_name'], 'common_name': r['common_name'], 'count': r['n']} for r in rows]


# ------------------------------------------------------------------ history

def history(conn, q='', date_from=None, date_to=None, camera=None, min_score=None,
            hide_flagged=False, flagged_only=False, first_of_season=False, returning_days=30,
            species=None, sort='newest', page=1, page_size=25, export=False, hour=None):
    where, args = [VISIBLE], []
    if hour is not None and str(hour) != '':
        where.append("CAST(strftime('%H', d.detection_time) AS INTEGER) = ?"); args.append(int(hour))
    if q:
        where.append("(%s LIKE ? OR d.display_name LIKE ?)" % COMMON)
        args += ['%' + q + '%', '%' + q + '%']
    if species:
        where.append("d.display_name = ?"); args.append(species)
    if date_from:
        where.append("date(d.detection_time) >= ?"); args.append(date_from)
    if date_to:
        where.append("date(d.detection_time) <= ?"); args.append(date_to)
    if camera:
        where.append("d.camera_name = ?"); args.append(camera)
    if min_score:
        where.append("d.score >= ?"); args.append(float(min_score))
    if hide_flagged:
        where.append("NOT (d.flagged = 1 AND d.reviewed = 0)")
    if flagged_only:
        where.append("d.flagged = 1 AND d.reviewed = 0")
    source = "detections d"
    if first_of_season:
        source = """(SELECT *, LAG(detection_time) OVER (PARTITION BY display_name ORDER BY detection_time) AS prev_t
                     FROM detections) d"""
        where.append("(d.prev_t IS NULL OR julianday(d.detection_time) - julianday(d.prev_t) >= ?)")
        args.append(returning_days)
    where_sql = ' AND '.join(where)
    order = {'newest': 'd.detection_time DESC', 'oldest': 'd.detection_time ASC',
             'confidence': 'd.score DESC, d.detection_time DESC'}.get(sort, 'd.detection_time DESC')
    agg = conn.execute("""
        SELECT COUNT(*) AS n, COUNT(DISTINCT d.display_name) AS sp, COUNT(DISTINCT date(d.detection_time)) AS days
        FROM %s %s WHERE %s
    """ % (source, NAMES_JOIN, where_sql), args).fetchone()
    sql = "SELECT %s FROM %s %s WHERE %s ORDER BY %s" % (DET_COLUMNS, source, NAMES_JOIN, where_sql, order)
    if export:
        return [det_dict(r) for r in conn.execute(sql, args)]
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    rows = conn.execute(sql + " LIMIT ? OFFSET ?", args + [page_size, (page - 1) * page_size]).fetchall()
    return {'total': agg['n'], 'species': agg['sp'], 'days': agg['days'], 'page': page,
            'page_size': page_size, 'results': [det_dict(r) for r in rows]}


def cameras(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT camera_name FROM detections ORDER BY 1")]


# ------------------------------------------------------------------ species

def species_list(conn):
    rows = conn.execute("""
        SELECT d.display_name, %s AS common_name, COUNT(*) AS n, MIN(%s) AS first, MAX(%s) AS last,
               AVG(d.score) AS avg_score, COALESCE(p.hidden, 0) AS hidden,
               (SELECT x.frigate_event FROM detections x WHERE x.display_name = d.display_name
                ORDER BY x.score DESC LIMIT 1) AS best_event
        FROM detections d %s LEFT JOIN species_prefs p ON p.scientific_name = d.display_name
        GROUP BY d.display_name ORDER BY n DESC
    """ % (COMMON, TIME, TIME, NAMES_JOIN)).fetchall()
    return [{'scientific_name': r['display_name'], 'common_name': r['common_name'], 'visits': r['n'],
             'first': r['first'].replace(' ', 'T'), 'last': r['last'].replace(' ', 'T'),
             'avg_score': round(r['avg_score'], 3), 'hidden': bool(r['hidden']),
             'best_event': r['best_event']} for r in rows]


def species_detail(conn, sci, now=None):
    now = now or datetime.now()
    base = conn.execute("""
        SELECT COUNT(*) AS n, MIN(%s) AS first, MAX(%s) AS last, AVG(d.score) AS avg_score,
               COUNT(DISTINCT date(d.detection_time)) AS days
        FROM detections d WHERE d.display_name = ?
    """ % (TIME, TIME), (sci,)).fetchone()
    name_row = conn.execute("SELECT common_name FROM names.birdnames WHERE scientific_name = ?", (sci,)).fetchone()
    prefs = conn.execute("SELECT min_score, hidden FROM species_prefs WHERE scientific_name = ?", (sci,)).fetchone()
    watch = conn.execute("SELECT * FROM watchlist WHERE scientific_name = ?", (sci,)).fetchone()
    out = {
        'scientific_name': sci,
        'common_name': name_row[0] if name_row and name_row[0] else sci,
        'visits': base['n'],
        'days_seen': base['days'],
        'first': base['first'].replace(' ', 'T') if base['first'] else None,
        'last': base['last'].replace(' ', 'T') if base['last'] else None,
        'avg_score': round(base['avg_score'], 3) if base['avg_score'] else None,
        'prefs': {'min_score': prefs['min_score'] if prefs else None, 'hidden': bool(prefs['hidden']) if prefs else False},
        'watching': bool(watch),
    }
    if not base['n']:
        out.update({'hours': [0] * 24, 'calendar': [], 'companions': [], 'photos': [], 'best': None,
                    'rank': None, 'peak_hour': None})
        return out
    since90 = (now - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    hours = [0] * 24
    for r in conn.execute("""SELECT CAST(strftime('%H', detection_time) AS INTEGER) h, COUNT(*) n FROM detections
                             WHERE display_name = ? AND detection_time >= ? GROUP BY h""", (sci, since90)):
        hours[r['h']] = r['n']
    out['hours'] = hours
    out['peak_hour'] = max(range(24), key=lambda h: hours[h]) if sum(hours) else None
    start = (now.date() - timedelta(days=7 * 26 + now.weekday() + 1))
    counts = {r[0]: r[1] for r in conn.execute("""
        SELECT date(detection_time), COUNT(*) FROM detections WHERE display_name = ? AND date(detection_time) >= ?
        GROUP BY 1""", (sci, start.isoformat()))}
    cal = []
    d = start
    while d <= now.date():
        cal.append({'date': d.isoformat(), 'n': counts.get(d.isoformat(), 0)})
        d += timedelta(days=1)
    out['calendar'] = cal
    best = conn.execute("SELECT %s FROM detections d %s WHERE d.display_name = ? ORDER BY d.score DESC LIMIT 1"
                        % (DET_COLUMNS, NAMES_JOIN), (sci,)).fetchone()
    out['best'] = det_dict(best)
    out['photos'] = [det_dict(r) for r in conn.execute(
        "SELECT %s FROM detections d %s WHERE d.display_name = ? ORDER BY d.detection_time DESC LIMIT 12"
        % (DET_COLUMNS, NAMES_JOIN), (sci,))]
    # Other species at the feeder within 10 minutes of this one (last 90 days).
    comp = conn.execute("""
        WITH mine AS (SELECT detection_time t FROM detections WHERE display_name = ? AND detection_time >= ?)
        SELECT d.display_name, %s AS common_name, COUNT(DISTINCT mine.t) AS overlap
        FROM mine JOIN detections d
          ON d.display_name != ? AND ABS(julianday(d.detection_time) - julianday(mine.t)) <= 10.0 / 1440
        %s WHERE %s
        GROUP BY d.display_name ORDER BY overlap DESC LIMIT 5
    """ % (COMMON, NAMES_JOIN, VISIBLE), (sci, since90, sci)).fetchall()
    n90 = sum(hours) or 1
    out['companions'] = [{'scientific_name': r['display_name'], 'common_name': r['common_name'],
                          'pct': round(100 * r['overlap'] / n90)} for r in comp]
    rank_rows = conn.execute("SELECT display_name FROM detections d WHERE %s GROUP BY display_name ORDER BY COUNT(*) DESC"
                             % VISIBLE).fetchall()
    names = [r[0] for r in rank_rows]
    out['rank'] = names.index(sci) + 1 if sci in names else None
    return out


def name_search(conn, q, limit=8):
    q = (q or '').strip()
    if len(q) < 2:
        return []
    rows = conn.execute("""
        SELECT n.scientific_name, n.common_name, COALESCE(c.n, 0) AS seen
        FROM names.birdnames n
        LEFT JOIN (SELECT display_name, COUNT(*) n FROM detections GROUP BY display_name) c
               ON c.display_name = n.scientific_name
        WHERE n.common_name LIKE ? OR n.scientific_name LIKE ?
        ORDER BY seen DESC, (n.common_name LIKE ?) DESC, n.common_name LIMIT ?
    """, ('%' + q + '%', '%' + q + '%', q + '%', limit)).fetchall()
    return [{'scientific_name': r[0], 'common_name': r[1] or r[0], 'seen': r[2]} for r in rows]


# ------------------------------------------------------------------ stats

def range_start(key, now):
    today = now.date()
    if key == '7d':
        return today - timedelta(days=6)
    if key == '30d':
        return today - timedelta(days=29)
    if key == 'season':
        m = ((today.month % 12) // 3) * 3  # 0=Dec-Feb, 3=Mar-May, 6=Jun-Aug, 9=Sep-Nov
        if m == 0:
            return date(today.year if today.month == 12 else today.year - 1, 12, 1)
        return date(today.year, m, 1)
    if key == 'year':
        return date(today.year, 1, 1)
    return None


SEASON_NAMES = {12: 'Winter', 3: 'Spring', 6: 'Summer', 9: 'Fall'}


def stats(conn, key='30d', now=None, returning_days=30):
    now = now or datetime.now()
    first_day = earliest_date(conn)
    start = range_start(key, now)
    if first_day:
        fd = datetime.strptime(first_day, '%Y-%m-%d').date()
        if start is None or start < fd:
            start = fd
    start = start or now.date()
    start_s = start.isoformat()
    where = "%s AND date(d.detection_time) >= ?" % VISIBLE
    agg = conn.execute("SELECT COUNT(*) n, COUNT(DISTINCT display_name) sp FROM detections d WHERE " + where,
                       (start_s,)).fetchone()
    days = (now.date() - start).days + 1
    busiest = conn.execute("""SELECT date(detection_time) dd, COUNT(*) n FROM detections d WHERE %s
                              GROUP BY dd ORDER BY n DESC LIMIT 1""" % where, (start_s,)).fetchone()
    first_seen = species_first_seen(conn)
    new_species = [s for s, t in first_seen.items() if t[:10] >= start_s]
    hours = [0] * 24
    for r in conn.execute("""SELECT CAST(strftime('%%H', detection_time) AS INTEGER) h, COUNT(*) n
                             FROM detections d WHERE %s GROUP BY h""" % where, (start_s,)):
        hours[r['h']] = r['n']
    # Daily series (weekly when the range is long).
    daily = {r[0]: r[1] for r in conn.execute(
        "SELECT date(detection_time), COUNT(*) FROM detections d WHERE %s GROUP BY 1" % where, (start_s,))}
    series = []
    if days <= 92:
        for i in range(days):
            dd = (start + timedelta(days=i)).isoformat()
            series.append({'label': dd, 'n': daily.get(dd, 0)})
        bucket = 'day'
    else:
        wk = start - timedelta(days=start.weekday())
        while wk <= now.date():
            n = sum(daily.get((wk + timedelta(days=i)).isoformat(), 0) for i in range(7))
            series.append({'label': wk.isoformat(), 'n': n})
            wk += timedelta(days=7)
        bucket = 'week'
    # Species per week, last 26 weeks.
    wk0 = now.date() - timedelta(days=now.weekday()) - timedelta(weeks=25)
    weekly = {r[0]: r[1] for r in conn.execute("""
        SELECT date(detection_time, '-' || ((CAST(strftime('%%w', detection_time) AS INTEGER) + 6) %% 7) || ' days') wk,
               COUNT(DISTINCT display_name) FROM detections d WHERE %s GROUP BY wk""" % where, (wk0.isoformat(),))}
    species_weeks = [{'week': (wk0 + timedelta(weeks=i)).isoformat(),
                      'n': weekly.get((wk0 + timedelta(weeks=i)).isoformat(), 0)} for i in range(26)]
    pending = conn.execute("SELECT COUNT(*) FROM detections d WHERE flagged = 1 AND reviewed = 0 AND %s" % VISIBLE).fetchone()[0]
    pending_by = [{'scientific_name': r[0], 'common_name': r[1], 'n': r[2]} for r in conn.execute("""
        SELECT d.display_name, %s, COUNT(*) FROM detections d %s WHERE d.flagged = 1 AND d.reviewed = 0 AND %s
        GROUP BY d.display_name ORDER BY 3 DESC LIMIT 5""" % (COMMON, NAMES_JOIN, VISIBLE))]
    runtime_removed = conn.execute("SELECT value FROM runtime WHERE key = 'removed_count'").fetchone()
    label = {'7d': 'Last 7 days', '30d': 'Last 30 days', 'year': str(now.year), 'all': 'All time'}.get(key)
    if key == 'season':
        label = '%s %d' % (SEASON_NAMES[start.month] if start.month in SEASON_NAMES else 'Season', start.year)
    return {
        'range': key, 'label': label, 'start': start_s, 'days': days,
        'visits': agg['n'], 'species': agg['sp'], 'per_day': round(agg['n'] / days, 1) if days else 0,
        'life_list_size': len(first_seen),
        'new_species': [{'scientific_name': s, 'first': first_seen[s][:19].replace(' ', 'T')} for s in new_species],
        'busiest_day': {'date': busiest['dd'], 'n': busiest['n']} if busiest else None,
        'top': top_species(conn, start_s, None, 10),
        'series': series, 'bucket': bucket,
        'hours': hours,
        'species_weeks': species_weeks,
        'arrivals': season_arrivals(conn, start_s, returning_days),
        'flagged_pending': pending,
        'flagged_by_species': pending_by,
        'removed_total': int(runtime_removed[0]) if runtime_removed else 0,
    }


def life_list(conn):
    return species_list(conn)
