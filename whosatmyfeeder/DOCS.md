# Who's At My Feeder

Identifies the bird species that Frigate or Blue Iris detects, and gives you a
searchable history, per-species pages, stats, and MQTT alerts for the birds you care about.

## Requirements

- Either **Frigate**, with a camera that detects the `bird` object and has
  snapshots enabled, or **Blue Iris** with CodeProject.AI confirming `bird` and an
  MQTT alert action (see [Using Blue Iris](#using-blue-iris-instead-of-frigate)).
- An MQTT broker that Frigate or Blue Iris publishes to. If you run the
  **Mosquitto broker** add-on, this add-on finds it automatically.

## Configuration

| Option | What it does |
| --- | --- |
| `source` | `frigate` (default) or `blueiris`. |
| `frigate_url` | Where Frigate's API is. For the Frigate add-on this is usually `http://ccab4aaf-frigate:5000`. Optional with Blue Iris (see below). |
| `cameras` | Camera names to watch for birds: Frigate camera names, or Blue Iris camera short names, spelled exactly (case-sensitive). Can also be picked in the app under **Settings → Cameras**, which overrides this option. |
| `frigate_topic` | Frigate's MQTT topic prefix (default `frigate`). |
| `bi_url` | Blue Iris web server, e.g. `http://192.168.1.20:81`. Needed with `source: blueiris`. |
| `bi_username`, `bi_password` | A Blue Iris user that can view the bird camera. |
| `bi_topic` | Topic the Blue Iris alert action publishes to (default `BlueIris/+/alert`). |
| `threshold` | Minimum classifier confidence to record a detection. Can be overridden in the app. |
| `mqtt_server`, `mqtt_port`, `mqtt_username`, `mqtt_password` | Only needed if you don't use the Mosquitto add-on. |

Open the app from the sidebar (**Feeder**). Click the camera status in the top right for a live view. Everything else (alerts, quiet hours,
review flags, hidden species) is set in the app under **Settings**.

## Using Blue Iris instead of Frigate

Set `source: blueiris` and the app takes bird alerts from Blue Iris (confirmed by
CodeProject.AI) over MQTT instead of Frigate events.

**In Blue Iris**, on the bird camera:

1. **Camera settings → Trigger → AI**: CodeProject.AI on, `bird` in the objects to
   confirm, and analyse the **main stream** (so the bird box is in main-stream pixels).
2. **Alerts → On alert → Add → Web request or MQTT**, MQTT topic
   `BlueIris/&CAM/alert` and payload:

   ```
   {"id":"&ALERT_DB","camera":"&CAM","detections":&JSON}
   ```

   Don't tick "retain". No "On reset" action is needed.
3. **Settings → MQTT**: point Blue Iris at the same broker as this add-on.
4. A Blue Iris user for this add-on that can view the camera (a limited user is
   fine). The add-on logs in through Blue Iris's JSON API, falling back to HTTP Basic.

**In the add-on**: `source: blueiris`, `bi_url` (e.g. `http://192.168.1.20:81`),
`bi_username`, `bi_password`, and `cameras` set to the Blue Iris camera short name,
exactly as Blue Iris spells it (it's case-sensitive: `BirdFeeder` is not `birdfeeder`).

How each alert is handled:

- Test alerts (id `@-1`) and alerts without a `bird` prediction are skipped.
- The most confident `bird` box across all of CodeProject.AI's results is used.
- The full alert image (`/alerts/<id>?fulljpeg`) is downloaded. If it isn't the
  camera's main-stream size, the box is scaled to fit; then it's clamped, padded by
  about 12%, and the bird is cropped out. The classifier shrinks its input to
  224×224, so classifying the whole frame would leave the bird a few pixels big.
- The detection time is CodeProject.AI's `timestampUTC`, converted to local time
  (or the time the message arrived, if that's missing).
- Event ids are stored as `bi-<alert id>` (e.g. `bi-406413738801416`).
- Pictures are always cached by the app, since Blue Iris alert images can't be
  fetched by event id later. There are no clips, and no sub labels are written back.
- Blue Iris has no "end" message. **Bird present** turns on with each alert and off
  5 minutes after the last one; with Blue Iris it tracks one bird per camera.
- Each alert is its own detection, so a long visit can give several rows (grouped
  into one visit on Today). Alerts still follow the new-species, returning and
  watchlist cooldown rules.

The add-on log prints the alert image size, the camera's main-stream size and the
first bird box it sees, which is the quickest way to check the crop is right.

### Switching an existing install from Frigate

1. While Frigate is still running, open **Settings → Snapshots & data** and make
   sure **Keep snapshots** is on, then click **Copy pictures from Frigate**. This
   saves Frigate's snapshots for every past detection that isn't cached yet.
2. Set `source: blueiris` and the Blue Iris options, and restart the add-on.
   History, stats and settings carry over; nothing in the database changes.
3. Remove Frigate, then clear `frigate_url`. Until you clear it the app still asks
   Frigate for any old picture that wasn't cached (and backs off for 5 minutes when
   Frigate doesn't answer).

Old clip links stop working once Frigate is gone; snapshots stay.

## Alerts in Home Assistant

With **Home Assistant discovery** on (the default), the add-on creates a device
with these entities:

| Entity | What it shows |
| --- | --- |
| `sensor.whosatmyfeeder_current_bird` (**Bird at feeder**) | The species at the feeder right now; `Unknown bird` when a bird is there but hasn't been identified; `No bird` when the feeder is empty. The `status` attribute is `identified`, `unidentified` or `none`. |
| `binary_sensor.whosatmyfeeder_bird_present` (**Bird present**) | On while any bird is at the feeder. |
| `sensor.whosatmyfeeder_last_bird` (**Last bird**) | The most recent species identified; keeps its value after the bird leaves. |
| `camera.whosatmyfeeder_last_bird_snapshot` | Picture of the most recent bird. |
| `binary_sensor.whosatmyfeeder_online` | Whether the add-on is connected. |

"Right now" follows Frigate's tracking: a bird is present from Frigate's first
event for it until its "end" event (or 5 minutes without updates). With Blue Iris,
from an alert until 5 minutes after the camera's last alert. Species alerts arrive on `whosatmyfeeder/alert`. Settings → Notifications
has a copy-ready automation that sends a phone notification with the picture.

## Moving over from the original add-on

If you used the WhosAtMyFeeder add-on from
[bertybuttface/addons](https://github.com/bertybuttface/addons), your history is in
`/data/speciesid.db` inside that add-on's container. The database format is the
same, so it imports directly:

1. In Home Assistant, go to **Settings → System → Backups** and make a backup
   that includes only the old **WhosAtMyFeeder add-on** (no need for the rest of
   Home Assistant).
2. Download that backup to your computer from the same page. Home Assistant
   decrypts it as it downloads, so you get a plain `.tar` file.
3. In this app, go to **Settings → Snapshots & data → Import database or backup**
   and pick that `.tar` file. The app finds `speciesid.db` inside it.

A bare `speciesid.db` file works too, if you've copied one out some other way.

Option names map across like this: `frigate.frigate_url` → `frigate_url`,
`frigate.camera` → `cameras`, `frigate.main_topic` → `frigate_topic`,
`classification.threshold` → `threshold`. The MQTT settings can stay empty if you
use the Mosquitto add-on; otherwise copy `mqtt_server`, `mqtt_username` and
`mqtt_password` over.

Imports merge, so you can run the old and new add-ons side by side for a while and
import again before switching the old one off. Pictures for old detections are
pulled from Frigate the first time they're viewed, for as long as Frigate still
has them.
