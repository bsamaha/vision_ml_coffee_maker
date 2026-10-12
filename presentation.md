# Presentation: watching chemical tanks with a camera

Field Engineering Tech Challenge, Blake Samaha. Monday 12 October 2026, 1:00 PM ET. 30 minutes live, hard stop, then a 15 to 30 minute debrief.

This is the outline for the slides and the talk track. The case and its numbers are in [business-case.md](business-case.md). How to run the demo, and every rule the board follows, is in [technical-solution.md](technical-solution.md). The Pi and the coffee maker are in [hardware.md](hardware.md).

## The pitch in one breath

Company X can't verify the chemical deliveries it pays for, and it can't see when a well stops being treated. One camera and a Raspberry Pi-class computer per pad, running a Roboflow Workflow with Roboflow Inference, reads every tank's level, logs every visit with a photo, and books every refill. One prevented failure on a high-rate well pays for about 94 sites. Today's proof is a coffee maker standing in for the tank, running live on a Raspberry Pi 4.

## Agenda

The brew is the long pole. From about 40 fl oz it shows Brewing within a minute, raises the alarm about 6 minutes in, and runs dry about 11 minutes in. Start it early and talk through the Roboflow stages while it runs.

| Time | Section | Live on the board |
|---|---|---|
| 0:00 | The problem at Company X | Board already ticking, level about 3/4 |
| 3:00 | Why a camera, and how the kitchen maps to a pad | |
| 5:00 | Live: a visit | Step in and out. Green person box, "Person seen", no bill |
| 6:00 | Live: start a Classic brew from the side | Brewing within about a minute |
| 7:00 | Data acquisition and labeling | Brew running |
| 11:00 | Model training | Brew running. The alarm comes on about here |
| 14:00 | The Workflow and its custom block, in the Roboflow app | |
| 19:00 | Deployment with Roboflow Inference on the Pi | Raspberry Pi row, detection overlay |
| 22:00 | Live: take the reservoir, refill it, put it back | Out, then Fill: 70 fl oz booked, refill bill |
| 24:00 | The insights, and what they mean on a pad | Use rate, Empty in, event log |
| 26:00 | Results, value, limits, next steps | |
| 29:00 | Close | |

## How the kitchen maps to a pad

| Kitchen | Pad |
|---|---|
| The Ninja's 70 fl oz reservoir | A 125 to 335 gallon poly chemical tank |
| A Classic brew drawing water down | The injection pump drawing chemical down |
| Taking the reservoir, filling it, putting it back | A treater truck refilling the tank |
| The refill bill, $0.50 a cup | The delivery ticket checked against what arrived |
| The refill alarm under 25% | A refill due before the well goes untreated |
| A person at the machine | A pumper or vendor on the pad, with a photo |
| The use rate and time to empty | The consumption baseline that catches a stopped pump, and the next delivery date |

One difference matters: a brew empties the reservoir, and a pad's pump does not. The kitchen shows the mechanics, not the field accuracy.

## 1. Use case: the business problem

- **Two problems on every pad.** Billing nobody can check: a ticket can bill a full refill when half was delivered. And treatment interruptions nobody sees: a dry tank or a stopped pump sits until the next visit, days to weeks, while the tubing corrodes.
- **Why it's unwatched today.** Many pads have SCADA on the well but leave the chemical skid to the treatment vendor. The RTU often has no spare input and no legal place for a tank-top sensor. A camera on a pole needs neither.
- **Why a camera over a level sensor.** Probes foul in inhibitor, acid, and wax. Radar costs about $2,600 a tank. Only a camera records who was at the tank and when, with a photo that settles a dispute, and one camera covers every tank on the pad for about $600.
- **The number.** One failure on the fast example well costs about $56,850: a $25,000 pull plus seven days of lost oil at 50 barrels a day. That equips about 94 sites. The slow example well is honest about where this does not pay on interruptions alone.

## 2. Data acquisition and labeling

What to say:

