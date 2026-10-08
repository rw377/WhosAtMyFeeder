/* Who's At My Feeder — single-page UI. No build step; plain modern JS.
 * Every URL is relative so the app works behind Home Assistant ingress. */
(function () {
  'use strict';

  var main = document.getElementById('main');
  var BIRD = '<svg viewBox="0 0 64 64" aria-hidden="true" width="%S" height="%S"><path fill="currentColor" d="M44 14c-5 0-9 4-9 9v2c-9-1-17 3-22 10l-7 2 6 3c4 8 12 12 21 12 13 0 22-9 22-21v-6l6-3-7-2c-2-4-6-6-10-6z"/></svg>';
  var ICON = {
    play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z"/></svg>',
    edit: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>',
    trash: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
    left: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>',
    right: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>',
    down: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/></svg>',
    bell: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4"/></svg>',
    send: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/></svg>',
    x: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>'
  };
  function bird(size) { return BIRD.replace(/%S/g, size); }

  /* ------------------------------------------------------------------ helpers */

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function enc(s) { return encodeURIComponent(s); }
  function qs(obj) {
    var p = [];
    Object.keys(obj).forEach(function (k) {
      var v = obj[k];
      if (v !== undefined && v !== null && v !== '' && v !== false) p.push(enc(k) + '=' + enc(v === true ? '1' : v));
    });
    return p.length ? '?' + p.join('&') : '';
  }
  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    return fetch('api/' + path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) {
          var e = new Error((data && (data.error || data.message)) || ('Request failed (' + r.status + ')'));
          e.data = data;
          throw e;
        }
        return data;
      });
    });
  }
  function toast(msg) {
    var box = document.getElementById('toast');
    var d = document.createElement('div');
    d.textContent = msg;
    box.appendChild(d);
    setTimeout(function () { d.remove(); }, 3200);
  }
  function fail(e) { toast(e && e.message ? e.message : 'Something went wrong'); }

  var skew = 0;
  function nowServer() { return new Date(Date.now() + skew); }
  function parse(iso) { return iso ? new Date(iso.replace(' ', 'T')) : null; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function ymd(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function todayStr() { return ymd(nowServer()); }
  function addDays(s, n) { var d = new Date(s + 'T12:00:00'); d.setDate(d.getDate() + n); return ymd(d); }
  function fmtTime(iso) {
    var d = parse(iso); if (!d) return '';
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  function hourLabel(h) { return (h % 12 === 0 ? 12 : h % 12) + (h < 12 ? ' AM' : ' PM'); }
  function fmtDay(s, opts) {
    return new Date(s.slice(0, 10) + 'T12:00:00').toLocaleDateString([], opts || { weekday: 'long', month: 'long', day: 'numeric' });
  }
  function fmtShort(iso) {
    var d = parse(iso); if (!d) return '—';
    var t = todayStr();
    var day = ymd(d);
    if (day === t) return 'Today, ' + fmtTime(iso);
    if (day === addDays(t, -1)) return 'Yesterday, ' + fmtTime(iso);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === nowServer().getFullYear() ? undefined : 'numeric' });
  }
  function ago(iso) {
    var d = parse(iso); if (!d) return '';
    var m = Math.round((nowServer() - d) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + ' min ago';
    var h = Math.round(m / 60);
    if (h < 24) return h + ' hr ago';
    var dd = Math.round(h / 24);
    return dd === 1 ? 'yesterday' : dd + ' days ago';
  }
  function pct(score) { return Math.round(score * 100) + '%'; }
  function tier(score) { return score >= 0.9 ? 'hi' : score >= 0.8 ? 'mid' : 'lo'; }
  function confPill(score) { return '<span class="pill ' + tier(score) + '">' + pct(score) + '</span>'; }
  function num(n) { return (n || 0).toLocaleString(); }
  function thumbUrl(ev) { return 'thumb/' + enc(ev) + '.jpg'; }
  function snapUrl(ev) { return 'snap/' + enc(ev) + '.jpg'; }
  function clipUrl(ev) { return 'clip/' + enc(ev) + '.mp4'; }
  function img(ev, kind, alt) {
    return '<img loading="lazy" src="' + (kind === 'full' ? snapUrl(ev) : thumbUrl(ev)) + '" alt="' + esc(alt || '') + '">';
  }
  function speciesHref(sci) { return '#/species/' + enc(sci); }
  function debounce(fn, ms) {
    var t; return function () { var a = arguments, self = this; clearTimeout(t); t = setTimeout(function () { fn.apply(self, a); }, ms); };
  }
  function setHash(path, params, replace) {
    var h = '#' + path + qs(params || {});
    if (replace) history.replaceState(null, '', h), render();
    else location.hash = h;
  }

  /* ------------------------------------------------------------------ status */

  var status = null;
  function loadStatus() {
    return api('status').then(function (s) {
      status = s;
      skew = parse(s.now) - Date.now();
      var pill = document.getElementById('status-pill');
      var txt = document.getElementById('status-text');
      var on = s.mqtt && s.mqtt.connected;
      pill.className = 'pill status ' + (on ? 'on' : 'off');
      txt.textContent = on ? (s.cameras.join(', ') || 'camera') + ' · live' : 'MQTT offline';
      pill.title = on ? 'Connected to ' + s.broker + ' since ' + fmtShort(s.mqtt.since) : 'Not connected to ' + s.broker;
      return s;
    }).catch(function () {
      document.getElementById('status-text').textContent = 'server unreachable';
      document.getElementById('status-pill').className = 'pill status off';
    });
  }
  setInterval(loadStatus, 30000);

  document.getElementById('top-search').addEventListener('submit', function (e) {
    e.preventDefault();
    var q = document.getElementById('top-q').value.trim();
    setHash('/history', { q: q });
  });

  /* ------------------------------------------------------------------ router */

  var routes = {};
  var current = null;
  var renderToken = 0;

  function route() {
    var h = location.hash.replace(/^#/, '') || '/today';
    var qi = h.indexOf('?');
    var path = qi >= 0 ? h.slice(0, qi) : h;
    var params = {};
    if (qi >= 0) h.slice(qi + 1).split('&').forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf('=');
      params[decodeURIComponent(i < 0 ? kv : kv.slice(0, i))] = i < 0 ? '1' : decodeURIComponent(kv.slice(i + 1).replace(/\+/g, ' '));
    });
    var parts = path.split('/').filter(Boolean);
    return { page: parts[0] || 'today', arg: parts.slice(1).map(decodeURIComponent).join('/'), params: params, path: path };
  }

  function render(keepScroll) {
    var r = route();
    var view = routes[r.page] || routes.today;
    document.querySelectorAll('[data-nav]').forEach(function (a) {
      if (a.getAttribute('data-nav') === r.page) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    var samePage = current && current.page === r.page && current.arg === r.arg;
    current = r;
    var token = ++renderToken;
    main.classList.add('loading');
    Promise.resolve(status || loadStatus()).then(function () {
      return view(r, token);
    }).then(function (html) {
      if (token !== renderToken || html === undefined) return;
      main.innerHTML = html;
      main.classList.remove('loading');
      if (view.after) view.after(r);
      if (!samePage && !keepScroll) { window.scrollTo(0, 0); }
    }).catch(function (e) {
      if (token !== renderToken) return;
      main.classList.remove('loading');
      main.innerHTML = '<div class="card empty"><h3>Couldn’t load this page</h3><p>' + esc(e.message) + '</p></div>';
    });
  }
  window.addEventListener('hashchange', function () { render(); });

  /* ------------------------------------------------------------------ actions (event delegation) */

  var actions = {};
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var fn = actions[el.getAttribute('data-act')];
    if (fn) { e.preventDefault(); fn(el, e); }
  });

  actions.keep = function (el) {
    var ids = el.dataset.ids.split(',');
    Promise.all(ids.map(function (id) { return api('detections/' + id, { method: 'PATCH', body: { reviewed: true } }); }))
      .then(function () { toast('Kept'); render(true); }).catch(fail);
  };
  actions['not-bird'] = function (el) {
    var ids = el.dataset.ids.split(',');
    if (!confirm('Delete ' + (ids.length > 1 ? 'these ' + ids.length + ' detections' : 'this detection') + '? Snapshots are removed too.')) return;
    Promise.all(ids.map(function (id) { return api('detections/' + id, { method: 'DELETE' }); }))
      .then(function () { toast('Deleted'); closeViewer(); render(true); }).catch(fail);
  };
  actions['delete'] = actions['not-bird'];
  actions.view = function (el) { openViewer(JSON.parse(el.dataset.det), el.dataset.mode); };
  actions.clear = function (el) {
    var r = route(); var p = Object.assign({}, r.params);
    el.dataset.keys.split(',').forEach(function (k) { delete p[k]; });
    delete p.page;
    setHash(r.path, p);
  };

  function detData(d) { return esc(JSON.stringify(d)); }

  /* ------------------------------------------------------------------ viewer dialog */

  var viewer = document.getElementById('viewer');
  function closeViewer() {
    var v = viewer.querySelector('video'); if (v) v.pause();
    if (viewer.open) viewer.close();
  }
  viewer.addEventListener('click', function (e) { if (e.target === viewer) closeViewer(); });
  viewer.addEventListener('close', function () { var v = viewer.querySelector('video'); if (v) v.pause(); viewer.querySelector('.viewer-inner').innerHTML = ''; });

  function openViewer(d, mode) {
    var inner = viewer.querySelector('.viewer-inner');
    var media = mode === 'clip'
      ? '<video controls autoplay playsinline src="' + clipUrl(d.frigate_event) + '"></video>'
      : '<img src="' + snapUrl(d.frigate_event) + '" alt="Snapshot of ' + esc(d.common_name) + '">';
    inner.innerHTML =
      '<div class="viewer-media">' + media + '</div>' +
      '<div class="viewer-body"><div>' +
      '<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><h2><a href="' + speciesHref(d.scientific_name) + '" style="color:inherit;text-decoration:none">' + esc(d.common_name) + '</a></h2>' + confPill(d.score) + '</div>' +
      '<div class="muted" style="margin-top:4px"><i>' + esc(d.scientific_name) + '</i> · ' + esc(fmtShort(d.time)) + ' · ' + esc(d.camera) + '</div></div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
      (mode === 'clip' ? '<button class="btn" type="button" data-vact="snap">Snapshot</button>' : '<button class="btn primary" type="button" data-vact="clip">' + ICON.play + 'Play clip</button>') +
      '<button class="btn" type="button" data-vact="fix">Fix ID</button>' +
      (d.flagged ? '<button class="btn" type="button" data-act="keep" data-ids="' + d.id + '">Keep</button>' : '') +
      '<button class="btn icon danger" type="button" aria-label="Delete detection" data-act="delete" data-ids="' + d.id + '">' + ICON.trash + '</button>' +
      '<button class="btn icon" type="button" aria-label="Close" data-vact="close">' + ICON.x + '</button>' +
      '</div></div><div class="fix" hidden></div>';
    inner.onclick = function (e) {
      var b = e.target.closest('[data-vact]'); if (!b) return;
      var a = b.getAttribute('data-vact');
      if (a === 'close') closeViewer();
      if (a === 'clip' || a === 'snap') openViewer(d, a === 'clip' ? 'clip' : 'snap');
      if (a === 'fix') showFix(inner.querySelector('.fix'), d);
    };
    if (!viewer.open) viewer.showModal();
    if (mode === 'fix') showFix(inner.querySelector('.fix'), d);
  }

  function showFix(box, d) {
    box.hidden = false;
    box.innerHTML = '<label class="lf ac" style="flex:1 1 280px"><span class="label">Correct species</span>' +
      '<input class="field" type="search" placeholder="Start typing a bird name…" autocomplete="off" data-ac="fix"></label>' +
      '<button class="btn primary" type="button" disabled>Save</button>';
    var input = box.querySelector('input'), save = box.querySelector('button');
    var chosen = null;
    attachAutocomplete(input, function (item) { chosen = item; input.value = item.common_name; save.disabled = false; });
    save.onclick = function () {
      if (!chosen) return;
      api('detections/' + d.id, { method: 'PATCH', body: { scientific_name: chosen.scientific_name } })
        .then(function () { toast('Changed to ' + chosen.common_name); closeViewer(); render(true); }).catch(fail);
    };
    input.focus();
  }

  /* ------------------------------------------------------------------ autocomplete */

  function attachAutocomplete(input, onPick) {
    var wrap = input.parentElement;
    var list = document.createElement('ul');
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    wrap.appendChild(list);
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    var items = [], sel = -1;
    function draw() {
      list.innerHTML = items.map(function (it, i) {
        return '<li role="option" aria-selected="' + (i === sel) + '" data-i="' + i + '"><span>' + esc(it.common_name) +
          ' <i class="muted" style="font-size:12px">' + esc(it.scientific_name) + '</i></span><span class="mono muted" style="font-size:12px">' +
          (it.seen ? 'seen ' + num(it.seen) + '×' : 'never seen') + '</span></li>';
      }).join('');
      list.hidden = !items.length;
      input.setAttribute('aria-expanded', items.length ? 'true' : 'false');
    }
    var lookup = debounce(function () {
      var q = input.value.trim();
      if (q.length < 2) { items = []; draw(); return; }
      api('names?q=' + enc(q)).then(function (r) { items = r; sel = r.length ? 0 : -1; draw(); });
    }, 180);
    input.addEventListener('input', lookup);
    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;
      if (e.key === 'ArrowDown') { sel = Math.min(items.length - 1, sel + 1); draw(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
      else if (e.key === 'Enter' && sel >= 0) { e.preventDefault(); pick(sel); }
      else if (e.key === 'Escape') { items = []; draw(); }
    });
    list.addEventListener('mousedown', function (e) {
      var li = e.target.closest('li'); if (li) { e.preventDefault(); pick(+li.dataset.i); }
    });
    input.addEventListener('blur', function () { setTimeout(function () { items = []; draw(); }, 150); });
    function pick(i) { var it = items[i]; items = []; draw(); onPick(it); }
  }

  /* ------------------------------------------------------------------ shared bits */

  function barsList(list, opts) {
    opts = opts || {};
    var max = Math.max.apply(null, list.map(function (t) { return t.count; }).concat([1]));
    return '<ol class="bars">' + list.map(function (t, i) {
      return '<li class="' + (opts.ranked ? 'ranked' : '') + '">' +
        (opts.ranked ? '<span class="mono muted" style="font-size:13px">' + (i + 1) + '</span>' : '') +
        '<a href="' + speciesHref(t.scientific_name) + '">' + esc(t.common_name) + '</a>' +
        '<span class="mono" style="font-size:13px">' + num(t.count) + '</span>' +
        '<span class="track"><span class="' + (i === 0 ? 'peak' : '') + '" style="width:' + Math.round(t.count / max * 100) + '%"></span></span></li>';
    }).join('') + '</ol>';
  }

  function vbars(values, opts) {
    opts = opts || {};
    var max = Math.max.apply(null, values.concat([1]));
    return '<div class="vbars" style="grid-template-columns:repeat(' + values.length + ',minmax(0,1fr));height:' + (opts.height || 160) + 'px">' +
      values.map(function (v, i) {
        var cls = v === 0 ? 'zero' : (v === max ? 'peak' : '');
        return '<div class="' + cls + '" style="height:' + Math.max(2, Math.round(v / max * 100)) + '%" title="' + esc(opts.tip ? opts.tip(v, i) : v) + '"></div>';
      }).join('') + '</div>';
  }

  function hourAxis() {
    return '<div class="axis"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span></div>';
  }

  function emptyCard(title, text) {
    return '<div class="card empty"><h3>' + esc(title) + '</h3><p>' + text + '</p></div>';
  }

  /* ================================================================== TODAY */

  routes.today = function (r) {
    var day = r.params.date || todayStr();
    return api('today' + qs({ date: day, limit: 10 })).then(function (t) {
      var isToday = day === todayStr();
      var visits = t.visits || [];
      var head =
        '<section class="head"><div><div class="label">' + (isToday ? 'Today' : 'Daily summary') + '</div>' +
        '<h1>' + esc(fmtDay(day)) + '</h1>' +
        '<p class="muted" style="margin:0;font-size:16px">' + (t.total
          ? num(t.total) + ' visit' + (t.total === 1 ? '' : 's') + ' from ' + t.species_count + ' species' + (isToday ? ' so far' : '') +
            ' · first visitor at ' + esc(fmtTime(t.first.time)) + ' (' + esc(t.first.common_name) + ')'
          : (isToday ? 'No visitors yet today.' : 'No visitors recorded on this day.')) + '</p></div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">' +
        '<a class="btn" href="#/today?date=' + addDays(day, -1) + '">' + ICON.left + 'Previous day</a>' +
        '<label style="display:flex"><span class="vh">Jump to date</span><input class="field" type="date" id="day-pick" value="' + day + '" max="' + todayStr() + '"' +
        (status.earliest_date ? ' min="' + status.earliest_date + '"' : '') + '></label>' +
        (isToday ? '' : '<a class="btn" href="#/today?date=' + addDays(day, 1) + '">Next day' + ICON.right + '</a><a class="btn" href="#/today">Today</a>') +
        '</div></section>';

      var arrival = (t.arrivals || [])[0];
      var tiles = '<section class="tiles" aria-label="At a glance">' +
        '<div class="card tile"><div class="label">Visits</div><div class="v">' + num(t.total) + '</div><div class="n">' +
        (t.weekday_average != null ? 'vs. ' + t.weekday_average + ' on an average ' + esc(fmtDay(day, { weekday: 'long' })) : 'detections that day') + '</div></div>' +
        '<div class="card tile"><div class="label">Species</div><div class="v">' + t.species_count + '</div><div class="n">of ' + t.life_list_size + ' on your life list</div></div>' +
        '<div class="card tile"><div class="label">Busiest hour</div><div class="v">' + (t.peak_hour != null ? hourLabel(t.peak_hour).replace(' ', ' ') : '—') + '</div><div class="n">' +
        (t.peak_hour != null ? t.peak_count + ' visit' + (t.peak_count === 1 ? '' : 's') : 'nothing yet') + '</div></div>' +
        (arrival
          ? '<div class="card tile gold"><div class="label">New this season</div><div class="v sm"><a href="' + speciesHref(arrival.scientific_name) + '" style="color:inherit;text-decoration:none">' + esc(arrival.common_name) + '</a></div><div class="n">First seen ' + esc(fmtTime(arrival.time)) + '</div></div>'
          : '<div class="card tile"><div class="label">Last visitor</div><div class="v sm">' + (visits[0] ? esc(visits[0].common_name) : '—') + '</div><div class="n">' + (visits[0] ? esc(ago(visits[0].latest.time)) : '') + '</div></div>') +
        '</section>';

      var hero = '';
      if (visits.length) {
        var v = visits[0], d = v.latest;
        hero = '<article class="card hero"><button type="button" class="ph" data-act="view" data-det="' + detData(d) + '" aria-label="Open snapshot">' +
          bird(140) + img(d.frigate_event, 'full', d.common_name) +
          '<span class="pill over" style="top:16px;left:16px;padding:6px 12px">Latest visit · ' + esc(ago(d.time)) + '</span></button>' +
          '<div class="hero-body"><div><div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">' +
          '<h2 class="disp"><a href="' + speciesHref(d.scientific_name) + '">' + esc(d.common_name) + '</a></h2>' + confPill(d.score) + '</div>' +
          '<div class="muted" style="margin-top:6px"><i>' + esc(d.scientific_name) + '</i> · ' + esc(fmtTime(d.time)) + ' · ' + esc(d.camera) +
          (v.count > 1 ? ' · ' + v.count + ' detections in this visit' : '') + '</div></div>' +
          '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
          '<button class="btn primary" type="button" data-act="view" data-mode="clip" data-det="' + detData(d) + '">' + ICON.play + 'Play clip</button>' +
          '<button class="btn" type="button" data-act="view" data-mode="fix" data-det="' + detData(d) + '">Fix ID</button>' +
          '<button class="btn icon" type="button" aria-label="Delete detection" data-act="delete" data-ids="' + d.id + '">' + ICON.trash + '</button>' +
          '</div></div></article>';
      }
      var top = '<aside class="card pad stack" style="flex:1 1 320px"><div class="sec-head"><h2>Top this week</h2><a href="#/stats?range=7d" style="font-size:14px">All stats</a></div>' +
        (t.top_week.length ? barsList(t.top_week, { ranked: true }) : '<p class="muted">No visits in the last 7 days.</p>') + '</aside>';

      var cards = visits.map(function (g) {
        var d = g.latest, ids = g.detections.map(function (x) { return x.id; }).join(',');
        return '<article class="card visit"><button type="button" class="ph" data-act="view" data-det="' + detData(g.best) + '" aria-label="Open snapshot of ' + esc(g.common_name) + '">' +
          bird(72) + img(g.best.frigate_event, 'crop', g.common_name) +
          (g.count > 1 ? '<span class="pill over tr">×' + g.count + (g.span_minutes ? ' in ' + g.span_minutes + ' min' : '') + '</span>' : '') +
          (g.first_ever ? '<span class="pill hi tl">First ever</span>' : g.first_of_season ? '<span class="pill hi tl">New this season</span>' : '') +
          '</button><div class="visit-body"><div class="visit-name"><a href="' + speciesHref(g.scientific_name) + '">' + esc(g.common_name) + '</a>' + confPill(g.best.score) + '</div>' +
          '<span class="muted" style="font-size:13px">' + esc(fmtTime(d.time)) + ' · ' + esc(ago(d.time)) + '</span>' +
          (g.flagged ? '<div class="flagbox">Needs review — ' + (g.first_ever ? 'first time this species has been seen here.' : 'the model wasn’t very sure.') + '</div>' +
            '<div class="two"><button class="btn" type="button" data-act="keep" data-ids="' + ids + '">Keep</button>' +
            '<button class="btn danger" type="button" data-act="not-bird" data-ids="' + ids + '">Not a bird</button></div>' : '') +
          '</div></article>';
      }).join('');

      var maxCell = 1;
      t.species.forEach(function (s) { s.hours.forEach(function (n) { if (n > maxCell) maxCell = n; }); });
      var nowH = isToday ? nowServer().getHours() : 23;
      var hours = []; for (var i = 0; i < 24; i++) hours.push(i);
      var heat = '<section class="card pad stack"><div class="sec-head"><div><h2>' + (isToday ? 'Today' : 'That day') + ' by hour</h2>' +
        '<p class="sub">Select a cell to see those visits. Species sorted by total.</p></div>' +
        '<div class="legend"><span>Fewer</span><span class="sq" style="background:rgba(233,180,76,.25)"></span><span class="sq" style="background:rgba(233,180,76,.55)"></span><span class="sq" style="background:rgba(233,180,76,.8)"></span><span class="sq" style="background:#E9B44C"></span><span>More</span></div></div>' +
        (t.species.length ? '<div class="heat"><div class="heat-grid"><div class="heat-row"><span class="label">Species</span><span class="label" style="text-align:right;padding-right:8px">Total</span>' +
          hours.map(function (h) { return '<span class="mono muted" style="font-size:11px;text-align:center">' + h + '</span>'; }).join('') + '</div>' +
          t.species.map(function (s) {
            return '<div class="heat-row"><a class="n" href="' + speciesHref(s.scientific_name) + '">' + esc(s.common_name) + '</a><span class="mono" style="font-size:13px;text-align:right;padding-right:8px">' + s.total + '</span>' +
              s.hours.map(function (n, h) {
                if (h > nowH) return '<span class="cell future"></span>';
                if (!n) return '<span class="cell zero"></span>';
                var a = 0.25 + 0.75 * n / maxCell;
                return '<a class="cell" href="#/history' + qs({ from: day, to: day, hour: h, species: s.scientific_name }) + '" title="' + esc(s.common_name + ', ' + hourLabel(h) + ': ' + n) + '" style="background:rgba(233,180,76,' + a.toFixed(2) + ');color:' + (a > 0.6 ? '#1A1405' : '#E8EDE9') + '">' + n + '</a>';
              }).join('') + '</div>';
          }).join('') + '</div></div>' : '<p class="muted">Nothing to chart yet.</p>') + '</section>';

      var recent = '<section class="stack"><div class="sec-head"><h2 class="disp big" style="font-size:24px">' + (isToday ? 'Recent visits' : 'Visits up to that day') + '</h2><a href="#/history" style="font-size:14px">Browse all history</a></div>' +
        (cards ? '<div class="visits">' + cards + '</div>' : emptyCard('No visits yet', 'Detections show up here as soon as Frigate spots a bird.')) + '</section>';

      return head + tiles + (hero ? '<section class="row">' + hero + top + '</section>' : '<section class="row">' + top + '</section>') + recent + heat;
    });
  };
  routes.today.after = function () {
    var p = document.getElementById('day-pick');
    if (p) p.addEventListener('change', function () { if (p.value) setHash('/today', { date: p.value === todayStr() ? '' : p.value }); });
  };

  /* ================================================================== HISTORY */

  routes.history = function (r) {
    var p = r.params;
    var query = {
      q: p.q, species: p.species, from: p.from, to: p.to, camera: p.camera, min_score: p.min_score,
      hide_flagged: p.hide_flagged, flagged: p.flagged, first_of_season: p.first_of_season, hour: p.hour,
      sort: p.sort, page: p.page || 1, page_size: p.view === 'grid' ? 48 : 25
    };
    return api('detections' + qs(query)).then(function (res) {
      var minConf = p.min_score ? Math.round(p.min_score * 100) : 0;
      var form =
        '<form class="card filters" id="filters" aria-label="Filter detections">' +
        '<label class="lf wide"><span class="label">Species</span><input class="field" name="q" type="search" value="' + esc(p.q || '') + '" placeholder="Common or scientific name"></label>' +
        '<label class="lf"><span class="label">From</span><input class="field" name="from" type="date" value="' + esc(p.from || '') + '"></label>' +
        '<label class="lf"><span class="label">To</span><input class="field" name="to" type="date" value="' + esc(p.to || '') + '"></label>' +
        '<label class="lf"><span class="label">Camera</span><select class="field" name="camera"><option value="">All cameras</option>' +
        res.cameras.map(function (c) { return '<option' + (c === p.camera ? ' selected' : '') + '>' + esc(c) + '</option>'; }).join('') + '</select></label>' +
        '<label class="lf"><span class="label">Min. confidence · <span class="mono" id="mc-v" style="color:var(--ink)">' + (minConf ? minConf + '%' : 'any') + '</span></span>' +
        '<input type="range" name="min_score" min="0" max="100" step="5" value="' + minConf + '"></label>' +
        '<label class="chk"><input type="checkbox" name="hide_flagged"' + (p.hide_flagged ? ' checked' : '') + '> Hide detections needing review</label>' +
        '<label class="chk"><input type="checkbox" name="flagged"' + (p.flagged ? ' checked' : '') + '> Only ones needing review</label>' +
        '<label class="chk"><input type="checkbox" name="first_of_season"' + (p.first_of_season ? ' checked' : '') + '> First-of-season only</label>' +
        '</form>';

      var chips = [];
      if (p.q) chips.push(['“' + p.q + '”', 'q']);
      if (p.species) chips.push([(res.results[0] && res.results[0].scientific_name === p.species ? res.results[0].common_name : p.species), 'species']);
      if (p.from || p.to) chips.push([(p.from ? fmtDay(p.from, { month: 'short', day: 'numeric' }) : '…') + ' – ' + (p.to ? fmtDay(p.to, { month: 'short', day: 'numeric' }) : 'now'), 'from,to']);
      if (p.hour) chips.push([hourLabel(+p.hour) + ' hour', 'hour']);
      if (p.camera) chips.push([p.camera, 'camera']);
      if (minConf) chips.push(['≥ ' + minConf + '%', 'min_score']);
      if (p.flagged) chips.push(['Needs review', 'flagged']);
      if (p.first_of_season) chips.push(['First of season', 'first_of_season']);
      var allKeys = 'q,species,from,to,hour,camera,min_score,hide_flagged,flagged,first_of_season';
      var bar = '<section class="sec-head" style="align-items:center"><div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px">' +
        chips.map(function (c) { return '<span class="chip">' + esc(c[0]) + '<button type="button" aria-label="Remove filter ' + esc(c[0]) + '" data-act="clear" data-keys="' + c[1] + '">×</button></span>'; }).join('') +
        (chips.length ? '<button class="btn ghost" type="button" data-act="clear" data-keys="' + allKeys + '">Clear all</button>' : '') +
        '</div><div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">' +
        '<span class="muted" style="font-size:14px"><span class="mono" style="color:var(--ink)">' + num(res.total) + '</span> detections · ' + res.species + ' species · ' + res.days + ' days</span>' +
        '<div class="seg" role="group" aria-label="View"><button type="button" aria-pressed="' + (p.view !== 'grid') + '" data-view="">List</button><button type="button" aria-pressed="' + (p.view === 'grid') + '" data-view="grid">Grid</button></div>' +
        '<label style="display:flex"><span class="vh">Sort</span><select class="field" id="sort">' +
        [['newest', 'Newest first'], ['oldest', 'Oldest first'], ['confidence', 'Highest confidence']].map(function (o) {
          return '<option value="' + o[0] + '"' + ((p.sort || 'newest') === o[0] ? ' selected' : '') + '>' + o[1] + '</option>';
        }).join('') + '</select></label></div></section>';

      var body;
      if (!res.results.length) {
        body = emptyCard('No detections match', 'Try widening the date range or clearing a filter.');
      } else if (p.view === 'grid') {
        body = '<section class="card"><div class="grid-results">' + res.results.map(function (d) {
          return '<article class="card visit"><button type="button" class="ph" data-act="view" data-det="' + detData(d) + '" aria-label="Open snapshot">' + bird(56) + img(d.frigate_event, 'crop', d.common_name) + '</button>' +
            '<div class="visit-body"><div class="visit-name"><a href="' + speciesHref(d.scientific_name) + '">' + esc(d.common_name) + '</a>' + confPill(d.score) + '</div>' +
            '<span class="muted" style="font-size:13px">' + esc(fmtShort(d.time)) + '</span></div></article>';
        }).join('') + '</div></section>';
      } else {
        var byDay = [];
        res.results.forEach(function (d) {
          var k = d.time.slice(0, 10);
          if (!byDay.length || byDay[byDay.length - 1].day !== k) byDay.push({ day: k, rows: [] });
          byDay[byDay.length - 1].rows.push(d);
        });
        body = '<section class="card" style="overflow:hidden">' + byDay.map(function (g) {
          return '<div class="day-h"><h2 class="disp">' + esc(fmtDay(g.day, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })) + '</h2>' +
            '<a class="mono muted" style="font-size:13px" href="#/today?date=' + g.day + '">day summary</a></div>' +
            g.rows.map(function (d) {
              return '<div class="hrow"><button type="button" class="ph" data-act="view" data-det="' + detData(d) + '" aria-label="Open snapshot">' + bird(38) + img(d.frigate_event, 'crop', d.common_name) + '</button>' +
                '<span class="t">' + esc(fmtTime(d.time)) + '</span>' +
                '<div class="who"><a href="' + speciesHref(d.scientific_name) + '">' + esc(d.common_name) + '</a><div class="sci">' + esc(d.scientific_name) + '</div></div>' +
                (d.flagged ? '<span class="pill lo">needs review</span>' : '') + confPill(d.score) +
                '<span class="muted cam" style="font-size:13px;min-width:70px">' + esc(d.camera) + '</span>' +
                '<div class="acts"><button class="btn icon" type="button" aria-label="Play clip" data-act="view" data-mode="clip" data-det="' + detData(d) + '">' + ICON.play + '</button>' +
                '<button class="btn icon" type="button" aria-label="Fix identification" data-act="view" data-mode="fix" data-det="' + detData(d) + '">' + ICON.edit + '</button>' +
                '<button class="btn icon" type="button" aria-label="Delete detection" data-act="delete" data-ids="' + d.id + '">' + ICON.trash + '</button></div></div>';
            }).join('');
        }).join('') + '</section>';
      }

      var pages = Math.max(1, Math.ceil(res.total / res.page_size));
      var cur = res.page;
      var nums = [];
      for (var i = 1; i <= pages; i++) if (i === 1 || i === pages || Math.abs(i - cur) <= 2) nums.push(i);
      var pager = pages > 1 ? '<nav class="pager" aria-label="Pagination"><span class="muted" style="font-size:14px">Showing ' +
        num((cur - 1) * res.page_size + 1) + '–' + num(Math.min(res.total, cur * res.page_size)) + ' of ' + num(res.total) + '</span><div class="pgs">' +
        '<button class="pg" type="button" data-page="' + (cur - 1) + '"' + (cur === 1 ? ' disabled' : '') + ' aria-label="Previous page">‹</button>' +
        nums.map(function (n, idx) {
          var gap = idx > 0 && n - nums[idx - 1] > 1 ? '<span class="muted" style="align-self:center;padding:0 4px">…</span>' : '';
          return gap + '<button class="pg" type="button" data-page="' + n + '"' + (n === cur ? ' aria-current="page"' : '') + '>' + n + '</button>';
        }).join('') +
        '<button class="pg" type="button" data-page="' + (cur + 1) + '"' + (cur === pages ? ' disabled' : '') + ' aria-label="Next page">›</button></div></nav>' : '';

      var csvQuery = Object.assign({}, query); delete csvQuery.page; delete csvQuery.page_size; delete csvQuery.sort;
      return '<section class="head"><div><div class="label">History</div><h1>Every visit, searchable</h1></div>' +
        '<a class="btn" href="api/detections.csv' + qs(csvQuery) + '" download>' + ICON.down + 'Export CSV</a></section>' +
        form + bar + body + pager;
    });
  };
  routes.history.after = function (r) {
    var form = document.getElementById('filters');
    function apply() {
      var p = Object.assign({}, r.params);
      ['q', 'from', 'to', 'camera'].forEach(function (k) { p[k] = form.elements[k].value.trim(); });
      var mc = +form.elements.min_score.value;
      p.min_score = mc ? (mc / 100).toFixed(2) : '';
      ['hide_flagged', 'flagged', 'first_of_season'].forEach(function (k) { p[k] = form.elements[k].checked; });
      delete p.page;
      setHash('/history', p, true);
    }
    form.addEventListener('submit', function (e) { e.preventDefault(); apply(); });
    form.elements.q.addEventListener('input', debounce(apply, 400));
    ['from', 'to', 'camera', 'hide_flagged', 'flagged', 'first_of_season'].forEach(function (k) { form.elements[k].addEventListener('change', apply); });
    form.elements.min_score.addEventListener('input', function () {
      var v = +form.elements.min_score.value; document.getElementById('mc-v').textContent = v ? v + '%' : 'any';
    });
    form.elements.min_score.addEventListener('change', apply);
    document.getElementById('sort').addEventListener('change', function (e) { setHash('/history', Object.assign({}, r.params, { sort: e.target.value, page: '' }), true); });
    document.querySelectorAll('[data-view]').forEach(function (b) {
      b.addEventListener('click', function () { setHash('/history', Object.assign({}, r.params, { view: b.dataset.view, page: '' }), true); });
    });
    document.querySelectorAll('[data-page]').forEach(function (b) {
      b.addEventListener('click', function () { setHash('/history', Object.assign({}, r.params, { page: b.dataset.page })); });
    });
  };

  /* ================================================================== SPECIES */

  routes.species = function (r) {
    if (r.arg) return speciesDetail(r.arg);
    return api('species').then(function (list) {
      var p = r.params, q = (p.q || '').toLowerCase();
      var shown = list.filter(function (s) {
        if (s.hidden && !p.hidden) return false;
        return !q || s.common_name.toLowerCase().indexOf(q) >= 0 || s.scientific_name.toLowerCase().indexOf(q) >= 0;
      });
      if (p.sort === 'name') shown.sort(function (a, b) { return a.common_name.localeCompare(b.common_name); });
      if (p.sort === 'recent') shown.sort(function (a, b) { return a.last < b.last ? 1 : -1; });
      if (p.sort === 'new') shown.sort(function (a, b) { return a.first < b.first ? 1 : -1; });
      var hiddenCount = list.filter(function (s) { return s.hidden; }).length;
      return '<section class="head"><div><div class="label">Species</div><h1>' + list.filter(function (s) { return !s.hidden; }).length + ' species at your feeder</h1></div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">' +
        '<label style="display:flex"><span class="vh">Filter species</span><input class="field" id="sp-q" type="search" placeholder="Filter…" value="' + esc(p.q || '') + '"></label>' +
        '<label style="display:flex"><span class="vh">Sort</span><select class="field" id="sp-sort">' +
        [['visits', 'Most visits'], ['recent', 'Recently seen'], ['new', 'Newest arrivals'], ['name', 'A–Z']].map(function (o) {
          return '<option value="' + o[0] + '"' + ((p.sort || 'visits') === o[0] ? ' selected' : '') + '>' + o[1] + '</option>';
        }).join('') + '</select></label>' +
        (hiddenCount ? '<label class="chk"><input type="checkbox" id="sp-hidden"' + (p.hidden ? ' checked' : '') + '> Show ' + hiddenCount + ' hidden</label>' : '') +
        '</div></section>' +
        (shown.length ? '<section class="sp-list">' + shown.map(function (s) {
          return '<a class="card sp-card" href="' + speciesHref(s.scientific_name) + '"><span class="ph">' + bird(36) + (s.best_event ? img(s.best_event, 'crop', '') : '') + '</span>' +
            '<span style="min-width:0"><span style="display:block;font-weight:600">' + esc(s.common_name) + (s.hidden ? ' <span class="pill line">hidden</span>' : '') + '</span>' +
            '<span class="muted" style="display:block;font-size:13px;font-style:italic">' + esc(s.scientific_name) + '</span>' +
            '<span class="mono muted" style="display:block;font-size:12px;margin-top:4px">' + num(s.visits) + ' visits · last ' + esc(fmtShort(s.last)) + '</span></span></a>';
        }).join('') + '</section>' : emptyCard('No species yet', 'Once birds are detected they’ll be listed here.'));
    });
  };
  routes.species.after = function (r) {
    if (r.arg) return speciesAfter(r);
    var qI = document.getElementById('sp-q');
    var go = function () {
      var h = document.getElementById('sp-hidden');
      setHash('/species', { q: qI.value.trim(), sort: document.getElementById('sp-sort').value, hidden: h && h.checked }, true);
    };
    qI.addEventListener('input', debounce(go, 300));
    document.getElementById('sp-sort').addEventListener('change', go);
    var h = document.getElementById('sp-hidden'); if (h) h.addEventListener('change', go);
  };

  function speciesDetail(sci) {
    return api('species/' + enc(sci)).then(function (s) {
      var back = '<a href="#/species" style="font-size:14px;display:inline-flex;align-items:center;gap:6px;min-height:44px;align-self:flex-start">' + ICON.left + 'All species</a>';
      if (!s.visits) {
        return back + emptyCard(s.common_name, 'No detections of this species yet.');
      }
      var thr = s.prefs.min_score;
      var opts = [['', 'Use global (' + pct(status.threshold) + ')']].concat([0.75, 0.8, 0.85, 0.9, 0.95].map(function (v) { return [v, pct(v)]; }));
      var hero = '<section class="sp-hero"><button type="button" class="ph" data-act="view" data-det="' + detData(s.best) + '" aria-label="Open best snapshot">' +
        bird(180) + img(s.best.frigate_event, 'full', s.common_name) +
        '<span class="pill hi" style="top:16px;left:16px;padding:6px 12px">Best shot · ' + pct(s.best.score) + '</span></button>' +
        '<div class="sp-info"><div><div style="display:flex;gap:8px;flex-wrap:wrap">' +
        (s.rank ? '<span class="pill line">#' + s.rank + ' all time</span>' : '') +
        (s.prefs.hidden ? '<span class="pill lo">hidden</span>' : '') + (s.watching ? '<span class="pill hi">on your alert list</span>' : '') + '</div>' +
        '<h1>' + esc(s.common_name) + '</h1><p class="muted" style="margin:0;font-size:17px;font-style:italic">' + esc(s.scientific_name) + '</p></div>' +
        '<div class="stats3">' +
        '<div class="stat"><div class="label">Total visits</div><div class="v">' + num(s.visits) + '</div></div>' +
        '<div class="stat"><div class="label">Days seen</div><div class="v">' + num(s.days_seen) + '</div></div>' +
        '<div class="stat"><div class="label">Peak hour</div><div class="v">' + (s.peak_hour != null ? hourLabel(s.peak_hour).replace(' ', ' ') : '—') + '</div></div>' +
        '<div class="stat"><div class="label">First seen</div><div class="v sm">' + esc(fmtDay(s.first, { month: 'short', day: 'numeric', year: 'numeric' })) + '</div></div>' +
        '<div class="stat"><div class="label">Last seen</div><div class="v sm">' + esc(fmtShort(s.last)) + '</div></div>' +
        '<div class="stat"><div class="label">Avg. confidence</div><div class="v sm">' + pct(s.avg_score) + '</div></div></div>' +
        '<div class="card" style="padding:16px 18px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between">' +
        '<label class="inline"><span>Minimum confidence for this species</span><select class="field" id="sp-thr">' +
        opts.map(function (o) { return '<option value="' + o[0] + '"' + ((thr == null ? '' : thr) == o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select></label>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        (s.watching ? '<a class="btn" href="#/settings/notifications">' + ICON.bell + 'Edit alert</a>' : '<button class="btn" type="button" id="sp-watch">' + ICON.bell + 'Add to alerts</button>') +
        '<button class="btn" type="button" id="sp-hide">' + (s.prefs.hidden ? 'Unhide species' : 'Hide species') + '</button></div></div>' +
        '</div></section>';

      var when = '<div class="card pad stack" style="flex:1 1 520px;min-width:0"><div><h2>When it visits</h2><p class="sub">Visits by hour of day, last 90 days</p></div>' +
        vbars(s.hours, { height: 180, tip: function (v, i) { return hourLabel(i) + ': ' + v + ' visits'; } }) + hourAxis() + '</div>';
      var comp = '<div class="card pad stack" style="flex:1 1 320px"><div><h2>Often seen with</h2><p class="sub">Other species at the feeder within 10 minutes</p></div>' +
        (s.companions.length ? '<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px">' + s.companions.map(function (c) {
          return '<li style="display:flex;justify-content:space-between;gap:12px"><a href="' + speciesHref(c.scientific_name) + '" style="color:var(--ink);text-decoration:none">' + esc(c.common_name) + '</a><span class="mono" style="font-size:13px;color:var(--ink2)">' + c.pct + '%</span></li>';
        }).join('') + '</ul>' : '<p class="muted">Usually comes alone.</p>') + '</div>';

      var calMax = Math.max.apply(null, s.calendar.map(function (d) { return d.n; }).concat([1]));
      var cal = '<section class="card pad stack"><div class="sec-head"><div><h2>Season at a glance</h2><p class="sub">Each square is a day over the last six months; brighter means more visits</p></div></div>' +
        '<div class="scroll"><div class="cal">' + s.calendar.map(function (d) {
          var c = d.n ? 'rgba(233,180,76,' + (0.22 + 0.78 * d.n / calMax).toFixed(2) + ')' : '#1B2420';
          return '<span style="background:' + c + '" title="' + esc(fmtDay(d.date, { month: 'short', day: 'numeric' }) + ': ' + d.n + ' visits') + '"></span>';
        }).join('') + '</div></div></section>';

      var photos = '<section class="stack"><div class="sec-head"><h2 class="disp" style="font-size:22px">Recent photos</h2><a href="#/history?species=' + enc(s.scientific_name) + '" style="font-size:14px">See all ' + num(s.visits) + ' visits</a></div>' +
        '<div class="photos">' + s.photos.map(function (d) {
          return '<button type="button" class="ph" data-act="view" data-det="' + detData(d) + '" aria-label="Open snapshot from ' + esc(fmtShort(d.time)) + '">' + bird(56) + img(d.frigate_event, 'crop', '') +
            '<span class="when">' + esc(fmtShort(d.time)) + '</span></button>';
        }).join('') + '</div></section>';

      speciesDetail.current = s;
      return back + hero + '<section class="row">' + when + comp + '</section>' + cal + photos;
    });
  }
  function speciesAfter() {
    var s = speciesDetail.current; if (!s) return;
    var thr = document.getElementById('sp-thr');
    function savePrefs(patch) {
      var body = Object.assign({ min_score: s.prefs.min_score, hidden: s.prefs.hidden }, patch);
      return api('species/' + enc(s.scientific_name) + '/prefs', { method: 'PUT', body: body });
    }
    if (thr) thr.addEventListener('change', function () {
      savePrefs({ min_score: thr.value ? +thr.value : null }).then(function () { toast('Saved'); s.prefs.min_score = thr.value ? +thr.value : null; }).catch(fail);
    });
    var hide = document.getElementById('sp-hide');
    if (hide) hide.addEventListener('click', function () {
      var to = !s.prefs.hidden;
      if (to && !confirm('Hide ' + s.common_name + '? New detections will be ignored and it disappears from stats. You can unhide it later from Species or Settings.')) return;
      savePrefs({ hidden: to }).then(function () { toast(to ? 'Hidden' : 'Unhidden'); render(true); }).catch(fail);
    });
    var watch = document.getElementById('sp-watch');
    if (watch) watch.addEventListener('click', function () {
      api('watchlist', { method: 'POST', body: { scientific_name: s.scientific_name, min_score: 0.8, cooldown_min: 15 } })
        .then(function () { toast(s.common_name + ' added to alerts'); render(true); }).catch(fail);
    });
  }

  /* ================================================================== STATS */

  routes.stats = function (r) {
    var key = r.params.range || '30d';
    return api('stats?range=' + key).then(function (s) {
      var ranges = [['7d', '7 days'], ['30d', '30 days'], ['season', 'Season'], ['year', 'Year'], ['all', 'All time']];
      var head = '<section class="head"><div><div class="label">Stats</div><h1>Your feeder, by the numbers</h1></div>' +
        '<div class="seg" role="group" aria-label="Time range">' + ranges.map(function (x) {
          return '<a class="btn ghost" style="min-height:40px;border-radius:9px;' + (x[0] === key ? 'background:var(--accent);color:var(--accent-ink)' : '') + '" href="#/stats?range=' + x[0] + '"' + (x[0] === key ? ' aria-current="true"' : '') + '>' + x[1] + '</a>';
        }).join('') + '</div></section>';

      var newNames = s.arrivals.slice(0, 2).map(function (a) { return a.common_name; }).join(', ');
      var tiles = '<section class="tiles"><div class="card tile"><div class="label">Visits</div><div class="v">' + num(s.visits) + '</div><div class="n">' + s.per_day + ' per day on average</div></div>' +
        '<div class="card tile"><div class="label">Species</div><div class="v">' + s.species + '</div><div class="n">of ' + s.life_list_size + ' on your life list</div></div>' +
        '<div class="card tile"><div class="label">New arrivals</div><div class="v">' + s.arrivals.length + '</div><div class="n">' + (newNames ? esc(newNames) : 'firsts and returning species') + '</div></div>' +
        '<div class="card tile"><div class="label">Busiest day</div><div class="v">' + (s.busiest_day ? esc(fmtDay(s.busiest_day.date, { month: 'short', day: 'numeric' })) : '—') + '</div><div class="n">' +
        (s.busiest_day ? esc(fmtDay(s.busiest_day.date, { weekday: 'long' })) + ' · ' + s.busiest_day.n + ' visits' : 'no visits') + '</div></div></section>';

      // line chart
      var series = s.series, n = series.length;
      var max = Math.max.apply(null, series.map(function (x) { return x.n; }).concat([4]));
      var niceMax = Math.ceil(max / 4) * 4;
      var W = 600, H = 220;
      function x(i) { return n > 1 ? (i / (n - 1) * W).toFixed(1) : W / 2; }
      function y(v) { return (H - v / niceMax * H).toFixed(1); }
      var line = series.map(function (p, i) { return x(i) + ',' + y(p.n); }).join(' ');
      var avg = series.map(function (p, i) {
        var a = 0, c = 0; for (var k = Math.max(0, i - 6); k <= i; k++) { a += series[k].n; c++; }
        return x(i) + ',' + y(a / c);
      }).join(' ');
      var ticks = [0, Math.floor((n - 1) / 3), Math.floor(2 * (n - 1) / 3), n - 1].filter(function (v, i, arr) { return arr.indexOf(v) === i; });
      var chart = '<div class="card pad stack" style="flex:2 1 600px;min-width:0"><div class="sec-head"><h2>Visits per ' + s.bucket + '</h2>' +
        '<span class="muted" style="font-size:13px">' + esc(s.label) + (s.bucket === 'day' ? ' · dashed line is the 7-day average' : '') + '</span></div>' +
        '<div style="display:flex;gap:10px"><div class="mono muted" style="display:flex;flex-direction:column;justify-content:space-between;font-size:11px;height:220px;text-align:right;width:28px">' +
        [niceMax, niceMax * 3 / 4, niceMax / 2, niceMax / 4, 0].map(function (v) { return '<span>' + Math.round(v) + '</span>'; }).join('') + '</div>' +
        '<svg class="linechart" viewBox="0 0 600 220" preserveAspectRatio="none" role="img" aria-label="Visits per ' + s.bucket + ' chart">' +
        [0.5, 55, 110, 165].map(function (yy) { return '<line x1="0" x2="600" y1="' + yy + '" y2="' + yy + '" stroke="#222C27"/>'; }).join('') +
        '<line x1="0" x2="600" y1="219.5" y2="219.5" stroke="#33403A"/>' +
        (n ? '<polygon points="0,' + H + ' ' + line + ' ' + W + ',' + H + '" fill="rgba(233,180,76,0.12)"/>' +
          '<polyline points="' + line + '" fill="none" stroke="#E9B44C" stroke-width="2.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>' +
          (s.bucket === 'day' && n > 7 ? '<polyline points="' + avg + '" fill="none" stroke="#C9D3CE" stroke-width="1.5" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>' : '') : '') +
        '</svg></div><div class="mono muted" style="display:flex;justify-content:space-between;font-size:11px;padding-left:38px">' +
        ticks.map(function (i) { return '<span>' + esc(fmtDay(series[i].label, { month: 'short', day: 'numeric' })) + '</span>'; }).join('') + '</div></div>';

      var top = '<div class="card pad stack" style="flex:1 1 340px"><div class="sec-head"><h2>Most common</h2><span class="muted" style="font-size:13px">' + esc(s.label) + '</span></div>' +
        (s.top.length ? barsList(s.top) : '<p class="muted">No visits in this range.</p>') + '</div>';

      var weeks = '<div class="card pad stack" style="flex:1 1 480px;min-width:0"><div><h2>Species per week</h2><p class="sub">Distinct species seen each week, last 26 weeks</p></div>' +
        vbars(s.species_weeks.map(function (w) { return w.n; }), { tip: function (v, i) { return 'Week of ' + fmtDay(s.species_weeks[i].week, { month: 'short', day: 'numeric' }) + ': ' + v + ' species'; } }) +
        '<div class="mono muted" style="display:flex;justify-content:space-between;font-size:11px"><span>' + esc(fmtDay(s.species_weeks[0].week, { month: 'short' })) + '</span><span>' + esc(fmtDay(s.species_weeks[13].week, { month: 'short' })) + '</span><span>This week</span></div></div>';
      var total = s.hours.reduce(function (a, b) { return a + b; }, 0) || 1;
      var hours = '<div class="card pad stack" style="flex:1 1 480px;min-width:0"><div><h2>Busiest hours</h2><p class="sub">All species, share of visits by hour (' + esc(s.label.toLowerCase()) + ')</p></div>' +
        vbars(s.hours, { tip: function (v, i) { return hourLabel(i) + ': ' + Math.round(v / total * 100) + '% of visits'; } }) + hourAxis() + '</div>';

      var newSet = {};
      s.arrivals.forEach(function (a) { newSet[a.scientific_name] = true; });
      var showAll = r.params.all === '1';
      var ll = s.life_list.filter(function (x) { return !x.hidden; });
      var shownLL = showAll ? ll : ll.slice(0, 12);
      var life = '<div class="card" style="flex:2 1 600px;min-width:0;padding:22px 0 8px"><div class="sec-head" style="padding:0 24px 10px"><h2>Life list</h2>' +
        '<span class="muted" style="font-size:13px">' + ll.length + ' species' + (status.earliest_date ? ' since ' + esc(fmtDay(status.earliest_date, { month: 'short', day: 'numeric', year: 'numeric' })) : '') + '</span></div>' +
        '<div class="scroll"><table class="tbl"><thead><tr><th scope="col">Species</th><th scope="col">First seen</th><th scope="col">Last seen</th><th scope="col" style="text-align:right">Visits</th></tr></thead><tbody>' +
        shownLL.map(function (x) {
          return '<tr><td><a href="' + speciesHref(x.scientific_name) + '" style="font-weight:500">' + esc(x.common_name) + '</a>' + (newSet[x.scientific_name] ? ' <span class="pill hi" style="margin-left:6px">New</span>' : '') + '</td>' +
            '<td class="muted">' + esc(fmtShort(x.first)) + '</td><td class="muted">' + esc(fmtShort(x.last)) + '</td><td class="mono" style="text-align:right">' + num(x.visits) + '</td></tr>';
        }).join('') + '</tbody></table></div>' +
        (ll.length > 12 ? '<a href="#/stats?range=' + key + (showAll ? '' : '&all=1') + '" style="font-size:14px;padding:6px 24px 10px;min-height:44px;display:inline-flex;align-items:center">' + (showAll ? 'Show fewer' : 'Show all ' + ll.length + ' species') + '</a>' : '') + '</div>';

      var dq = '<aside class="card pad stack" style="flex:1 1 320px"><h2>Data quality</h2><p class="muted" style="margin:0;font-size:14px;line-height:1.5">Detections flagged because the model was unsure, or because it was the first time a species was seen.</p>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div class="warnstat"><div class="v">' + num(s.flagged_pending) + '</div><div style="font-size:13px;color:var(--warn-ink)">awaiting review</div></div>' +
        '<div class="stat"><div class="v" style="font-size:28px">' + num(s.removed_total) + '</div><div class="muted" style="font-size:13px">removed so far</div></div></div>' +
        (s.flagged_by_species.length ? '<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px;font-size:14px">' + s.flagged_by_species.map(function (f) {
          return '<li style="display:flex;justify-content:space-between;gap:8px"><span>' + esc(f.common_name) + '</span><span class="mono muted">' + f.n + ' flagged</span></li>';
        }).join('') + '</ul>' : '') +
        (s.flagged_pending ? '<a class="btn" href="#/history?flagged=1">Review flagged detections</a>' : '<p class="okmsg" style="margin:0">Nothing waiting for review.</p>') + '</aside>';

      return head + tiles + '<section class="row" style="align-items:flex-start">' + chart + top + '</section><section class="row">' + weeks + hours + '</section><section class="row" style="align-items:flex-start">' + life + dq + '</section>';
    });
  };

  /* ================================================================== SETTINGS */

  var SECTIONS = [['notifications', 'Notifications'], ['detection', 'Detection & thresholds'], ['storage', 'Snapshots & data'], ['about', 'About']];

  routes.settings = function (r) {
    var section = r.arg || 'notifications';
    return Promise.all([api('settings'), section === 'notifications' ? api('watchlist') : [], section === 'notifications' ? api('alerts/recent') : [],
      section === 'detection' ? api('species') : []]).then(function (res) {
      var st = res[0];
      routes.settings.state = { settings: st, watch: res[1], species: res[3] };
      var side = '<nav class="side" aria-label="Settings sections">' + SECTIONS.map(function (x) {
        return '<a href="#/settings/' + x[0] + '"' + (x[0] === section ? ' aria-current="page"' : '') + '>' + x[1] + '</a>';
      }).join('') + '</nav>';
      var body = ({ notifications: settingsNotifications, detection: settingsDetection, storage: settingsStorage, about: settingsAbout }[section] || settingsNotifications)(st, res);
      var title = (SECTIONS.filter(function (x) { return x[0] === section; })[0] || SECTIONS[0])[1];
      return '<section class="head"><div><div class="label">Settings</div><h1>' + esc(title) + '</h1></div></section>' +
        '<div class="settings">' + side + '<div class="set-main" id="set-main">' + body + '</div></div>';
    });
  };

  function sw(id, on, label, attrs) {
    return '<button class="sw" type="button" role="switch" id="' + id + '" aria-checked="' + (!!on) + '" aria-label="' + esc(label) + '"' + (attrs || '') + '><span></span></button>';
  }
  function select(id, value, options, attrs) {
    return '<select class="field" id="' + id + '"' + (attrs || '') + '>' + options.map(function (o) {
      return '<option value="' + o[0] + '"' + (String(value) === String(o[0]) ? ' selected' : '') + '>' + esc(o[1]) + '</option>';
    }).join('') + '</select>';
  }
  var CONF_OPTS = [[0.6, '60%'], [0.7, '70%'], [0.75, '75%'], [0.8, '80%'], [0.85, '85%'], [0.9, '90%'], [0.95, '95%']];
  var COOL_OPTS = [[0, 'No cooldown'], [5, '5 min'], [15, '15 min'], [30, '30 min'], [60, '1 hour'], [180, '3 hours'], [1440, 'Once a day']];

  function settingsNotifications(st, res) {
    var prefix = st.mqtt.topic_prefix;
    var mq = status.mqtt || {};
    var watch = res[1], recent = res[2];
    var conn = '<section class="card pad stack"><div class="toggle-head"><div><h2>MQTT connection</h2><p class="sub">Uses the broker from <span class="mono">config.yml</span>, the same one Frigate events arrive on.</p></div>' +
      '<span class="pill status ' + (mq.connected ? 'on' : 'off') + '"><span class="dot"></span>' + (mq.connected ? 'Connected' : 'Not connected') + '</span></div>' +
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;align-items:end">' +
      '<div class="lf"><span class="label">Broker</span><span class="mono" style="min-height:44px;display:flex;align-items:center">' + esc(status.broker) + '</span></div>' +
      '<label class="lf"><span class="label">Topic prefix</span><input class="field mono" id="s-prefix" value="' + esc(prefix) + '"></label>' +
      '<label class="chk">' + sw('s-discovery', st.mqtt.discovery, 'Home Assistant discovery') + 'Home Assistant discovery</label></div>' +
      '<label class="chk">' + sw('s-legacy', st.mqtt.legacy_topic, 'Original topic') + '<span>Also send the plain species name to <span class="mono">whosatmyfeeder/detections</span> (the original app’s topic, for existing automations)</span></label>' +
      '<div class="inline"><button class="btn" type="button" id="s-test">' + ICON.send + 'Send test message</button><span id="s-test-msg"></span></div>' +
      '<p class="sub" style="margin:0">Prefix and discovery changes take effect when the add-on restarts.</p></section>';

    var pa = st.publish_all;
    var all = '<section class="card pad stack"><div class="toggle-head"><div><h2>Publish every detection</h2>' +
      '<p class="sub">Sends each detection to <span class="mono" style="color:var(--ink2)">' + esc(prefix) + '/detection</span>. Good for logging or counters; too noisy for phone alerts.</p></div>' +
      sw('s-pa', pa.enabled, 'Publish every detection') + '</div>' +
      (pa.enabled ? '<div class="inline"><label class="inline">Minimum confidence ' + select('s-pa-min', pa.min_score == null ? '' : pa.min_score, [['', 'Detection threshold (' + pct(status.threshold) + ')']].concat(CONF_OPTS)) + '</label>' +
        '<label class="chk"><input type="checkbox" id="s-pa-skip"' + (pa.skip_flagged ? ' checked' : '') + '> Skip detections needing review</label></div>' : '') + '</section>';

    var a = st.alerts;
    var alerts = '<section class="card stack" style="padding:22px 0 8px"><div class="toggle-head" style="padding:0 24px"><div><h2>Species alerts</h2>' +
      '<p class="sub">Sends to <span class="mono" style="color:var(--ink2)">' + esc(prefix) + '/alert</span> when a watched species shows up. Each species has its own confidence bar and cooldown.</p></div>' +
      sw('s-alerts', a.enabled, 'Species alerts') + '</div>' +
      '<div style="padding:0 24px;display:flex;flex-direction:column;gap:12px"><div class="subtle"><span class="label">Also alert on</span>' +
      '<label class="chk">' + sw('s-new', a.new_species, 'Never seen before') + 'Any species never seen before (life-list first)</label>' +
      '<label class="chk" style="flex-wrap:wrap">' + sw('s-ret', a.returning, 'Returning species') + 'Any species back after ' +
      select('s-ret-days', a.returning_days, [[14, '14 days'], [30, '30 days'], [60, '60 days'], [90, '90 days'], [180, '180 days']], ' style="min-height:36px"') + ' away</label></div>' +
      '<form id="w-add" class="inline" style="align-items:flex-end" aria-label="Add species to alert list">' +
      '<label class="lf ac" style="flex:2 1 260px"><span class="label">Add species</span><input class="field" id="w-name" type="search" placeholder="Start typing a bird name…" autocomplete="off"></label>' +
      '<label class="lf" style="flex:1 1 120px"><span class="label">Min. confidence</span>' + select('w-min', 0.8, CONF_OPTS) + '</label>' +
      '<label class="lf" style="flex:1 1 120px"><span class="label">Cooldown</span>' + select('w-cool', 15, COOL_OPTS) + '</label>' +
      '<button class="btn primary" type="submit" id="w-add-btn" disabled>Add</button></form></div>' +
      (watch.length ? '<div class="scroll" style="margin-top:8px"><table class="tbl"><thead><tr><th scope="col">Species</th><th scope="col">Min. confidence</th><th scope="col">Cooldown</th><th scope="col">Last alert</th><th scope="col">On</th><th scope="col"><span class="vh">Remove</span></th></tr></thead><tbody>' +
        watch.map(function (w, i) {
          return '<tr data-w="' + i + '"><td><a href="' + speciesHref(w.scientific_name) + '" style="font-weight:500">' + esc(w.common_name) + '</a><div class="muted" style="font-size:12px;margin-top:2px">' +
            (w.seen ? 'seen ' + num(w.seen) + '×' : 'not seen yet') + '</div></td>' +
            '<td>' + select('w-min-' + i, w.min_score, CONF_OPTS, ' data-wf="min_score" style="min-height:36px" aria-label="Minimum confidence for ' + esc(w.common_name) + '"') + '</td>' +
            '<td>' + select('w-cool-' + i, w.cooldown_min, COOL_OPTS, ' data-wf="cooldown_min" style="min-height:36px" aria-label="Cooldown for ' + esc(w.common_name) + '"') + '</td>' +
            '<td class="muted">' + (w.last_alert ? esc(fmtShort(w.last_alert)) : 'Never') + '</td>' +
            '<td>' + sw('w-on-' + i, w.enabled, 'Alerts for ' + w.common_name, ' data-wf="enabled"') + '</td>' +
            '<td><button class="btn icon" type="button" data-wdel="' + i + '" aria-label="Remove ' + esc(w.common_name) + '">' + ICON.x + '</button></td></tr>';
        }).join('') + '</tbody></table></div>' : '<p class="muted" style="padding:8px 24px 14px;margin:0">No species on your alert list yet. Add one above, or use “Add to alerts” on any species page.</p>') + '</section>';

    var q = st.quiet;
    var quiet = '<section class="card pad stack"><div class="toggle-head"><div><h2>Quiet hours</h2><p class="sub">Hold species alerts overnight. Detections still log and still publish to the detection topic.</p></div>' +
      sw('s-quiet', q.enabled, 'Quiet hours') + '</div><div class="inline">' +
      '<label class="inline">From <input class="field" type="time" id="s-q-start" value="' + esc(q.start) + '"></label>' +
      '<label class="inline">to <input class="field" type="time" id="s-q-end" value="' + esc(q.end) + '"></label>' +
      '<label class="chk"><input type="checkbox" id="s-q-new"' + (q.allow_new_species ? ' checked' : '') + '> Except life-list firsts</label></div></section>';

    var payload = JSON.stringify({
      common_name: 'Dark-eyed Junco', scientific_name: 'Junco hyemalis', confidence: 0.89, camera: (status.cameras[0] || 'birdcam'),
      time: '2026-10-08T09:47:12', frigate_event: '1791473232.4-abc123',
      snapshot_url: st.snapshots.base_url ? st.snapshots.base_url.replace(/\/$/, '') + '/snap/1791473232.4-abc123.jpg' : null,
      first_ever: false, first_of_season: true, flagged: false, reason: 'watchlist,returning'
    }, null, 2);
    var yaml = [
      'alias: Bird at the feeder',
      'triggers:',
      '  - trigger: mqtt',
      '    topic: ' + prefix + '/alert',
      'actions:',
      '  - action: notify.mobile_app_YOUR_PHONE',
      '    data:',
      '      title: "{{ trigger.payload_json.common_name }} at the feeder"',
      '      message: >-',
      '        {{ (trigger.payload_json.confidence * 100) | round }}% confident',
      '        ({{ trigger.payload_json.reason }})',
      '      data:',
      '        image: /api/camera_proxy/camera.whosatmyfeeder_last_bird_snapshot'
    ].join('\n');
    routes.settings.snippets = { payload: payload, yaml: yaml };
    var sent = '<section class="card pad stack"><div class="sec-head"><h2>What gets sent</h2><div style="display:flex;gap:8px;flex-wrap:wrap">' +
      '<button class="btn" type="button" data-copy="payload">Copy payload</button><button class="btn" type="button" data-copy="yaml">Copy HA automation</button></div></div>' +
      '<p class="sub" style="margin:0">An example alert, and a Home Assistant automation that turns it into a phone notification with the picture. ' +
      (st.mqtt.discovery ? 'The picture comes from the “Last bird snapshot” camera that discovery creates, so it works away from home too.' : 'Turn on discovery above to get the “Last bird snapshot” camera this automation uses.') + '</p>' +
      '<div style="display:flex;flex-wrap:wrap;gap:14px"><pre class="code">// ' + esc(prefix) + '/alert\n' + esc(payload) + '</pre><pre class="code">' + esc(yaml) + '</pre></div></section>';

    var log = recent.length ? '<section class="card pad stack"><h2>Recent alerts</h2><ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px;font-size:14px">' +
      recent.map(function (x) { return '<li style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><span>' + esc(x.common_name) + ' <span class="muted">(' + esc(x.reason.replace(/_/g, ' ').replace(/,/g, ', ')) + ')</span></span><span class="mono muted">' + esc(fmtShort(x.sent_at)) + '</span></li>'; }).join('') +
      '</ul></section>' : '';
    return conn + all + alerts + quiet + sent + log;
  }

  function settingsDetection(st, res) {
    var d = st.detection;
    var hidden = res[3].filter(function (s) { return s.hidden; });
    return '<section class="card pad stack"><div><h2>Detection threshold</h2><p class="sub">Classifications below this confidence are ignored. Individual species can override it from their page.</p></div>' +
      '<label class="inline">Minimum confidence ' + select('d-thr', d.threshold == null ? '' : d.threshold, [['', 'From config.yml (' + pct(status.config_threshold) + ')']].concat(CONF_OPTS)) + '</label></section>' +
      '<section class="card pad stack"><div><h2>Needs-review flag</h2><p class="sub">Flagged detections get Keep / Not a bird buttons on Today and can be filtered in History. Flagging never blocks alerts; the payload carries <span class="mono">"flagged": true</span>.</p></div>' +
      '<label class="inline">Flag detections below ' + select('d-review', d.review_below == null ? '' : d.review_below, [['', 'Never']].concat(CONF_OPTS)) + '</label>' +
      '<label class="chk">' + sw('d-first', d.flag_first_sighting, 'Flag first sightings') + 'Flag the first-ever sighting of a species</label></section>' +
      '<section class="card pad stack"><div><h2>Grouping visits</h2><p class="sub">Back-to-back detections of the same species are shown as one visit on Today.</p></div>' +
      '<label class="inline">Group detections within ' + select('d-group', st.ui.group_minutes, [[0, 'Don’t group'], [5, '5 minutes'], [10, '10 minutes'], [20, '20 minutes'], [30, '30 minutes']]) + '</label></section>' +
      '<section class="card pad stack"><div><h2>Hidden species</h2><p class="sub">New detections of hidden species are ignored and old ones are left out of stats.</p></div>' +
      (hidden.length ? '<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px">' + hidden.map(function (s, i) {
        return '<li style="display:flex;justify-content:space-between;align-items:center;gap:10px"><a href="' + speciesHref(s.scientific_name) + '" style="color:var(--ink)">' + esc(s.common_name) + '</a>' +
          '<button class="btn" type="button" data-unhide="' + i + '">Unhide</button></li>';
      }).join('') + '</ul>' : '<p class="muted" style="margin:0">None. Use “Hide species” on a species page for things like a heron your feeder keeps turning into.</p>') + '</section>';
  }

  function fmtBytes(b) {
    if (b < 1024 * 1024) return Math.round(b / 1024) + ' KB';
    if (b < 1024 * 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + ' MB';
    return (b / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  function settingsStorage(st) {
    return '<section class="card pad stack"><div class="toggle-head"><div><h2>Keep snapshots</h2><p class="sub">Save a copy of each bird’s pictures when it’s detected, so they outlive Frigate’s retention.</p></div>' +
      sw('st-cache', st.snapshots.cache, 'Keep snapshots') + '</div>' +
      '<p class="mono muted" style="margin:0">' + num(status.cache.files) + ' files · ' + fmtBytes(status.cache.bytes) + '</p></section>' +
      '<section class="card pad stack"><div><h2>External address</h2><p class="sub">Optional. If this app is reachable at a URL, it goes in MQTT payloads as <span class="mono">snapshot_url</span>. Not needed for the Home Assistant camera entity.</p></div>' +
      '<label class="lf"><span class="label">Base URL</span><input class="field mono" id="st-base" placeholder="http://192.168.1.10:7766" value="' + esc(st.snapshots.base_url) + '"></label></section>' +
      '<section class="card pad stack"><div><h2>Move or back up your data</h2><p class="sub">Download the detection database, or import history from another install. You can upload a <span class="mono">speciesid.db</span> file, or a Home Assistant backup of the original WhosAtMyFeeder add-on (the <span class="mono">.tar</span> file, unencrypted). Imports merge; nothing already here is overwritten.</p></div>' +
      '<div class="inline"><a class="btn" href="api/export.db" download>' + ICON.down + 'Download database</a>' +
      '<label class="btn" style="cursor:pointer">Import database or backup…<input type="file" id="st-import" accept=".db,.sqlite,.tar,.tgz,.gz,application/octet-stream,application/x-tar" class="vh"></label>' +
      '<span id="st-import-msg"></span></div></section>';
  }

  function settingsAbout() {
    return '<section class="card pad stack"><h2>Who’s At My Feeder ' + esc(status.version) + '</h2>' +
      '<table class="tbl"><tbody>' +
      [['Frigate', status.frigate_url], ['MQTT broker', status.broker], ['Cameras', status.cameras.join(', ')],
        ['Detection threshold', pct(status.threshold)], ['First detection', status.earliest_date ? fmtDay(status.earliest_date, { month: 'long', day: 'numeric', year: 'numeric' }) : '—'],
        ['Last detection', status.last_detection ? status.last_detection.common_name + ', ' + fmtShort(status.last_detection.time) : '—']].map(function (r) {
        return '<tr><th scope="row" style="width:220px">' + esc(r[0]) + '</th><td class="mono">' + esc(r[1]) + '</td></tr>';
      }).join('') + '</tbody></table>' +
      '<p class="sub" style="margin:0">Bird classification uses the Google AIY birds V1 model. Based on <a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener">mmcc-xx/WhosAtMyFeeder</a>. Fonts: IBM Plex and Bricolage Grotesque (SIL OFL).</p></section>';
  }

  routes.settings.after = function (r) {
    var section = r.arg || 'notifications';
    var stt = routes.settings.state;
    function save(patch, quiet) {
      return api('settings', { method: 'PUT', body: patch }).then(function (s) { stt.settings = s; if (!quiet) toast('Saved'); return s; }).catch(fail);
    }
    function onSwitch(id, fn) {
      var el = document.getElementById(id); if (!el) return;
      el.addEventListener('click', function () {
        var v = el.getAttribute('aria-checked') !== 'true';
        el.setAttribute('aria-checked', String(v));
        fn(v);
      });
    }
    function onChange(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener('change', function () { fn(el); }); }
    function numOrNull(v) { return v === '' ? null : +v; }

    if (section === 'notifications') {
      onChange('s-prefix', function (el) { save({ mqtt: { topic_prefix: el.value } }).then(function () { render(true); }); });
      onSwitch('s-discovery', function (v) { save({ mqtt: { discovery: v } }).then(function () { render(true); }); });
      onSwitch('s-legacy', function (v) { save({ mqtt: { legacy_topic: v } }); });
      onSwitch('s-pa', function (v) { save({ publish_all: { enabled: v } }).then(function () { render(true); }); });
      onChange('s-pa-min', function (el) { save({ publish_all: { min_score: numOrNull(el.value) } }); });
      onChange('s-pa-skip', function (el) { save({ publish_all: { skip_flagged: el.checked } }); });
      onSwitch('s-alerts', function (v) { save({ alerts: { enabled: v } }); });
      onSwitch('s-new', function (v) { save({ alerts: { new_species: v } }); });
      onSwitch('s-ret', function (v) { save({ alerts: { returning: v } }); });
      onChange('s-ret-days', function (el) { save({ alerts: { returning_days: +el.value } }); });
      onSwitch('s-quiet', function (v) { save({ quiet: { enabled: v } }); });
      onChange('s-q-start', function (el) { if (el.value) save({ quiet: { start: el.value } }); });
      onChange('s-q-end', function (el) { if (el.value) save({ quiet: { end: el.value } }); });
      onChange('s-q-new', function (el) { save({ quiet: { allow_new_species: el.checked } }); });
      var test = document.getElementById('s-test');
      test.addEventListener('click', function () {
        var msg = document.getElementById('s-test-msg');
        test.disabled = true; msg.className = 'muted'; msg.textContent = 'Sending…';
        api('mqtt/test', { method: 'POST', body: {} }).then(function (res) {
          msg.className = 'okmsg'; msg.textContent = res.message + ' · acknowledged by the broker';
        }).catch(function (e) { msg.className = 'errmsg'; msg.textContent = e.message; }).then(function () { test.disabled = false; });
      });
      // watchlist add
      var chosen = null, nameI = document.getElementById('w-name'), addBtn = document.getElementById('w-add-btn');
      attachAutocomplete(nameI, function (it) { chosen = it; nameI.value = it.common_name; addBtn.disabled = false; });
      nameI.addEventListener('input', function () { chosen = null; addBtn.disabled = true; });
      document.getElementById('w-add').addEventListener('submit', function (e) {
        e.preventDefault(); if (!chosen) return;
        api('watchlist', { method: 'POST', body: { scientific_name: chosen.scientific_name, min_score: +document.getElementById('w-min').value, cooldown_min: +document.getElementById('w-cool').value } })
          .then(function () { toast(chosen.common_name + ' added'); render(true); }).catch(fail);
      });
      // watchlist edits
      document.querySelectorAll('tr[data-w]').forEach(function (tr) {
        var w = stt.watch[+tr.dataset.w];
        var path = 'watchlist/' + enc(w.scientific_name);
        tr.querySelectorAll('select[data-wf]').forEach(function (s) {
          s.addEventListener('change', function () { var b = {}; b[s.dataset.wf] = +s.value; api(path, { method: 'PUT', body: b }).then(function () { toast('Saved'); }).catch(fail); });
        });
        var t = tr.querySelector('.sw[data-wf]');
        t.addEventListener('click', function () {
          var v = t.getAttribute('aria-checked') !== 'true'; t.setAttribute('aria-checked', String(v));
          api(path, { method: 'PUT', body: { enabled: v } }).then(function () { toast(v ? 'Alerts on' : 'Alerts paused'); }).catch(fail);
        });
        tr.querySelector('[data-wdel]').addEventListener('click', function () {
          api(path, { method: 'DELETE' }).then(function () { toast('Removed ' + w.common_name); render(true); }).catch(fail);
        });
      });
      document.querySelectorAll('[data-copy]').forEach(function (b) {
        b.addEventListener('click', function () {
          var text = routes.settings.snippets[b.dataset.copy];
          (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { toast('Copied'); }, function () {
            var ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); toast('Copied'); } catch (e) { toast('Copy failed'); }
            ta.remove();
          });
        });
      });
    }
    if (section === 'detection') {
      onChange('d-thr', function (el) { save({ detection: { threshold: numOrNull(el.value) } }).then(loadStatus); });
      onChange('d-review', function (el) { save({ detection: { review_below: numOrNull(el.value) } }); });
      onSwitch('d-first', function (v) { save({ detection: { flag_first_sighting: v } }); });
      onChange('d-group', function (el) { save({ ui: { group_minutes: +el.value } }); });
      var hidden = stt.species.filter(function (s) { return s.hidden; });
      document.querySelectorAll('[data-unhide]').forEach(function (b) {
        b.addEventListener('click', function () {
          var s = hidden[+b.dataset.unhide];
          api('species/' + enc(s.scientific_name) + '/prefs', { method: 'PUT', body: { hidden: false, min_score: null } })
            .then(function () { toast('Unhid ' + s.common_name); render(true); }).catch(fail);
        });
      });
    }
    if (section === 'storage') {
      onSwitch('st-cache', function (v) { save({ snapshots: { cache: v } }); });
      onChange('st-base', function (el) { save({ snapshots: { base_url: el.value.trim() } }); });
      var imp = document.getElementById('st-import');
      imp.addEventListener('change', function () {
        var f = imp.files[0]; if (!f) return;
        var msg = document.getElementById('st-import-msg');
        msg.className = 'muted'; msg.textContent = 'Importing ' + f.name + '…';
        var fd = new FormData(); fd.append('file', f);
        fetch('api/import', { method: 'POST', body: fd, headers: { 'X-Requested-With': 'wamf' } })
          .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Import failed'); return d; }); })
          .then(function (d) { msg.className = 'okmsg'; msg.textContent = 'Imported ' + num(d.imported) + ' detections.'; loadStatus(); })
          .catch(function (e) { msg.className = 'errmsg'; msg.textContent = e.message; });
      });
    }
  };

  /* ------------------------------------------------------------------ go */

  loadStatus().then(function () { render(); });
})();
