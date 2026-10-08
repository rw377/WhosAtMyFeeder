# Who's At My Feeder

Identifies the bird species that Frigate detects, and gives you a searchable
history, per-species pages, stats, and MQTT alerts for the birds you care about.

## Requirements

- Frigate, with a camera that detects the `bird` object and has snapshots enabled.
- An MQTT broker that Frigate publishes to. If you run the **Mosquitto broker**
  add-on, this add-on finds it automatically.

## Configuration

| Option | What it does |
| --- | --- |
| `frigate_url` | Where Frigate's API is. For the Frigate add-on this is usually `http://ccab4aaf-frigate:5000`. |
| `cameras` | Frigate camera names to watch for birds. |
| `frigate_topic` | Frigate's MQTT topic prefix (default `frigate`). |
| `threshold` | Minimum classifier confidence to record a detection. Can be overridden in the app. |
| `mqtt_server`, `mqtt_port`, `mqtt_username`, `mqtt_password` | Only needed if you don't use the Mosquitto add-on. |

Open the app from the sidebar (**Feeder**). Everything else (alerts, quiet hours,
review flags, hidden species) is set in the app under **Settings**.

## Alerts in Home Assistant

With **Home Assistant discovery** on (the default), the add-on creates a device
with a **Last bird** sensor, a **Last bird snapshot** camera and an **Online**
sensor. Species alerts arrive on `whosatmyfeeder/alert`. Settings → Notifications
has a copy-ready automation that sends a phone notification with the picture.

## Moving over from the original add-on

The original add-on keeps its database inside its own container. To bring your
history across:

1. With the SSH add-on (protection mode off), copy the database out:
   `docker cp addon_932a64e5_whosatmyfeeder:/data/speciesid.db /share/speciesid.db`
   (the database is normally at `/data/speciesid.db` inside the old container;
   use your old add-on's slug, shown on its Info page as the hostname).
2. Download `/share/speciesid.db` with the Samba add-on or File editor.
3. In this app, go to **Settings → Snapshots & data → Import database**.

Imports merge, so it's safe to run the old and new add-ons side by side for a
while and import again later. Pictures for old detections are pulled from
Frigate the first time they're viewed, for as long as Frigate still has them.
