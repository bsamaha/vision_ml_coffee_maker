# Chemical tank route audit — plan

This file is an earlier draft. Do not build from it. The rig, the capture, and the page rules are in [technical-solution.md](technical-solution.md). Hardware is in [hardware.md](hardware.md). The Pi runs the model. The laptop is the browser. There is no strap table and no 3% lab pass line.

## Idea

A camera watches a chemical tank at a well. A detector finds the liquid surface, and the level is read as a percentage and in gallons. A person detector logs when the attendant is at the tank. A custom Workflow block compares each vendor ticket to what the camera saw and shows a shift dashboard.

The pitch in [business-case.md](business-case.md) sells one catch. The operator owns the camera. A ticket bills a full refill and the pictures show half. Scaled to a 335-gallon tank, that gap is about $2,760, which pays for the box. A wasted visit and a fast drain are shown. They are not priced as a route that has been cut, and a workover dollar stays off the screen.

The coffee maker's water reservoir stands in for one of those tanks. Say that in the room. The wrench board is the fallback.

The pitch is in [business-case.md](business-case.md). Competitors, sensors, accuracy, costs, hardware, connectivity, and Roboflow pricing are in [business-case-reference.md](business-case-reference.md). This file is the demo build.

## Demo vs. field

| | Demo | Field |
|---|---|---|
| Camera | Raspberry Pi camera, or the laptop camera | Outdoor PoE IP camera rated to 60 °C |
| Edge | This laptop runs Inference | Fanless reComputer R1000 on the pad |
| Link | Wi-Fi | Cellular, SCADA radio (Modbus), LoRaWAN, or satellite. Only results leave the pad. |
| Level | Liquid surface in pixels, converted to mL by a strap table for the reservoir | The same method, with a strap table for each tank, converted to gallons |

## Reading the level

The model detects two classes in the tank crop:

- **`liquid`**: a box from the bottom of the reservoir up to the surface. Its top edge is the level.
- **`reservoir`**: the outline of the tank. It checks that the camera hasn't moved.

**Calibration**, done once at setup:

1. Start with the reservoir empty. Pour in 100 mL at a time with a measuring cup, and take a still at each step.
2. Record the pixel row of the surface at each step. That is the strap table, mapping a pixel row to mL. Reservoirs aren't straight-sided, so the table interpolates between points instead of assuming a line.
3. Save the position of the `reservoir` box.

**Each still:**

```text
level_mL  = strap_table(top edge of the liquid box)
level_pct = level_mL ÷ capacity_mL
```

- The level is the median of the last three confident stills, which removes single-frame noise.
- If the `reservoir` box moves more than a few pixels from its calibrated position, the reading is `review` and the dashboard flags a recalibration.
- The refill line is 25%. At or below it, a work order opens.
- Delivered amount = `after_mL − before_mL`, scaled so a full reservoir is 335 gallons, the tank in the pitch.
- The sale ticket bills a refill from the 25% line to full: 251 gallons, about $5,530 at $22 a gallon. Half of that delivery is about 126 gallons. The disputed amount is about $2,760. That is the number the pitch sells. Pour to make the gap land there.

**Accuracy estimate:** ±2% of tank height in the lab. In the field, about ±3–5% in daylight. The lab test below measures the real number, and the event tolerances come from it.

## Lab accuracy test

The test answers one question: how close is the camera to what was actually poured?

1. **Ground truth.** Pour measured volumes. Use around 20 levels that aren't on the 100 mL calibration steps. Pour, wait for the surface to settle, and take three stills.
2. **Conditions.** Room light, a lamp from the side, dim light, and a hand near the tank. Keep these levels out of training.
3. **Report:**
   - Mean absolute error, in % of height and in mL.
   - 95th-percentile error.
   - Bias: whether it reads high or low on average.
   - Repeatability: the spread of 10 stills at one level.
   - Delivery error: the measured `after − before` against the volume actually poured.
4. **Pass:** a mean error of 2% or less and a 95th percentile of 4% or less. Readings close to the refill line must never read high. A low tank read as high means the refill work order never opens.
5. **If it fails:** use a clearer bottle or a tape backing behind the reservoir for contrast. Then add more stills at the levels that missed. As a last resort, fall back to 10% classes.

Put the error plot on a slide. A measured number from your own rig is stronger than a quoted one.

## Flow

```text
Pi camera ──jpeg──▶ runner (this machine) ──▶ Roboflow Inference :9001
                       │                         crop tank ─▶ liquid + reservoir detector
                       │                         full frame ─▶ person detector ─▶ filter to pad
                       │                         custom block: level, visits, tickets, dashboard
                       ◀──── dashboard + ledger ─┘
                       │
                       ▼
                   window (HMI), ledger.json
```

- **The Pi** captures stills and runs no model. It sends a still on a slow interval for the level, and a burst whenever something moves in the pad. It keeps each jpeg until the runner accepts it.
- **The runner** is the site server. It owns the shift ledger, the ticket list, and the strap table, and passes all three into each Workflow call. Each request is stateless. An `image_id` that was already processed is skipped.
- **Inference** runs locally on the free tier. Custom Python is enabled, and the port is bound to localhost.

