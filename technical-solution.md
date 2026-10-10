# Run sheet

Hardware is in [hardware.md](hardware.md). The case is in [business-case.md](business-case.md). Publish a code change with the steps in [README.md](README.md).

This is a proof on the Ninja, not a small copy of the well. A brew here empties the reservoir. On a pad the pump does not. The page has to show volume, a consumption rate, person visits, refills, a coffee bill, and a refill alarm.

## What is already true

The camera stays where it is. It looks at the graduated face from a little above the reservoir, with the whole machine in the frame. On 9 October 2026 a fill of about 75% showed as a bright horizontal band. The cup marks above that band were readable. Do not zoom. This webcam has no zoom, and a crop missed the tank.

The camera body is upside down. There is no flip control on the device. Every still and the live page use `hflip,vflip`. The preview owns `/dev/video0`. Open [http://192.168.1.248:8080](http://192.168.1.248:8080). A person box is green. Chair, bowl, dining table, and bottle boxes are orange. The picture updates about every 5 seconds.

Nano is the COCO `RFDETRNano` from the uv lock, on CPU. One 1280×720 frame takes about 4.4 seconds. Person is a class on that model. It is not a second model we train. The tank model (`liquid` and `reservoir`) is not trained yet.

The water line is the top of that bright band. Percent full is how high the line sits in the reservoir. Volume is that percent times 70 fl oz. A rate of 0 is normal. Under 25% full (17.5 fl oz) is the refill alarm. Accuracy is only figured on readings at or above 25%.

## Traps

- Training stills are 1280×720 MJPEG with the same `hflip,vflip` as the preview. Another size or an unflipped frame is a different picture from the one we checked.
- Stop the preview before opening `/dev/video0` from anything else, or save stills from `http://127.0.0.1:8080/frame.jpg`. Two opens fight over the camera.
- `power_line_frequency=2` is 60 Hz. Value 1 is 50 Hz.
- Manual exposure is `auto_exposure=1`, then `exposure_time_absolute`. Switching to manual without the absolute value blacks the frame. `auto_exposure=3` is the current Aperture Priority mode.
- Lock focus only after this aim is final: `focus_automatic_continuous=0`, then `focus_absolute` at the settled value. Set those again if a new capture process opens the camera. They do not always stick.
- A Classic brew uses whatever is in the reservoir and empties it. The refill alarm will come on partway through a normal brew and stay on until someone pours. That is the alarm demo. It is not a fault in the page.
- Set WARM to 0 and wait until the machine is off before pouring. With the plate on, water added to the reservoir starts another brew, so the pour and the pump run together.
- 1-4 CUP does not stop at 4 cups. Leave it off.
- The carafe is seated and empty before a brew. If it is missing or already full, the basket overflows.
- The brew pauses at the start, then continues. During that pause the rate is about 0. That is not the alarm.
- A visit is the person class only. A chair box is not a visit.
- The level for a refill is the last frame with no person, and the frame after they have been gone. Do not read the line while a person covers the reservoir.
- A rise with nobody in frame is not a refill and not a person visit.
- Label `liquid` up to the top of the bright band. Vertical reflections in the water and the printed cup numbers are not the line.
- Under 25% is photographed so the alarm has examples. Those frames are not part of the accuracy average.

## 1. Lock the camera

Do this once, before the stills you keep. The aim does not change after it.

```bash
v4l2-ctl -d /dev/video0 --list-ctrls
v4l2-ctl -d /dev/video0 -c power_line_frequency=2
v4l2-ctl -d /dev/video0 -c focus_automatic_continuous=0
v4l2-ctl -d /dev/video0 -c auto_exposure=1
```

Read the settled `focus_absolute` and a usable `exposure_time_absolute` from `--list-ctrls` before turning the automatic modes off. Write those two numbers to `/home/bs/tank-envs/camera.conf`.

```
focus_absolute=<settled value>
exposure_time_absolute=<settled value>
```

`check/capture.py` applies `power_line_frequency=2`, manual focus, that focus value, `auto_exposure=1`, then `exposure_time_absolute`, every time it opens the camera. Manual exposure without the absolute value blacks the frame. Confirm the page is still a bright, sharp picture of the reservoir before you leave it running.

## 2. Capture

Open http://raspberrypi.local:8080. That page is `check/capture.py`. It shows the clean camera and does not draw boxes.

If `camera.conf` is missing, the picture still moves and the page says the camera is not locked. The countdown starts the first time you open the page after that file exists. It does not pause between cups. Open it when the reservoir is empty and you can stay for the whole ladder.

There is no capture button. The first line waits 60 seconds, then writes `train/0cup_0.0oz_0.0pct.jpg`. Each later line waits 45 seconds and tells you to add 1/2 cup. The stops run from 1/2 cup through 14 cups. Stand where the camera cannot see you before the count reaches zero. The page saves the picture at zero and shows the next stop. Fills under 17.5 fl oz, which is under 25%, say alarm. The last stop is 14 cups. Empty plus every half cup through 14 is 29 pictures.

A reload stays on the current cup. If the process restarts, it continues at the first missing file. `train/` is what you label. These files are already flipped. The accuracy number uses fresh fills after training, not these files.

Do not save `/frame.jpg` from `check/preview.py`. After the first Nano pass that URL can include boxes. Person notes later point the hook back at `check/preview.py`.

## 3. Label and train

New Roboflow project, Object Detection. Upload `train/` only.

- `liquid` — from the bottom of the reservoir up to the bright band. The top edge sits on that band.
- `reservoir` — the tank outline.

No person class. The first version uses no augmentations, so the result is these pictures. A later version can add brightness, exposure, blur, and a little noise. Flip, rotation, crop, and shear stay off. The frames are already upright. Draw the boxes tight. The top of the liquid box is the level. The empty frame gets a reservoir box and no liquid box.

Train RF-DETR Nano for the tank. Keep the COCO Nano for person.

## 4. Accuracy experiment

After the tank model exists, and before the ledger page stays up. These fills are new.

The camera does not move. Weigh the water, let the surface settle, and let the tank model read percent full. Keep a trial only if the weighed fill is at or above 25%. Under 25% is an alarm check, not an accuracy sample.

One round is five weighed fills from about 25% to full. Run three rounds.

| Round | Weighed fl oz | Weighed % of 70 | Model % | Difference |
|---|---|---|---|---|
| 1 | | | | |
| 1 | | | | |
| 1 | | | | |
| 1 | | | | |
| 1 | | | | |
| 2 | | | | |
| 2 | | | | |
| 2 | | | | |
| 2 | | | | |
| 2 | | | | |
| 3 | | | | |
| 3 | | | | |
| 3 | | | | |
| 3 | | | | |
| 3 | | | | |

Difference is model % minus weighed %. The result is the average of the absolute differences, in percent of full. There is no pass line.

Brew once from above 25% down through 25% and confirm the refill alarm comes on. That check is separate from the average.

## 5. Person experiment

The boxed preview is this experiment. Watch [http://192.168.1.248:8080](http://192.168.1.248:8080). The green box lags by about 5 seconds. Stand still that long.

Stay out of frame. Walk in and stand at the tank. Leave. Walk through once without stopping. Step in, pour, and leave.

Write down when the green box appeared, when it went away, and whether the pour was inside a box. A visit starts when the person box is on and ends after two frames with no person box. One visit is one person-seen event. Orange boxes do not count.

## 6. Live page

Start this after the accuracy table and the person notes are written down. The boxed preview can stay up while that work happens. The ledger page is the next program. It is not running yet.

One JPEG about every 15 seconds. That is longer than the 5 second Nano pass, so a frame finishes before the next one starts. Ledger on disk. systemd on boot. Page on the LAN behind a password.

```text
webcam → Pi
           upright JPEG
           tank Nano on the reservoir crop → liquid, reservoir
           COCO Nano on the full frame → person
           custom block → level, visit, refill, rates, alarm, coffee bill
           ledger
           page → browser on the LAN
```

Dates are America/Chicago. Today is separate from the three calendar days before it.

| On the page | Rule |
|---|---|
| Level | Percent full, and fl oz as that percent times 70. Median of the last 3 confident stills. |
| Person | Green box right now, yes or no. |
| Last minute consumption | fl oz the level fell in the last 60 seconds. A rise counts as 0. A 0 is normal. |
| Average consumption | fl oz that left the tank over the last 24 hours, divided by 24 hours, in fl oz/min. Idle minutes count. |
| Person seen | Visits today, and each of the previous 3 days. |
| Refill count | Today, and each of the previous 3 days. |
| Refill volume | fl oz added on those same days. |
| Coffee bill | Refill dollars for those same days, and a monthly figure. |
| Alarm | Refill needed when the level is under 25% full. A rate of 0 is not an alarm. |

Coffee is $0.50 a cup. One cup is 5 fl oz.

```text
dollars = (added fl oz / 5) × 0.50
monthly = average daily coffee dollars × 30
```

The average uses today and the previous 3 days. A day with no refill is $0. Divide by how many of those days are in the ledger.

A rise smaller than the spread in the accuracy experiment does not count as a refill. Until that spread is written down, ignore a rise under 5% of full.

## 7. Demo

Monday 12 October, 1:00 PM ET.

1. Open the page. The tank is above 25%. The rate can be 0. No alarm. Read the accuracy number and the person notes.
2. Step in and step out without pouring. Person seen for today goes up. Refill count does not.
3. Step in, pour, step out. Person seen goes up again. Refill count, volume, and the coffee bill go up. WARM is off.
4. Start a Classic brew and let it fall through 25%. The refill alarm comes on. A 0 rate does not alarm.
