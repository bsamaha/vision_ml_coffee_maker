# Field engineering demo — use case notes

The tank build is specified in [tank-build-plan.md](tank-build-plan.md). Follow that file. Section 2 below is the earlier waterline sketch and is not the build.

Build the water-reserve tank, with a person logged when they show up. Alex Strang rejected the desk app for weak ROI and thin domain expertise. He later accepted a wrench board as straightforward to train. Discrete fill states on this tank are the same kind of training problem, and they are your customer. The wrench board stays the fallback he already approved.

What he said a submission has to show: domain expertise, business value, customer context, and training data you generated. The presentation order: use case, market size, fault impact, financial cost, the Roboflow demo, calculated value. The custom Python block is a shift dashboard. On this proof the three numbers are tanks under the refill line, visits this shift, and an estimated dollar impact. That is his missing-count dashboard, with chemical as the item.

The tank is not a carafe. It is the clear reserve. You label stills `full`, `half`, and `empty` from this camera. That is a small classification set, or one detection class per state. It does not depend on measuring a meniscus inside a box. A fixed camera and three states is a straightforward training run.

A person at the tank is the attendant. The block writes a visit when a person is in the frame, with the time and the tank state before and after. A visit where the state goes from `empty` or `half` to `full` is a delivery. A visit where the state does not change is a stop with nothing added, which is the disputed ticket. A change to `full` with no person is `review`. Do not train a `truck` class until this camera has frames of a vehicle. A COCO truck detector will call a passing car a delivery. In the demo, you walk into frame. You say the field object on that same event is the service truck.

The wrench board remains the demo if you want to show him exactly the prop he already called clear. It is one class and a named slot, and it does not use the route you ran. The switch, the bead, the books, and the sink valves do not have his yes.

Show the dollar figure as a calculation you can point at: tanks under the line, visits, and either gallons times a price or the cost of a dry tank. Say the plant number is an assumption. Keep a backup clip of the same pour and the same walk-up. The demo itself is live.

The build stays on the free Core plan and on this machine. One training run fits in the monthly credits. Self-hosted Inference is the deployment. The on-screen window is the HMI. A Vision Event or a local log line is the record. A PLC bit is the later plant version of the same fail output. PLC Writer and Deployment Manager need an enterprise plan, so they stay out of the build.

Own frames are the training set and the live scene. A Universe dataset is allowed only as extra images when the class and the camera angle match.

## Edge

A Raspberry Pi is the device at the station. It takes the still. This machine is the server. It runs the Workflow on local Inference. The Pi does not need a GPU. RF-DETR Nano on a Pi CPU may miss a kitting time limit, and a tank only needs a still every few minutes, so the split is the same either way: capture on the Pi, decide on the server. If a measured Nano run on the Pi fits the tank interval, the tank can later infer on the Pi. The demo does not depend on that.

The Pi keeps the jpeg until the server accepts it. A dead link does not drop the still and does not open a second work order for the same still. Cameras are cheap, so a second camera is normal. Two cameras are for redundancy, not for a second product. Each still carries `camera_id`. The Workflow scores each still. The custom block, or a few lines beside it on the server, applies one rule:

- Both readings are confident and close. Use the mean.
- One is `review` or missing. Use the other.
- They disagree, or both are `review`. Emit `review`. Do not call a truck and do not hold a kit.

The demo can show this with the Pi camera and one USB camera on that Pi, or with a second still from the laptop if the second camera is not plugged in yet. Say which one ran. A second Pi is the plant version of a second camera, not a requirement for the proof.