## Events

`tol` is the delivery tolerance: twice the 95th-percentile error from the lab test, with a minimum of 5% of capacity.

A level is committed only when the `liquid` box's confidence is above the limit. A reading below the limit is `review`, and it changes nothing.

A visit opens after two stills with a person in the pad. It closes after two stills with no one there. While a visit is open, the level is frozen, because the attendant blocks the tank. When the visit closes, `before` and `after` are compared:

| When the visit closes | Event |
|---|---|
| `after − before` is more than `tol` | `delivery`, with the mL added |
| `before` at or below the refill line, no change | `no_change` |
| `before` at 50% or above, no change | `wasted_stop` |
| `after` is not confident | The visit stays open |

More rules:

- If the level rises by more than `tol` with no visit open, the event is `unattended` and the window shows `review`. Nothing is verified.
- If the level drains faster than the planned dose rate, the event is `fast_drain`, which points to a leak, theft, or a pump set wrong. Brewing a pot shows it live.
- A tank dropping to the refill line opens one work order. A delivery clears it.
- A ticket matches a closed visit on the same tank within a time window. It is verified if the observed amount is within `tol` of the billed amount. Otherwise it is unverified, and the difference is the disputed amount.

## Dashboard

The custom block outputs three numbers:

- **Tanks at or below the refill line**, with each tank's level in % and gallons.
- **Visits this shift**, broken down into deliveries, no-change visits, and wasted stops.
- **Estimated dollars:**

```text
disputed_gallons × $22
```

$22 a gallon is the price in [business-case.md](business-case.md). A visit with nothing added is counted in the visit line. It does not add a route dollar. A tank under 5% opens the same refill work order. It does not put a workover price on the screen. The pitch states that price out loud and leaves the rate off the payback.

## Model

- **Project type.** Object detection on a fixed crop of the tank, with two classes: `liquid` and `reservoir`. The same crop is applied to the training images and to the live frames.
- **Data.** About 100–150 settled stills spread across the full range, empty to full, not clustered at round numbers. Use the room and lighting you will demo in, and lock the camera's exposure. Draw the top of the `liquid` box exactly on the surface. That edge is the measurement.
- **Model choice.** RF-DETR Nano, or Small if Nano's edges are loose. Augment with brightness, exposure, light blur, and a little noise. Leave flips, rotation, and crop or shift augmentations off, because those move the edge being measured.
- **The error that matters.** A low tank read as high. The refill work order never opens. Check the error near the refill line separately.
- **The person model is not trained.** It is the public COCO RF-DETR Nano. Avoid YOLO, which needs a paid license to self-host commercially. The tank images are your own training data.

## Workflow

1. Relative Static Crop on the tank.
2. The liquid and reservoir detector on the crop.
3. The person detector on the full frame, filtered to `person`.
4. The custom block, `TankShift`. It takes the two boxes, their confidences, the people in frame, the strap table, the ledger, and the tickets. It returns the level, the dashboard, the event, and the new ledger.

The custom block is required because the built-in blocks can't turn a box edge into mL through a strap table, pair a visit with the level before and after, check it against a ticket, or keep a shift ledger.

## Demo (30 min)

| Min | |
|---|---|
| 0–6 | Read [business-case.md](business-case.md), in order: use case, market size, fault impact, financial cost. |
| 6–13 | Dataset, labeling the surface, augmentations, training, and the lab accuracy plot |
| 13–18 | The Workflow graph, the custom block, local Inference, the field hardware and connectivity plan |
| 18–26 | Live demo (below) |
| 26–30 | Read the calculated-value close in [business-case.md](business-case.md). The dashboard dollar should be about $2,760. A 5–10 gallon short is inside the error. A batch down the annulus is not this tank. |

The live demo, in order:

Say the reservoir stands in for a 335-gallon tank.

1. Brew a pot. The level falls through 25% and one refill work order opens. This is the tank heading for empty. It is not a multi-day stall, and it does not put $15,000 on the screen.
2. Refill with a visit. The ticket bills what was poured. It is verified. The level shows in mL and in gallons.
3. Bill 251 gallons, the refill from the quarter line to full. Pour about half of that. The ticket is unverified. Disputed gallons times $22 land near $2,760.
4. Walk up to a full tank. The visit added nothing. It is counted as a visit. It does not add a route dollar.
5. Stop capture, pour, and restart. The level rose with no person. The event is `unattended` and stays on review.

Backup: replay saved jpegs through the same runner.

## Open questions

- Is the surface clear in a still across the whole reservoir? Check this on the first night, before labeling. If it isn't, use a backing card or a clear jug.
- The field tank is 335 gallons, so the half-fill in the pitch is about $2,760. Measure the reservoir in mL on the first night.
- How long should the ticket match window be?
- What is the confidence limit? Set it from the validation set.
- Should the demo use the Pi or the laptop camera?
- The live dollar uses $22 a gallon and a 335-gallon tank, from [business-case.md](business-case.md). Route counts in the reference are background. They do not go on the dashboard.
