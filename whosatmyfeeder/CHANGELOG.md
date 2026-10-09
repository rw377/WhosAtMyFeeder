# Changelog

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
