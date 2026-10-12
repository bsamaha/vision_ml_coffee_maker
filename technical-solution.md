# Run sheet

Hardware is in [hardware.md](hardware.md). The case is in [business-case.md](business-case.md). Publish a code change with the steps in [README.md](README.md).

This is a proof on the Ninja, not a small copy of the well. A brew here empties the reservoir. On a pad the pump does not. The page shows booked ounces, ounces used in the last 15 minutes and today, the use rate over the last 2 minutes with a time to empty, person visits, refills, a coffee bill, and a refill alarm. There is no weekly rate.

## What is already true

The camera stays where it is. It looks at the graduated face from a little above the reservoir, with the whole machine in the frame. On 9 October 2026 a fill of about 75% showed as a bright horizontal band. The cup marks above that band were readable. Do not zoom. This webcam has no zoom, and a crop missed the tank.

The camera body is upside down. There is no flip control on the device. Every still and the live page use `hflip,vflip`. The process on port 8080 is `check/board.py`, started by `scripts/pi-receive`. It owns `/dev/video0`. Open [http://192.168.1.248:8080](http://192.168.1.248:8080). The earlier pages are in `archive/check/`. Do not start one of them while the board is up.

The person model is the COCO RF-DETR Nano. The tank model is the fine-tuned RF-DETR Nano, with classes `Reservoir` and `liquid-level`. Both run on the Pi's CPU. On 9 October one 1280×720 person pass took about 4.4 seconds while `ffmpeg` was flipping and encoding 60 frames a second. On 11 October, with the board's `ffmpeg` thinned to 2 frames a second, each pass takes about 1.85 seconds. Ounces come from `check/volume.py`. The live page rules are in section 6.

Used, last 15 min and Used today at 0.0 fl oz are normal. The refill alarm is under 17.5 fl oz. Accuracy is only figured on readings at or above 25%.

## Traps

- Training stills are 1280×720 MJPEG with the same `hflip,vflip` as the preview. Another size or an unflipped frame is a different picture from the one we checked.
- Stop the process that owns `/dev/video0` before opening it from anything else. Right now that process is `check/board.py`. Two opens fight over the camera.
- `power_line_frequency=2` is 60 Hz. Value 1 is 50 Hz.
- Manual exposure is `auto_exposure=1`, then `exposure_time_absolute`. Switching to manual without the absolute value blacks the frame. `auto_exposure=3` is the current Aperture Priority mode. A bright morning clips that automatic picture. Lock then looks for a usable exposure instead of copying the white frame. Darker and Brighter on the capture page change the shutter and keep the same focus. Set that once, then leave it for the rest of the 24 stills.
- Lock focus only after this aim is final: `focus_automatic_continuous=0`, then `focus_absolute` at the settled value. Set those again if a new capture process opens the camera. They do not always stick.
- A Classic brew uses whatever is in the reservoir and empties it. The refill alarm will come on partway through a normal brew and stay on until someone pours. That is the alarm demo. It is not a fault in the page.
- Set WARM to 0 and wait until the machine is off before pouring. With the plate on, water added to the reservoir starts another brew, so the pour and the pump run together.
- 1-4 CUP does not stop at 4 cups. Leave it off.
- The carafe is seated and empty before a brew. If it is missing or already full, the basket overflows.
- The brew pauses at the start, then continues. During that pause both Used tiles can stay 0. That is not the alarm.
- Do not stand between the camera and the reservoir for more than about 15 seconds. Two ticks with the reservoir hidden and a person in view read as a take, then a put-back once you step away. The level is not changed, but two extra lines land in the log.
- A visit is the person class only. A chair box is not a visit. Section 6 is the live person rule. This list does not define a fill.
- Do not read the line while a person covers the reservoir. Section 6 stores that gauge and leaves the booked ounces alone.
- A rise with nobody in frame is not a refill and not a bill. Section 6 updates the level only after the quiet-jump hold, and it does not book 70.
- Label `liquid` up to the top of the bright band. Vertical reflections in the water and the printed cup numbers are not the line.
- Under 25% is photographed so the alarm has examples. Those frames are not part of the accuracy average.

## 1. Lock the camera

Do this once, before the stills you keep. The aim does not change after it.

The page walks one step at a time.

1. Empty the reservoir, seat the carafe, and turn the machine off. Stand clear. When the reservoir looks sharp, press Lock this picture. The page reads `focus_absolute`, then tries manual exposures. If the automatic picture is clipped white, it looks for a shorter exposure that keeps the tank visible. Otherwise it matches the automatic brightness. The control's idle reading is 166. Writing 166 makes the picture dark, so the page does not use that reading. If the match is still dark, it leaves the camera on automatic and stays on this step.
2. Look again. Press Keep this lock, or Try again. Try again deletes the lock and returns to step 1.

```
focus_absolute=<settled value>
exposure_time_absolute=<settled value>
accepted=1
```

`check/capture.py` applies `power_line_frequency=2`, manual focus, that focus value, `auto_exposure=1`, then the matched `exposure_time_absolute`, every time it opens the camera. A press that fails is printed in `/tmp/preview.log` and on the page.

## 2. Capture

Open http://raspberrypi.local:8080. That page is `check/capture.py`. It shows the clean camera and does not draw boxes.

After the lock is kept, the page names one stop at a time. Stand where the camera cannot see you, then press Save this picture. That press writes one file and names the next stop. A second tap while the first press is still working does not write another file. A Ninja cup is 5 fl oz. 14 MAX is 70 fl oz. Fills under 17.5 fl oz, which is under 25%, say alarm.

The shoot is 18 pictures. The carafe can be full or empty. Only the reservoir is in the picture. Four turns, camera stays put:

- **Squared tank.** Cup marks face the camera.
- **Rotated right.** Buttons on the left, reservoir on the right. This is the angle in `train/2026-10-09-first-try/`.
- **Rotated left.** The other way: reservoir on the left, buttons on the right.
- **Face on.** Buttons face the camera.

Pour on Squared tank: empty, 1 cup, 2 cups, then the even lines through 14. At empty, 8 cups, and 14 cups, also save Rotated right, Rotated left, and Face on. The cup line is only where you stop pouring. The file name does not store ounces or a percent. The morning clear-water set, with the window glare, is `train/2026-10-10-clear-water/`. The afternoon recapture with the sun off the tank is `train/2026-10-10-clear-water-afternoon/`. First file is `square_empty.jpg`. Upload the afternoon folder as the training set. The test split is a new walk of the same 18 stops, saved in `train/2026-10-10-clear-water-test/` by `archive/check/capture_test.py`. Upload that folder as the test split. Do not put those files in the training set. The level is the box ratio after the pictures are labeled.

Retake the last picture deletes that file and shows the same stop again. Save does not skip a filename that is already in train/. Replace clears that current file. A reload does not take another picture. If the process restarts, it continues at the first missing file. `train/2026-10-10-clear-water-afternoon/` is what you label. Leave `train/2026-10-09-first-try/` and the morning glare folder out of this upload. These files are already flipped. The accuracy number uses fresh fills after training, not these files.

Do not save `/frame.jpg` from `archive/check/preview.py`. After the first Nano pass that URL can include boxes. The hook starts `check/board.py`. The live board has no `/frame.jpg`.

## 3. Label and train

New Roboflow project, Object Detection. Upload `train/2026-10-10-clear-water-afternoon/` only.

The classes are `Reservoir` and `liquid-level`. No person class. The project stores boxes. A polygon is converted to the rectangle around it, so the edges that matter are the top and bottom of that rectangle. Use the box tool.

Labeling rules:

- `Reservoir` is the usable tank. The top edge is the 14-cup line, not the plastic lip above it. The bottom edge is the lowest visible point of the reservoir floor. Both edges are level.
- `liquid-level` uses that same bottom. The top edge is the water line.
- The water surface is slanted in the picture because the camera looks down. Bisect it. The top of `liquid-level` is the median between the low side of that surface and the high side, not the front lip and not the back of the ellipse.
- If the 14-cup line is slanted the same way, bisect that line too.
- An empty frame gets `Reservoir` only. Do not draw `liquid-level`, and do not mark the image null. The white piece at the bottom of the tank is not water.
- A full frame gets `liquid-level` up to the 14-cup line.

Percent full is how far the top of `liquid-level` sits between the bottom and the top of `Reservoir`. The two boxes have to share the same bottom or that ratio moves when the water did not.

The camera does not move during a pose, so the reservoir floor is the same pixels on every picture taken at that angle. Roboflow does not snap one box edge to another. The way to keep the bottoms lined up is to copy a box that is already right, then only move the top of `liquid-level`.

How we do that, from Roboflow Annotate:

- Label one pose at a time, in fill order. Squared tank from empty through 14, then rotated right, then rotated left, then face on. Repeat Previous copies the last image's boxes into the same place. That is only right when the coffee maker has not been turned.
- On the first picture of a pose, zoom in on the floor and set the `Reservoir` bottom on the lowest visible point. Zoom lock keeps that view while the edge is placed. This is the bottom for every later picture of that pose.
- On the next picture, use Repeat Previous. It is in the Bounding Box, Polygon, or Smart Polygon menu: Undo, Redo, and Repeat Previous. Leave the `Reservoir` box where it landed. If this frame has water, keep `liquid-level` and drag only its top edge to the bisected water line. Do not drag its bottom.
- On an empty frame, Repeat Previous, then delete `liquid-level` if the previous picture had one. The `Reservoir` box stays.
- A polygon's bottom is the lowest point of the outline, which wanders. Convert to Box from the right-click menu, then line that straight edge up with the `Reservoir` bottom before leaving the image.
- When the coffee maker is turned, do not reuse the previous pose's box. Start that pose's first `Reservoir` again, on its own floor, and repeat from there.

Train the tank with Custom Training. Architecture is Roboflow RF-DETR, size Nano. Checkpoint is the COCO default. Neural Architecture Search stays unused: its latency band times TensorRT on a T4, and the Pi loads `RFDETRNano`. YOLO26 stays unused. The person model is the separate COCO Nano.

Use the current dataset. Starting the train saves it as version 1. The split is already 180 train, 26 valid, 48 test. Leave that split.

Preprocessing on that version:

- Auto-Orient on. It strips EXIF so a sideways flag cannot turn a frame.
- Resize on, 384×384, Stretch to. Nano's documented input is 384×384. Stretch is also what `RFDETRNano.predict` does to a 1280×720 frame: it resizes both sides to 384. Fit (black edges) would train on padded squares the Pi does not make. Stretch scales every y by the same factor, so the level ratio is unchanged when the boxes come back to the original frame.
- Leave the rest off. No grayscale, auto-contrast, filter null, random sample, static crop, tile, dynamic crop, isolate objects, modify classes, or filter by tag. An empty frame is `Reservoir` only, not a null. The tank is not a small object, and it does not sit in one place across poses.

No augmentations on this version. A later version can add brightness, exposure, blur, and a little noise. Flip, rotation, crop, and shear stay off. The frames are already upright.

Leave the epoch count the Nano form shows. Do not type in the 200 from the search page.

## 4. Accuracy experiment

After the tank model exists, and before the ledger page stays up. These fills are new.

Stop the process on port 8080. One process owns the camera. From `/home/bs/tank`:

```text
/home/bs/tank-envs/current/bin/python check/accuracy.py
```

Open [http://192.168.1.248:8080](http://192.168.1.248:8080). The tank stays squared. Do not weigh this fill. The known value is the cup line the page names. The model value is the reading that page records from one settled frame.

Pour, wait for the surface, stand out of the picture, and press Record this reading. A second tap while that press is still working does not write another row. Retake last drops the last row and shows the same stop. A reload shows the rows already in `learn/accuracy.json`.

Three rounds of 4, 6, 8, 10, and 14 cups. Those five lines are each at or above 25% of 14 cups. Those 15 rows are the accuracy rows. Then pour to 2 cups, and brew once so the level falls through 4 cups. Those two rows are the alarm check. They stay out of the average.

Difference is model percent minus the cup-line percent. The number at the top is the average of the absolute differences, in percent of full. There is no pass line.

### Result, 10–11 October

The 15 accuracy rows and 2 alarm rows are in `learn/accuracy.json` on the Pi. The page that night scored them with the cup conversion it had then: an average of 10.5% of full, worst 39.7%. `check/volume.py` was then rebuilt from those same rounds, so scoring them again with today's table (4.8%) is in-sample and flatters the model.

The honest number scores each round with a cup table built from the other two rounds:

| Cup line | Held-out error, rounds 1 / 2 / 3, % of full |
|---|---|
| 4 cups | +1.2 / +0.4 / −1.4 |
| 6 cups | +0.7 / +0.5 / −1.3 |
| 8 cups | −0.7 / −0.2 / +6.5 |
| 10 cups | +2.4 / +0.8 / +12.1 |
| 14 cups | −31.7 / −32.9 / −28.6 |

From 4 to 10 cups the average is 2.4% of full (12 rows, worst 12.1%). The full tank is the weak point: in rounds 1 and 2 the model put the 14-cup water line at a box ratio of about 0.74, where round 3 put it at 0.995. With clear water at the very top, the surface is hard to see. The 11 October rehearsal hit the same thing once, a refill frame that read 52.5 of 70 fl oz. The ledger covers it: a refill books 70, and the highest settled reading after the refill becomes the full mark (section 6).

## 5. Person experiment

The live board's detection overlay is this experiment now. Watch [http://192.168.1.248:8080](http://192.168.1.248:8080). The green person box is drawn on each tick's frame, and a tick starts every 7.5 seconds, so stand still for about two ticks.

Stay out of frame. Walk in and stand at the tank. Leave. Walk through once without stopping. Step in, pour, and leave.

Write down when the green box appeared, when it went away, and whether the pour was inside a box. A visit starts when the person box is on and ends after two frames with no person box. One visit is one person-seen event. Only the person class counts, and only the person class is drawn. The person model's other classes stay in the frame's JSON. The live page does not use this two-frame visit. Section 6 writes the person-seen event when the appearance starts.

## 6. Live page

One process owns the camera. `scripts/pi-receive` starts `check/board.py`.

Each tick, in order:

1. One upright 1280×720 JPEG. `hflip`, `vflip`. The focus and exposure lock stays as it was set. The loop does not change the shutter. The webcam sends 1280×720 MJPEG at 60 fps whatever `-framerate` asks for, so the board's `ffmpeg` puts `fps=2` ahead of the flip and only flips and encodes 2 frames a second. With that load gone the two models take about 3.9 s together, but a tick starts at most every 7.5 s. Brewing starts on two ticks in a row that each fall more than 0.5 fl oz. In the 11 October rehearsal a full Classic brew fell about 3.6 fl oz a minute on average (about 3 early, about 4.6 mid-brew), about 0.4 fl oz a tick at 7.5 s. At 3.9 s a tick it would fall well under 0.5 a tick and seldom start Brewing. The pause also keeps the Pi near 62 °C, under its 80 °C soft throttle; running flat out it reached 79 °C. The reading's time is when that photo was taken, not when the models finished, and `capture_ms` is how old the photo was when the tick took it. Each reading also stores the board process's memory (`rss_mb`), the CPU temperature (`temp_c`), whole-Pi CPU use since the previous tick (`cpu_pct`), and free memory (`mem_free_pct`).
2. Tank RF-DETR Nano on that full frame. Classes `Reservoir` and `liquid-level`. Read the names from `class_names.txt`. `predict()` renames the last class to `__background__`.
3. Person RF-DETR Nano on the same frame. This is the COCO checkpoint. Use the person class only.
4. Gauge. `check/volume.py`. No memory. No reservoir box means `gauge_oz` is null. No liquid line means 0. Percent is cups / 14 × 100. Fluid ounces are cups × 5.
5. One SQLite transaction in `learn/tank.sqlite`. Insert a `reading`. Replace the `machine` row, including both ounce totals and the coffee figures. Insert an `event` when a person appearance starts, the reservoir comes back, the activity changes, or the alarm changes. A return that also changes the alarm writes both events. Tables are in `page/schema.sql`.
6. Write the JPEG under `learn/frames/` and delete all but the newest 8. The database does not store the JPEG. Beside each JPEG, write a JSON file with the same name: every box both models returned on that frame, its class, confidence, and corners, whether the gauge or the person check used it, and the gauge reading. It is pruned with its JPEG. The JPEG itself stays clean, with no boxes drawn in.

The page on port 8080 reads the `machine` row, the newest 50 `event` rows, the newest 40 `reading` rows (for the Raspberry Pi row and the use rate), the list of logged days, and those 8 frames with their box files. It does not open the camera, it does not run a model, and it does not scan the whole `reading` table. It fetches itself every 3 seconds, so nobody reloads it during the demo. The header says how old the last reading is. Past 30 seconds it turns red and says Not updating. When the loop cannot tick, it writes one line to `learn/board-error.txt` and the page shows that line in red. A good tick clears it. The photo shows that frame's saved boxes on top: Reservoir in blue, the water line in amber with the reading and percent, and a person in green. The person model's other COCO classes stay in the JSON and are not drawn. A box the gauge did not use is dashed. The Detections button hides them, and the browser remembers that choice. Under the photo, a Raspberry Pi row shows CPU use and the tank and person model times averaged over the last 2 minutes, the newest CPU temperature and free memory, and how often a reading lands. The temperature turns amber at 75 °C and red at 80 °C. The board to match is `page/live.html`.

The process keeps its running totals in memory and replays `reading` only when it starts, so a tick costs the same at the end of a day as at the start. A failed tick prints the traceback to `/tmp/preview.log` and the loop goes on with the next picture. If the models do not load, the page stays up and shows why.

Dates are America/Chicago. Store that day on the row.

On a seated tick with a liquid line and no person, move booked ounces by the gauge change. A drop of 2 fl oz subtracts 2. A rise of 2 fl oz adds 2 and does not bill. The fill tick is the exception. It sets booked ounces to 70. Booked ounces stay between 0 and 70.

| Item | Rule |
|---|---|
| Seated person | A person with the reservoir still visible stores `gauge_oz` and changes nothing else. Booked ounces, the alarm, the quiet-jump hold, and the brew window stay put. One event when `person_open` goes from 0 to 1. `person_open` clears after two ticks with no person. Leaving does not write a second line when the reservoir stayed. |
| Taken | Confirm a take only after the reservoir has been missing for two ticks and a person was on one of them, or was still latched from just before (`person_open`, which holds for two ticks after the last person). Someone who lifts the reservoir and walks out between two ticks is never in a frame without it, and that is still a take. Save booked ounces in `taken_oz`. Activity becomes Out. A single miss that comes back changes nothing. Out stays until the return tick, including frames where the box is back and the person is still there. |
| Returned | The return tick is the first tick the reservoir is back, a liquid line is present, and no person is in the picture. A return with no line keeps the saved ounces and stays Out. Up at least 3.5 fl oz from `taken_oz` is a fill. Book 70. `delta_oz` is 70 minus `taken_oz`. Down at least 3.5 is a dump, and booked ounces become the model reading. A smaller change is a put-back at the model reading. A return may jump more than 5 fl oz. The quiet-jump wait does not apply. The reading stores both numbers. |
| After a fill | The fill tick's gauge becomes 70 and an empty tank stays 0. Later gauges scale onto that line: booked ounces are gauge × 70 ÷ the fill gauge, capped at 70. A higher seated, person-free gauge after the fill becomes the new full mark. The return tick can catch the tank mid-settle: in the 11 October rehearsal it read 52.5 and the next tick read 70, and keeping 52.5 would have held booked ounces at 70 until the brew fell below 52.5. If the model read 60 at the fill, a gauge of 30 books 35. Booked ounces stay 70 while the gauge sits still, and an empty tank still reaches 0, so a low fill reading cannot keep the alarm off. The scale ends at the next take, dump, put-back, or seated empty. |
| Quiet jump | Compare the new gauge to the previous gauge. A step over 5 fl oz, reservoir seated, nobody taking it, holds booked ounces. Accept the candidate after two further ticks, each within 1 fl oz of it. Any other tick cancels the hold. A seated person, a take, and a return cancel it too. An accepted rise updates booked ounces, does not bill, and does not book 70. The alarm follows booked ounces. |
| Alarm | On under 17.5 fl oz of booked ounces. Off at 17.5 and above. Both ounce totals at 0 are not the alarm. |
| Bands | Full at 52.5 fl oz and up. 3/4 from 35 up to 52.5. 1/2 from 17.5 up to 35. Low under 17.5. A shared edge belongs to the higher band. Bands use booked ounces. |
| Activity | Out only while a confirmed take is open. Otherwise brewing starts when two brew samples in a row each fell by more than 0.5 and at most 5 fl oz. A brew sample is a seated tick with a line and no person, and it is not inside a quiet-jump hold. Brewing ends when no brew sample has fallen more than 0.5 fl oz for 60 seconds. A Classic brew falls about 0.4 fl oz a tick with a few tenths of model wobble, so ticks that do not fall are normal mid-brew; the longest such stretch in the rehearsal was about 45 seconds. Otherwise idle. A person in the frame does not stop a brew and does not make that drop a dump. A miss that is not a take is not a brew sample and does not change activity. During a brew, two seated ticks in a row with no liquid line mean the tank ran out below the last line the model can see. Booked ounces go to 0, that drop counts as out, and activity goes back to idle. One such tick is a missed line and changes nothing. |
| Empty | A seated tick with no line clears a booking under 5 fl oz to 0. Outside a brew that clear is the empty-tank flicker and is not ounces out. |
| Stale | `gap_ticks` counts consecutive misses while no take is open. `gap_person` is 1 when any tick in that gap had a person. At 2 with `gap_person` 1, the take confirms and the gap clears. At 4 with `gap_person` 0, the page says the reservoir is not in view and it is holding the last level. Those ticks leave booked ounces, both totals, the alarm, and activity unchanged. The gap clears when the reservoir is visible or a take confirms. Stale is not an event. |
| Used, last 15 min | Sum of downward steps in `booked_oz` whose later reading is in the last 15 minutes. A rise, including the jump to 70, adds 0. Do not subtract the first reading in the window from the last. A step only counts below the lowest booked level since the last rise of more than 2 fl oz. The model wobbles a few tenths on a still tank, and mid-brew the line rose up to 1.4 fl oz for a single tick in the 11 October rehearsal. Without that floor, every wobble down would count again after the wobble back up. The ledger writes `out_15m` on `machine`. |
| Used today | The same sum since local midnight. The ledger writes `out_today` on `machine`. On a brew that fits in 15 minutes the two numbers match. |
| Coffee | $0.50 a cup. A fill bills `delta_oz`, which is 70 minus `taken_oz`, not the model delta. `filled_oz` is the sum of today's fill deltas. Coffee today is `filled_oz / 5 × 0.50`. The month is the mean of logged days × 30. A day with no rows is left out. A logged day with no refill is $0. The ledger writes `coffee_month` on `machine`. |

Not in this build. An exposure probe, thumbnail files, a password, a reservoir crop, one combined model, a second Inference server, and a 24-hour rate. The use rate is the net fall in booked ounces over the last 2 minutes, per minute, read from `reading` by the page; it needs a minute of history, and a rise reads as 0. Empty in is booked ounces over that rate, shown as Not draining under 0.2 fl oz a minute, and Empty once the tank is dry. Each reading stores `tank_ms` and `person_ms`, about 1.85 s each on 11 October. A slow tick waits, then the next grab starts.

## 7. Demo

Monday 12 October, 1:00 PM ET. The page is already ticking before the call. Do not push a commit during the call: a restart costs about 66 seconds while the models load.

Reset before the call, after any rehearsal, so the log starts clean. Events are written once and a restart does not rebuild them. From an SSH session on the Pi:

```sh
fuser -k 8080/tcp
cd /home/bs/tank/learn && rm -f tank.sqlite tank.sqlite-wal tank.sqlite-shm board-error.txt && rm -rf frames
cd /home/bs/tank && setsid nohup /home/bs/tank-envs/current/bin/python check/board.py >/tmp/preview.log 2>&1 </dev/null &
```

Keep `learn/accuracy.json`. Wait about 70 seconds, then open the page and check that the header says Updated a few seconds ago and Live in green. Do not wipe after the call has started.

WARM is off. 1-4 CUP is off. The carafe is seated and empty. Start near 40 fl oz. The camera sees the whole machine, so out means out of that frame.

Stop the cycle and wait until the machine is off before the reservoir comes out.

1. Open the page. The band is 3/4. The refill alarm is off. Activity is Idle. The log has no fill. Used, last 15 min and Used today are both 0.0 fl oz. Use rate reads 0.0 and Empty in says Not draining. The photo shows the Reservoir box in blue and the water line in amber with its reading. The Raspberry Pi row under the photo shows the model times, about 1.9 s each.
2. Step in where the reservoir stays visible, then step out. A green person box appears on the photo. One log line says a person was seen. People seen today becomes 1 on that line. The level is not a fill or a dump.
3. Leave the reservoir seated and start a Classic brew from the side, without blocking the camera's view of the reservoir. The opening pause is Idle, and both Used tiles can stay 0. That is not the alarm. Brewing shows about 40 seconds after the level starts falling, and stays on through the brew. Used today climbs, Use rate shows about 3 to 5 fl oz a minute, and Empty in counts down. From 40 fl oz at about 3.6 fl oz a minute, the band goes Low and the alarm comes on about 6 minutes in, and the tank runs dry about 11 minutes in. Do not walk through the frame during the brew.
4. Stop the cycle. Take the reservoir out of the frame, fill it to the 14-cup line, put it back, and leave the frame. Carrying it straight out is a take: a person seen in the two ticks before it disappeared counts. Wait for the return tick, the first one with the reservoir seated and nobody in view. That tick books 70 when the model rose at least 3.5 fl oz from the saved ounces. The bill is 70 minus those saved ounces. The log keeps the model reading next to 70, and the level panel shows it as Camera reads. That first reading can be low on a full, clear tank. The next settled reading becomes the full mark. Both Used tiles stay at the ounces the brew dropped. Refilled today and Refill bill today show the fill. The monthly estimate is 30 times today's dollars, because it has 1 day of data.

Waiting before pressing Brew after a refill is fine. A full tank sitting still stays at 70 and Idle, and the brew plays out the same whenever it starts.

## 8. Rehearsal, 11 October 2026

A full refill and a Classic brew from empty, 23:12 to 23:34, with the camera at night under room lights. Every frame and its box file from that run are in `/home/bs/rehearsal-2026-10-11/` on the Pi.

| Time | What the board recorded |
|---|---|
| 23:12:20 | Person seen at the machine |
| 23:12:35 | Reservoir taken, saved 0 fl oz. The person carried it straight out of the frame. |
| 23:13:43 | Refill booked at 70 fl oz, bill $7.00. That frame read 52.5; the next read 70.0. |
| 23:14:28 | Level starts falling after the warm-up, and booked ounces follow the camera |
| 23:15:05 | Brewing, 37 seconds after the fall began, on through the brew |
| 23:29:13 | Refill alarm on at 17.4 fl oz, still brewing |
| 23:33:51 | Tank dry. 0 fl oz, Idle. Used today 70.0 fl oz, exactly what went in. |

The brew took about 19½ minutes from full to empty, about 3.6 fl oz a minute, slower than the 12 to 15 minutes `hardware.md` gives for a full carafe.

What the rehearsal changed:

- The take rule now counts a person seen just before the reservoir vanished. Carrying it straight to the sink was not a take before.
- The full mark after a refill is the highest settled reading, not the return tick's reading. The low 52.5 had held the level at 70 for five minutes.
- Brewing ends after 60 seconds with no fall, not on the first tick that does not fall. The old rule wrote ten Brewing and Idle lines in five and a half minutes.
- The noise floor for Used is 2 fl oz. Single-tick upticks of up to 1.4 fl oz were counting the same ounces twice, 49.4 fl oz used out of 45.6.

Edge device during the brew: two RF-DETR Nano passes of about 1.9 seconds each on the Pi 4's CPU, a reading every 7.5 seconds, CPU use about 50%, CPU at 61 to 63 °C, and about 68% of memory free. Before `ffmpeg` was thinned to 2 frames a second it used 166% CPU by itself, each model pass took about 3.7 seconds, and the CPU sat at 79 °C.
