# Changelog

## 2.3.1

- `frigate_topic` is now optional, so the configuration saves with
  `source: blueiris` and no Frigate options. It still defaults to `frigate`.

## 2.3.0

- **Blue Iris as an event source.** New `source` option (`frigate` or `blueiris`)
  plus `bi_url`, `bi_username`, `bi_password` and `bi_topic`. With Blue Iris, the
  app listens for the alert action's MQTT message, downloads the full alert image,
  crops out the most confident CodeProject.AI `bird` box (scaled if the image isn't
  main-stream size, padded ~12%), and classifies the crop. Test alerts (`@-1`) and
  alerts without a bird are skipped; the detection time comes from
  `timestampUTC`. See the Documentation tab for the Blue Iris setup.
- With Blue Iris, pictures are always cached, clips and Frigate sub labels are off,
  Settings → Cameras lists the configured cameras, the live view uses Blue Iris,
  and "Open Blue Iris" replaces "Open Frigate". **Bird present** follows Blue Iris
  alerts and clears 5 minutes after the last one.
- **Settings → Snapshots & data → Copy pictures from Frigate** caches Frigate's
  snapshots for every past detection, so history keeps its pictures after Frigate
  is removed. Clips aren't copied.
- `frigate_url` is now optional, and the app stops asking an unreachable Frigate
  for 5 minutes instead of on every thumbnail.
- The default camera list is now `BirdFeeder`. Existing installs keep their own
  `cameras` setting.
- No database changes: Blue Iris event ids are stored as `bi-<alert id>` in the
  existing column.

## 2.2.1

- **Bird at feeder** now reads `No bird` when the feeder is empty. It sent
  `None`, which Home Assistant treats as "no value" and showed as Unknown, so an
  empty feeder looked the same as an unidentified bird (`Unknown bird`).
- New `status` attribute: `none`, `unidentified` or `identified`, for automations.

## 2.2.0

- New Home Assistant entities (via MQTT discovery) for what's at the feeder
  right now: **Bird at feeder** (species name, or "None") and **Bird present**
  (occupancy on/off). They follow Frigate's tracking: a bird counts as present
  from its first event until Frigate's "end" event, or 5 minutes without news.
  Attributes include confidence, camera, arrival time, how many birds are being
  tracked, and every species currently identified.
- Published on `whosatmyfeeder/current` (retained JSON).

## 2.1.1

- Fix: after an update, browsers could keep running the previous version's
  app.js/app.css from cache for up to an hour, so new features (the Cameras
  page, the live view) didn't appear. Asset URLs now change with every release
  and the page itself is never cached.

## 2.1.0

- **Settings → Cameras**: lists every camera Frigate has, with a live thumbnail,
  whether it tracks birds and has snapshots on, and detection counts. Tick the
  ones to watch; this overrides the add-on's `cameras` option and applies
  without a restart.
- **Live view**: click the camera status in the top right (or "Live view" on the
  Cameras page) for a live picture from Frigate, refreshed every second, with a
  camera switcher and an "Open Frigate" button.
- Help text for every option on the add-on's Configuration tab.
- The skipped-camera warning clears once that camera is being watched.

## 2.0.5

- Bird events from a camera that isn't in the `cameras` option are no longer
  dropped silently: the log names the camera, and the app shows a banner saying
  which camera to add. The startup log lists the cameras being watched.

## 2.0.4

- Species page: "When it visits" and "Often seen with" now cover the year up to
  the species' last visit instead of the last 90 days, so birds not seen lately
  aren't blank.
- "Often seen with" uses the time index (was a full pairwise scan) and says
  how many visits it's based on.

## 2.0.3

- Species pictures: use the best detection that still has a picture (cached
  here or still in Frigate) instead of the best-scoring one overall, which is
  often long gone from Frigate.
- Remember events Frigate has purged, so pages don't re-request them from
  Frigate on every view.

## 2.0.2

- Fix startup crash: install libusb, which tflite_support loads at import
  ("libusb-1.0.so.0: cannot open shared object file").
- Import accepts a Home Assistant backup of the original add-on (the .tar from
  Settings → System → Backups), so moving your history over needs no terminal.

## 2.0.1

- Fix add-on install: the Supervisor rejected the base image in build.yaml and
  fell back to its Alpine image (no apt-get). build.yaml is removed and the
  Dockerfile now names its Debian Python 3.8 base directly.

## 2.0.0

- New web UI: Today dashboard, searchable history, species pages, stats, settings.
- MQTT alerts: watchlist with per-species confidence and cooldown, life-list
  firsts, returning species, quiet hours, optional publish-every-detection.
- Home Assistant MQTT discovery: Last bird sensor, snapshot camera, online sensor.
- Snapshots are cached locally so pictures outlive Frigate's retention.
- Review flags for low-confidence and first-time detections; fix IDs, delete,
  hide species, per-species thresholds.
- Database import/export and CSV export.
- Fixes: daily summary sorted by busiest hour instead of total; date-range page
  returning an error; one database connection per name lookup.
- Runs as a Home Assistant add-on with ingress.