- **Our own data, our own camera.** A USB webcam on the Pi, aimed at the reservoir and the whole machine, the same camera that runs the demo. The camera is mounted upside down, so every frame is flipped in software, training and live alike.
- **Locked camera first.** Focus and exposure were locked before any keeper stills, and the board reapplies that lock every time it opens the camera, so the training pictures and the live pictures match.
- **Designed for coverage, not volume.** A guided 18-stop shoot: empty, 1 cup, 2 cups, then every even line to 14, plus three more turns of the machine (rotated right, rotated left, face on) at empty, 8, and 14 cups. Low fills were shot on purpose so the alarm has examples.
- **Straight into Roboflow.** A rapid capture page sent extra stills directly into the project through Roboflow's dataset upload API, one press per picture or a batch at a time.
- **Bad data left out.** A morning set with window glare and the first attempt were kept out. The training set is the afternoon shoot, with the sun off the tank.
- **A held-out test split.** A fresh walk of the same 18 stops, taken separately and uploaded only as the test split.
- **Labeling built for a measurement, not just a detection.** Two classes, `Reservoir` and `liquid-level`, boxes only. Both boxes share the same bottom edge, so the level is just where the water line sits between the reservoir's bottom and its 14-cup line. The slanted water surface is bisected. An empty tank gets `Reservoir` only, not a null. In Roboflow Annotate, each pose was labeled in fill order with Repeat Previous, so the floor edge never moved and only the water line did.

Show: the Roboflow project, a labeled squared-tank image and a rotated one, and the dataset version's split.

Version 1 of the dataset: 180 train, 26 valid, 48 test. Confirm that count in the Roboflow project before the call.

## 3. Model training

What to say:

- **Project type.** Object detection. The level is the ratio of two box edges, so boxes are all it needs. Segmentation would cost labeling time for no gain in the ratio.
- **Model.** Roboflow RF-DETR Nano, from the COCO checkpoint. Small enough for a Pi's CPU, which is the field hardware story.
- **Preprocessing.** Auto-Orient on. Resize to 384×384 with Stretch, which matches what inference does to a 1280×720 frame and scales every height by the same factor, so the level ratio survives. Fit would have trained on padded squares the Pi never sends.
- **Augmentations: none, on purpose.** The camera is fixed and the frames are already upright, so flips, rotations, crops, and shear would teach poses the camera never sees. Brightness, exposure, blur, and noise are the next version, for outdoor light.
- **Person detection.** The stock COCO RF-DETR Nano, kept to the person class. No custom training needed.

## 4. The Workflow and its custom block

What to say:

- **One Workflow, three steps.** The fine-tuned tank model, the COCO person model filtered to `person`, and a custom Python block, TankGauge.
- **What the custom block does.** It picks the best `Reservoir` and `liquid-level` boxes, turns the water line's position into fluid ounces through a cup table calibrated from the accuracy rounds, and reports whether a person is in view. That is the business measurement, inside the Workflow.
- **What stays outside the Workflow, and why.** A Workflow sees one image. Whether a rise is a refill or noise, whether a missing tank was taken, whether a brew is under way: those need memory across frames, so the board's ledger keeps them. Perception in the Workflow, business rules beside it.
- **One definition, two places.** The same JSON is saved in the Roboflow app and runs on the Pi. It is generated from the code, and a test fails if the two drift.
- **Proved against the earlier pipeline.** On 348 saved rehearsal frames, the Workflow matched the earlier in-process models within 1 fl oz on 329 of 336 readings and on every person flag. On the two frames where they differed by more, the Workflow was right.

- **The alert, live in the editor.** The alert version adds Continue If (under 17.5 fl oz), a box visualization, and an Email Notification block with the annotated photo attached. Drop in an empty-tank frame and the email arrives. Drop in a full one and nothing is sent. The Pi runs the version without email, because each email costs credits and the board already shows the alarm.

Show: the Workflow in the Roboflow editor, the TankGauge block's code, then the alert version. Upload `.shots/rehearsal/00000303.jpg` (empty, nobody in view) and show the email arriving with its photo. Then upload `00000316.jpg` (full) and show that nothing is sent. Use one upload each: every email spends credits.

## 5. Deployment with Roboflow Inference, and the insights

Deployment, what to say:

- **On the edge, on a hobby-board CPU.** The Workflow runs with the `inference` library inside the board's own process on a Raspberry Pi 4: no GPU, no Docker, no cloud call per frame. Both models download once from Roboflow and run from a local cache.
- **Measured.** About 1.6 to 1.9 seconds per model, a reading every 7.5 seconds, CPU about 50 to 60%, 62 °C, about half of the 4 GB free. The board shows these live, under the photo.
- **Built to keep running.** A bad frame or a failed tick is logged and skipped. If the camera stops, or the Workflow does not load, the page stays up and says why in red. The header turns red if readings stop arriving.

The insights, and what each one becomes on a pad:

| On the board | On the pad |
|---|---|
| Live level with a tank gauge, and the model's boxes on the photo | Tank level per tank, with photo evidence |
| Refill alarm under 25% | Refill due, before the well goes untreated |
| Activity: Idle, Brewing, Out | Pump running, or not; tank being serviced |
| Used in the last 15 minutes and today, use rate, Empty in | Consumption baseline; a stopped pump shows as a rate that went flat; the next delivery date |
| Every visit and refill in the event log, with a photo | A visit record for every pumper and vendor |
| Refill bill: 70 fl oz minus what was left | Every delivery ticket checked against a fill event |

