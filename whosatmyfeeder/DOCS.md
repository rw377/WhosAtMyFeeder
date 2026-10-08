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

If you used the WhosAtMyFeeder add-on from
[bertybuttface/addons](https://github.com/bertybuttface/addons), your history is in
`/data/speciesid.db` inside that add-on's container. The database format is the
same, so it imports directly:

1. Open a shell with the **Advanced SSH & Web Terminal** add-on (protection mode
   off) and copy the database somewhere you can reach:
   `docker cp addon_932a64e5_whosatmyfeeder:/data/speciesid.db /share/speciesid.db`
   (`932a64e5_whosatmyfeeder` is the old add-on's slug; its Info page shows it as
   the hostname with a dash instead of the underscore).
2. Download `/share/speciesid.db` with the Samba share or File editor add-on.
3. In this app, go to **Settings → Snapshots & data → Import database**.

Option names map across like this: `frigate.frigate_url` → `frigate_url`,
`frigate.camera` → `cameras`, `frigate.main_topic` → `frigate_topic`,
`classification.threshold` → `threshold`. The MQTT settings can stay empty if you
use the Mosquitto add-on; otherwise copy `mqtt_server`, `mqtt_username` and
`mqtt_password` over.

Imports merge, so you can run the old and new add-ons side by side for a while and
import again before switching the old one off. Pictures for old detections are
pulled from Frigate the first time they're viewed, for as long as Frigate still
has them.