| | Kitting | Chemical tanks | Switch ports |
|---|---|---|---|
| Roboflow page | [Kitting verification](https://roboflow.com/ai/kitting-verification) | [Predictive maintenance](https://roboflow.com/ai/predictive-maintenance) and [analog gauge reading](https://roboflow.com/ai/analog-gauge-reading) | No named page. The job is an unmanaged closet |
| Buyer | Quality lead at the kit bay | Operator who pays the chemical ticket, and the company that drives the route | The person who gets the call when a line drops |
| Loss | A short kit stops a customer line, comes back, or is charged back | A ticket with no before-and-after level, and a truck that visits full tanks while another runs dry | A site visit for a port that was never linked, or a dark port nobody saw |
| False pass | A missing or wrong part and the station releases the kit | A delivery accepted with no pictures, or "enough left" and the tank runs dry | A port that should be up is dark, and no ticket opens |
| False fail | A complete kit is held | Glare or a stain sends a truck | A glare or a blink looks like a dead port, and someone rolls |
| Live move | Pull one part. The window names the line | Drop one level. A work order carries the frame. Refill. The after frame is the ticket | Unplug one cable. The window names that port |
| Score | 94 | 91 | 87 |

## 1 — Kitting verification

A camera over the tray checks the parts against the bill of materials. A weight check or a barcode on the bag cannot tell an M6 from an M8. The record is the image plus the missing line.

**Stand-in.** One overhead camera, one tray, parts a box can separate: a bracket, a nut, a washer, a long screw, a short screw. Two kit SKUs so the bill of materials is an input. `HINGE-A` wants the bracket, two long screws, and a washer. `HINGE-B` swaps in the short screws.

**Live moment.** Pull one long screw. The window names that line. Put it back. Switch the input to `HINGE-B` and show the same tray fail for a different reason.

**Model.** Object detection, RF-DETR Nano, one class per part. About 50 to 80 frames: complete, one missing, one extra, lamp on and off, a small nudge, a hand in frame. Augment brightness, exposure, and a little blur. Leave vertical flip off. COCO does not contain these classes.

**Custom block.** Compare counts to the active bill of materials. Output `pass`, `fail`, or `review`, the missing lines, and the extra lines. Below the confidence limit is `review`, which is how the two screw lengths stay honest. Hold the flag across a few frames so a hand does not flicker the station.

**Not in this proof.** Line rate, a second kit family, a PLC. `fail` holds the tote later, and the customer owns the reject timer. A second camera is the redundancy rule above, used when one angle hides a part. It is not a second model.

## 2 — Chemical tank level

On a beam pump the donkey head is the horsehead. A tank at the well feeds a chemical pump, often stroked by the walking beam. A service company gauges the tank and refills it. The operator gets a ticket. There is no product name from that contract to put on a slide.

| Class | Why it fits | Why a probe fails |
|---|---|---|
| Paraffin solvent | Dissolves wax in the tubing, on the rods, and in the flowline | Aromatic solvent swells seals. Wax coats what remains |
| Scale acid or scale inhibitor | Acid breaks existing scale. Inhibitor is the continuous inject | Acid eats a metal probe. Scale coats it |
| Corrosion inhibitor | The usual continuous inject. Published routes use 250 to 500 gallon tanks hours apart | Filming amine coats the probe, so the reading sticks |

Use paraffin solvent if the memory is that it broke a deposit down. Use corrosion inhibitor if the memory is a truck on a loop keeping wells clean. The camera never touches the fluid.

A pad often has more than one of these tanks. Each has its own ticket and its own dry-tank failure. The route is priced in stops and miles. One workflow covers the program. Do not multiply one chemical's spend by the number of classes. The unit of value is the tank-visit and the gallons on the ticket.

**Stand-in.** The coffee maker's water tank is one translucent chemical tank. A second clear bottle in the same frame is the second tank on the pad. The camera takes a still on an interval, the way a remote well sends a snapshot.

**Live moment.** Both tanks full, no work order. Pour or brew one of them past the limit. The window names that tank, shows the percent, and opens a refill work order with the frame. Refill it and keep the after frame. Then a glare frame or a hand on the tank is `review` and does not call a truck.

**Model.** Object detection, RF-DETR Nano, one class for the meniscus. About 40 to 60 frames, both tanks, empty to full, lamp moved, one glare frame, one hand. Augment brightness and a little blur. Leave rotation off. The camera stays fixed.

**Custom block.** Each tank is a named rectangle. A meniscus counts for a tank when its center lies inside that rectangle. Height between that tank's empty mark and full mark is a percent. Under the limit, that tank is `fail` and the block emits a refill request for it. The other tank can stay `pass`. No meniscus in a rectangle, or a meniscus on the line between two rectangles, is `review` for that tank and does not emit a request. The insight is the work order plus the before image and the after image.

**One camera, several tanks.** This is the pad. The block, not a second camera, separates the tanks. The new failure is a line assigned to the wrong tank. Rectangles that overlap, or a tank hidden behind another, are `review`. Say that a stained or dyed tank can need its own empty mark and full mark. A second camera is the redundancy rule in the Edge section. It agrees, fills in, or refuses. It does not average a glare frame into a truck roll.

**Pressure gauge, for a tank you cannot see through.** Hydrostatic pressure at the bottom is the level when the density is known. A mechanical gauge on a tap is the instrument. The camera reads the dial, so the site does not wire a transmitter. Train needle base and needle tip, and the same block maps the angle through that tank's calibration into a percent or a head. Density is part of the calibration, and it changes with the chemical, so each gauge has its own scale. The gauge is still wetted through the tap, so the chemical can still destroy the bourdon tube. The camera is what survives. Do not plumb a gauge into the coffee maker. Use this path only if an analog gauge you can turn is in the scene, and say it stands for an opaque tank. A fire-extinguisher gauge will not move unless you discharge it.

**Not in this proof.** A fleet, a real invoice, or a truck. One frame, one tank crossing, one refill. The plant version stores the percent on an interval, calls the route only for tanks under the limit, and attaches the two images to the delivery ticket.

## 3 — Switch port lights

The switch under the desk is unmanaged. It has no IP, no SNMP, and no port table anyone can query. The LEDs are the only status. A lit LED means the cable is linked at both ends. On most small switches the same LED blinks when frames pass, and it is dark when the link is down. Confirm that on this switch before the demo. One still cannot see a blink. The Pi takes a short burst, three or four frames a second apart, and sends the burst to the server.

Pitch this as a closet, a cell, or a remote cabinet full of unmanaged switches. A datacenter core switch already answers this with SNMP. Say that in the first minute, or the room will stop you. The camera is for the switch that has no management plane. The same pattern covers a managed switch whose management port is the thing that died.

**Buyer.** The person who dispatches a tech when a line drops, in a plant network or a branch closet.

**Loss.** A visit for a port that was never linked, or a port that should be up and has been dark since yesterday. A false pass leaves a required port dark with no ticket. A false fail sends someone because a reflection looked like a dead LED.

**What "open" means.** A dark port is not automatically a fault. Spare ports are supposed to be dark. The block holds a list of ports that must be up, the same role a bill of materials plays for a kit. Dark and required is `fail`. Dark and spare is free capacity, and the window can say so. Lit and not on the list is a port in use that nobody recorded. The LED cannot tell you the VLAN, the error count, or what device is on the far end. Do not claim those.

**Stand-in.** This switch, the Pi framed on the faceplate, cables you can pull. Label the ports in the block as they are printed on the switch.

**Live moment.** Start with two cables linked. Pull one. The window names that port and opens one ticket with the burst. Seat the cable. The ticket clears. Then cover one LED with a finger. That port is `review`, and it does not page anyone.

**Model.** Object detection, RF-DETR Nano, one class for a lit LED, or a class per port if the faceplate is stable enough to crop. About 40 frames: linked, unplugged, a hand, the room lamp moved. Augment brightness. Leave rotation off. The camera stays fixed.

**Custom block.** Each port is a named rectangle. Across the burst, a rectangle that stays dark is down. A rectangle that stays bright is linked and idle. A rectangle that changes bright to dark inside the burst is passing traffic. Required and down is `fail` and one ticket. Idle on a required port can be `pass` or `review` depending on whether that link should be talking. You pick that with the person in the room. One event per state change, not one event per burst. Their question about a plug that is in but not working is the idle-versus-down distinction, and it only exists if this switch shows a steady link light when traffic stops. If the LED is dark unless frames are flowing, say that, and treat dark-while-cabled as the fault you can see.

**Not in this proof.** SNMP, a MAC table, or a second closet. One switch, one pulled cable, one ticket.

## 4 — Three more from a home prop

[Plant vision](912f79f4-99b2-448f-89ac-258ac3694c5e), [home sensors](e735c3c4-c498-428b-ae94-a64b43a80d38), and [field props](2d4ef5c4-b2da-4765-92cf-ca96de3512af) looked for jobs outside the three proofs above. These three survived. A floor-register economizer and an oil stain that must grow were real and harder to show honestly on Zoom, so they are not in the set.

### Sealant bead

A robot lays a bead of adhesive or gasket. A skip in that bead leaks after the joint closes. Roboflow sells this as [adhesive and glue bead inspection](https://roboflow.com/ai/adhesive-and-glue-bead-inspection).

**At home.** Black poster board, a closed rectangle of toothpaste or school glue, a quarter in the corner for scale. The Pi looks straight down.

**Live moment.** Wipe one side with a finger. The window shows the skip length and `fail`. Smooth the bead back. It passes.

**Custom block.** Walk a saved path. Find the longest run with no bead. Convert that run to millimeters from the quarter (24.3 mm). Fail when the skip exceeds the limit. Glue off the path does not fill the skip.

**False pass.** A thin smear still bridges the wipe. **False fail.** A shadow splits a sound bead. Do not claim bead height, volume, or a watertight joint.

### Valve lineup

Before a line is opened, the valves on that path have to sit in one combination and hold there. Roboflow sells [valve inspection](https://roboflow.com/ai/valve-inspection). A round knob looks the same open or shut, so it cannot be the prop.

**At home.** The two lever stops at a washing machine, or the pair under the sink. The Pi sees each lever against its pipe. The step requires both levers across the pipe.

**Live moment.** Leave one lever in line with the hose. The step stays `fail`. Swing the second lever and hold both still. The step passes. Crack one back. The pass drops.

**Custom block.** Each lever is open, closed, or partial. Pass only for the required combination, and only after that combination holds across the burst. One frame of the right pose does not sign the step.

**False pass.** A half-open lever looks perpendicular from the Pi, or the handle was installed a quarter-turn off. **False fail.** A low angle makes a closed lever look diagonal. Lever angle does not prove the line is depressurized.

### Panel gap

A door, hood, or panel is rejected when the opening is wide or when it tapers. Roboflow sells [gap and flush inspection](https://roboflow.com/ai/gap-and-flush-inspection). This camera sees the width of the opening. It does not see which panel sits proud.

**At home.** Two hardcover books or two cereal boxes on edge, seam toward the Pi, a quarter in frame.

**Live moment.** Slide the top of one book out so the seam is tight at the bottom and open at the top. The window shows both widths and `fail`. Square the books. It passes.

**Custom block.** Measure the gap at two stations along the seam. Convert pixels with the quarter. Fail if either width, or the difference between them, exceeds the limit.

**False pass.** The Pi sits off to the side and foreshortens a wide gap. **False fail.** A shadow beside the seam is measured as opening.

## Scoring

The brief grades technical expertise, communication, presentation, and problem-solving. Each cell is an integer from 1 to 5. Total = (sum of score × weight) / 5.

| Criterion | Weight | A 5 |
|---|---|---|
| Prospect story | 20 | A named buyer and a named loss, false pass before the model |
| Live moment | 20 | One motion changes the window on a Zoom share |
| Custom block | 15 | The decision needs this code |
| Training choice | 15 | These classes are not COCO |
| Ease of building | 15 | Shared local Inference path, one model, one window |
| Debrief you can show | 15 | The attack has a frame |

Ease is the nearest integer to the mean of code, infra, and architecture. A 5 there is the easy end. The shared path is a free workspace, one training run, Docker Inference on this machine, a Raspberry Pi taking stills, one window, and one event.

| Idea | Code | Infra | Architecture | Ease |
|---|---:|---:|---:|---:|
| Kitting | 4 | 4 | 4 | 4 |
| Chemical tanks | 3 | 4 | 3 | 3 |
| Switch ports | 4 | 4 | 3 | 4 |
| Sealant bead | 3 | 4 | 3 | 3 |
| Valve lineup | 4 | 4 | 4 | 4 |
| Panel gap | 3 | 4 | 3 | 3 |

Kitting compares counts to a document. The chemical block owns the rectangles, the empty and full marks, the per-tank work order, and the two-camera rule. The switch block owns the port list and the burst. The bead and the gap each own a measurement along a path. The valve lineup owns a combination that must hold. The Pi is capture for all of them.

| Idea | Story 20 | Live 20 | Block 15 | Training 15 | Ease 15 | Debrief 15 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Kitting | 5 | 5 | 5 | 5 | 4 | 4 | 94 |
| Chemical tanks | 5 | 5 | 5 | 4 | 3 | 5 | 91 |
| Switch ports | 4 | 5 | 5 | 3 | 4 | 5 | 87 |
| Sealant bead | 5 | 5 | 5 | 4 | 3 | 4 | 88 |
| Valve lineup | 5 | 5 | 4 | 4 | 4 | 4 | 88 |
| Panel gap | 5 | 5 | 5 | 4 | 3 | 3 | 85 |

Kitting debrief is 4 until both screw lengths are in the tray. Chemical debrief is 5 because you can show a glare frame that must not call a truck, and a meniscus on the boundary between the two tanks. Switch story is 4 because a managed datacenter switch already has SNMP, so the buyer is the unmanaged closet. Training is 3 because a brightness check inside a rectangle is close to the whole model. Debrief is 5 because you can unplug a cable, cover an LED, and explain a blink. Bead and gap debriefs stop at the image plane: no bead height, no flush. Valve debrief stops at the handle: the line can still be pressurized.

Build kitting if the room should recognize a page Roboflow sells. Build the coffee-maker tanks if the room should hear the route. Build the switch if the room should see a port go dark on a switch that has no IP. Build the bead if the room should see a skip measured in millimeters. Build the valve lineup if the room should see a step wait until both handles hold. Build the panel gap if the room should see a seam taper.

## Panel

Three judges scored the written plan. They ignored the totals above. [Prospect](1d3e0f3f-7cef-45e4-87b5-9dab2b6ef401) buys a change to a release, a truck, or a ticket. [Platform](644778c0-2074-4afd-934a-46db59afbe29) grades training, a block the built-ins do not already do, a free-tier action, and what the proof refuses to claim. [Demo day](4d991b05-9715-43f5-8399-edba14d04ff6) grades a live Zoom share, a two-week build, and a miss that still teaches.

| Idea | Prospect | Platform | Demo day |
|---|---:|---:|---:|
| Kitting | 17 | 16 | 14 |
| Chemical tanks | 15 | 14 | 17 |
| Switch ports | 17 | 11 | 15 |
| Sealant bead | 6 | 13 | 13 |
| Valve lineup | 10 | 10 | 12 |
| Panel gap | 8 | 12 | 12 |

Bead, lineup, and gap are out. Toothpaste on poster board and two books read as a school project. A sink valve the prospect can already see does not sign a lineup.

The choice is kitting or the tanks. The switch is the spare if the prop fails the night before, not the main show. Port LEDs are a few millimeters on a Zoom share, and the first question is SNMP.

Kitting is the page they sell, and the sentence in the first two minutes is that a scale cannot tell the long screw from the short one. The question that kills it is to leave the order on `HINGE-A` and put the short screws in the tray. A missing part is not enough. The low-confidence screw has to be `review`, and that review has to suppress a missing-line fail, or the same object fails the kit twice. One still has no previous frame, so a hand-debounce cannot live only inside that request.

The tanks are the story only he has. The demo is one drop, one refill, one glare frame that does not call a truck. A percent is only as good as the waterline a stranger can point at by day three. If the coffee reservoir is a dark mold, use the clear bottle. The before image and the after image are two requests. The Pi keeps the first still. The block on a single request cannot.