The board is the operator screen (an HMI). The refill email is the alert, shown from the Roboflow app's version of the Workflow. Sending every event out from the Pi, and onto the operator's SCADA or historian over MQTT, is the next step.

## 6. Results

- **Accuracy, measured the honest way.** Three rounds of 4, 6, 8, 10, and 14 cups, each round scored with a cup table built from the other two. 4 to 10 cups: 2.4% of full on average, nine of twelve readings within 1.5%. The field target is 3% of tank height.
- **The weak point, found and handled.** A full tank of clear water reads low: about 74% in two of three rounds. The ledger books 70 on a refill and takes the highest settled reading after it as full, so the alarm still fires and an empty tank still reads 0.
- **A full rehearsal, end to end.** On 11 October a full tank was taken, refilled, and brewed to empty. The board booked the refill at $7.00, held Brewing through the brew, raised the alarm at 17.4 fl oz, and ended at 0 with 70.0 fl oz used, exactly what went in.
- **Problems the rehearsal caught, and fixed the same night.** A low first reading after the refill pinned the level at 70. A one-tick rule made Brewing flicker on and off. Model wobble counted the same ounces twice. Carrying the reservoir straight to the sink wasn't recognized as a take. Each was fixed and replayed against the saved readings.
- **Value.** About $600 a site with power, about $25 a year to run. One prevented failure on a high-rate well, about $56,850, equips about 94 sites.

## 7. Limits and next steps

Limits to say out loud:

- A clear reservoir indoors reads more cleanly than a poly tank outdoors. Outdoor accuracy, summer heat, and solar uptime are unproven.
- The Pi reached 79 °C at full load indoors before its camera feed was trimmed. Heat in a Permian enclosure is a design input, not a footnote.
- A full tank is the model's weak point today.
- On a slow well, a stopped pump can't be caught in a useful time from the camera alone.

Next steps:

1. Alerts from the edge and the operator hand-off: the refill email sent from the Pi on the board's own alarm and fill events, and MQTT to SCADA or a historian.
2. Field data: pictures from a real pad, with brightness, exposure, blur, and noise augmentations, and spills as a new class.
3. A strapping table per tank, calibrated at the top of the tank on site.
4. Duty cycling for off-grid sites, and Roboflow's deployment manager for a fleet.
5. An optional ultrasonic sensor on high-value tanks, cross-checked against the camera.

## Debrief questions to be ready for

- **Why not segmentation?** The level is a ratio of two horizontal edges. Boxes give exactly that, with far less labeling.
- **Why no augmentations?** A fixed, upright camera. Geometric augmentations would teach views it never sees. Photometric ones are next, for outdoor light.
- **How many images, and is that enough?** The version-1 split is 180, 26, and 48. It's enough for one fixed camera and one tank in one kitchen. A fleet needs data from real pads.
- **Why is the ledger outside the Workflow?** A Workflow is stateless per image. Refills, takes, and brews are decisions across frames.
- **What happens if the network drops?** The models run locally from the cache, with no cloud call per frame. Roboflow is needed to download the models the first time.
- **Why one reading every 7.5 seconds?** The brew rule needs a measurable fall per tick, and the gap keeps the Pi near 62 °C. A field box reads every few minutes.
- **How do you know the reading is right?** Held-out accuracy by cup line, a full rehearsal that accounted for every ounce, and a 348-frame check between two runtimes.
- **How would this scale to hundreds of pads?** The same Workflow on every site computer, one Roboflow plan for the fleet, retraining from field images, and the operator's own systems for the log.
- **What does it cost to run?** Inference on the site's own hardware uses no Roboflow credits. About $25 a year in cellular data per site.

## Before the call

- Reset the board, as in section 7 of [technical-solution.md](technical-solution.md), and wait for "Roboflow Workflow on local Inference" in green.
- Machine ready: about 40 fl oz in the reservoir, carafe seated and empty, WARM and 1-4 CUP off.
- Tabs open: the board, the Roboflow project's dataset and a labeled image, the trained model's version page, the Workflow in the editor, the alert Workflow with `alert_email` filled in, and your inbox.
- Files ready to upload: `.shots/rehearsal/00000303.jpg` (empty) and `00000316.jpg` (full).
- A backup in case the live board fails: screenshots of the board mid-brew and after a refill, and the rehearsal's refill frames.
- Don't push code during the call. A restart takes about a minute.
