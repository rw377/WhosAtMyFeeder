# Changelog

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
