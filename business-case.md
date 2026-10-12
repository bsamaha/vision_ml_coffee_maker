# Chemical tanks at Company X's wells

## Summary

Company X injects treatment chemicals into its wells from small tanks on each site, and it has two problems with them:

1. **Billing it can't verify.** A truck refills each tank and leaves a ticket, and nothing independent checks the ticket against what was delivered.
2. **Treatment interruptions it can't see.** If a tank runs dry or its pump stops, the well goes untreated. The chemical tanks are often still unchecked even when the well itself is on SCADA, so a stopped pump can sit until the next pumper or chemical-tech visit (days to weeks) while the steel corrodes, until the well has to be shut in and repaired.

A camera running a Roboflow model on site logs the tank level and every visit, all day, which addresses both problems. It turns days or weeks without treatment into under two weeks. A site costs about $600 to equip (about $1,025 off-grid) and about $25 a year in cellular data to run, plus one Roboflow plan for the whole fleet. The failure that an unnoticed interruption leads to costs about $56,850 on a high-rate well, enough to equip about 94 sites. The billing records and the site photos add value on top of that, but they can't be measured in advance, so they aren't counted.

## The problem

Company X is one of the largest oil producers in the Permian Basin (West Texas and southeast New Mexico), with hundreds of new wells coming online this year.

Each well has one to three tanks beside it, each holding one chemical that a small pump injects into the well continuously. The tanks are on ESP, gas-lift, rod-pump, and flowing wells. Lift type does not decide this. What does is whether anyone already watches the chemical skid. A pad can have an RTU on the well and still leave the tanks to the treatment vendor, which is still common, including on large Permian fleets ([Detechtion](https://www.detechtion.com/hubfs/Chemical-Injection-Monitoring-and-Control-2.pdf)). That RTU often has no spare input and no legal place to add a tank-top sensor. The camera mounts on a pole and does not use the RTU.

- **Billing.** A treatment company's truck refills the tank and leaves a ticket. A ticket can bill for a full refill when only half was delivered, and today nobody can tell.
- **Treatment interruptions.** The treatment stops if the tank runs dry or the pump stops working, and either one has the same result. A stopped pump can sit until the next pumper or chemical-tech visit, typically days or weeks. Without corrosion inhibitor the steel in the well corrodes and eventually fails. A crew has to pull the pipe to repair it, and the well sells no oil while it is down.

This case covers corrosion inhibitor only, to keep the numbers simple. Scale inhibitor and other chemicals on the same pad are covered by the same camera at no extra cost.

### Two example wells

The camera and the box are the same at every well. What changes is how much chemical the well uses and how much oil is at stake, so the case uses two wells at the ends of the range. The fast well is an older Delaware Basin well, and the slow well is a typical low-rate US well.

| Input | Fast well | Slow well | Source |
|---|---|---|---|
| Oil | 50 barrels a day | 2.4 barrels a day | Assumption; [IOGCC](https://oklahoma.gov/content/dam/ok/en/iogcc/documents/publications/2010marginalwell.pdf) |
| Water per barrel of oil | 7 | 3 | [Wood Mackenzie](https://www.woodmac.com/press-releases/permian-produced-water/); assumption from [Permian Produced Water](https://www.permianproducedwater.com/basics.html) |
| Corrosion inhibitor dose | 50 ppm of oil plus water | Same | |
| Chemical price | About $22 a gallon | Same | [SWPSC 2015](https://www.swpshortcourse.org/paper/2015025-improving-paraffin-treating-modernizing-chemical) |
| Tank size | 335 gallons | 125 gallons | |

The dose applies to all the fluid the well produces, so daily use is `(oil + water barrels a day) × 42 × 50 ÷ 1,000,000` gallons:

- **Fast well:** 400 barrels of fluid a day uses about 0.84 gallons a day, about $6,750 a year. A tank lasts about ten months between refills.
- **Slow well:** about 9.6 barrels of fluid a day uses about 0.02 gallons a day, about $160 a year. A tank lasts for years.

## The solution

### Why a camera

A probe inside the tank does not hold up. Corrosion inhibitor leaves a film on it, acid eats metal, and wax or scale coats whatever survives. Non-contact sensors avoid those problems, and they already exist: [intrinsically safe radar](https://www.flowline.com/oil-well-chemical-tank-80-ghz-radar-level-sensor/) has been used on exactly these tanks, at about [$2,600 per tank](https://www.dwyeromega.com/en-us/intrinsically-safe-radar-level-transmitter-for-corrosive-media/p/LR11), and ultrasonic monitors sell for about [$299 plus $10 a month per tank](https://meterrasystems.com/solutions/chemical-dosing-tank-monitoring/).

A camera is the better choice for three reasons:

1. **It records who was at the tank, with photos.** A level sensor can show that the level rose. Only a camera can show who filled the tank and when, with an image that settles a dispute.
2. **One camera covers every tank on the pad.** Radar on three tanks costs about $7,800. Three ultrasonic monitors cost about $900 plus $360 a year. The camera covers the whole site for about $600.
3. **It sees the rest of the site.** The same images can show spills, leaks, and unauthorized visits.

### How the camera reads the site

Every few minutes, the site computer takes a frame and runs a small Roboflow model on it, such as RF-DETR Nano. The model does two jobs:

- **Tank level.** The model finds each tank and the liquid line inside it. The level is the line's height as a fraction of the tank's height, and each tank's strapping table (its chart of height to gallons) converts that to gallons. This depends on seeing the liquid. Many chemical tanks are translucent poly, where the liquid line shows through the wall. Opaque tanks need a sight gauge the camera can see.
- **People.** The model detects any person in the frame. It logs that someone was there, not who they are. A person with the tank still in the picture is a visit, and that visit does not bill. On a pad the tank stays put, so a delivery is a rise in level while a person is there, and the ticket is checked against the gallons that rise shows. A half-fill from the 25% line on the 335-gallon tank is about $2,760 at about $22 a gallon.

The same frames show whether the pumpjack is moving, by comparing consecutive frames. Spills can be added later as another class, trained on images from the deployed cameras.

In the field the models and the gauge run as one Roboflow Workflow on Roboflow Inference on each site computer: the tank model, the person model, and a custom block that turns the boxes into gallons. The site computer keeps the log and the rules that need memory, such as what counts as a fill. This proof already runs that way. Its Pi runs the tank model, the person model, and a TankGauge custom block as one Roboflow Workflow, in the board's own process with the `inference` library, no Docker and no cloud call per frame. The same Workflow is saved in the Roboflow app. Section 8 of [technical-solution.md](technical-solution.md) has the details.

### What it records

The camera keeps a continuous log. Each entry is a time, the booked level, and whether a person is present.

In the kitchen proof the tank is a coffee maker's reservoir, which is lifted off to be refilled, so a fill looks like this:

| Moment | What the frame shows | Booked level |
|---|---|---|
| Taken | The reservoir has been missing for two ticks, and a person was on one of them or was seen just before it disappeared | Ounces saved when it left |
| Return | The reservoir is back, a liquid line is present, no person is in the picture, and the line is at least 3.5 fl oz higher | 70 fl oz |

The model reading is stored beside the 70. The coffee bill uses 70 minus the saved ounces, at $0.50 a cup (5 fl oz). From the alarm, about 16 fl oz, that bill is about $5.40. From empty, as in the 11 October rehearsal, it is $7.00.

- **Ounces used.** The page sums the booked ounces that fell, in the last 15 minutes and today. A rise, including the jump to 70, adds 0, and a wobble of up to 2 fl oz is not counted twice. In the rehearsal a full tank brewed to empty read 70.0 fl oz used, exactly what went in. There is no weekly rate.
- **Use rate and time to empty.** The page shows the net fall per minute over the last 2 minutes and how long the tank lasts at that rate. On the well, the same rate over days is the consumption baseline the stopped-pump check compares against, and the time to empty is when the next delivery is due.
- **Anomalies.** A day with little or no drop means the treatment may have stopped. A low level means a refill is due. A rise while nobody took the tank updates the level after the quiet-jump hold, and it does not bill.

The photos and the log belong to Company X. The model runs on the site computer. On this proof the newest 8 frames stay on the Pi, each with the boxes the models found, and the board draws the reservoir, water line, and person boxes over the photo. The well product would send the log and the fill photos.

### The insights

| Insight | On the proof | On a pad |
|---|---|---|
| Tank level, with photo evidence | Live level, a tank gauge, and the model's boxes on the photo | Level per tank, in gallons from its strapping table |
| Refill due | The refill alarm under 25% | An alert before the well goes untreated |
| Consumption | Used in the last 15 minutes and today, the use rate, and the time to empty | The baseline that shows a stopped pump as a rate gone flat, and the next delivery date |
| Visits | Every person logged with a time and a photo | A visit record for every pumper and vendor |
| Deliveries | Each refill booked with its bill | Each ticket checked against a fill event |

On the proof these appear on the board, the operator screen. Sending them out, as an alert to a phone or into the operator's SCADA system or historian over MQTT, is the field design and is not built in the proof.

### How long a well can go untreated

A continuously injected inhibitor [stops protecting the steel within hours](https://www.icmt.ohio.edu/documents/AMPP2022/C2022-18056.pdf) once injection stops. From then on, untreated carbon steel in CO₂-laden brine corrodes at about 3.5 mm a year in the lab, and field rates can be [several times higher](https://kpt-bj.com/ampp-paper-18205-2022-enabling-carbon-steel-with-a-special-dense-co2-corrosion-inhibitor-a-field-study-1084979212.html). Typical 2⅞-inch tubing has a wall about [5.5 mm thick](https://www.sciencedirect.com/science/article/abs/pii/S1350630715301680). At the conservative 3.5 mm a year:

| Untreated for | Tubing wall lost |
|---|---|
| 3 days | ~0.5% |
| 2 weeks | ~2.4% |
| 1 month | ~5% |
| 3 months | ~16% |
| 10 months (until the next refill) | ~53% |

So a short interruption does little damage. Long ones, the kind nobody notices on a remote site, are what cause failures. These figures come from lab conditions with CO₂ only. Many Permian wells also contain H₂S, which changes the rates.

### How fast it catches a stopped pump

A dry tank is easy to catch, because the level is low. A stopped pump is harder, because the camera has to notice that the level *isn't* falling. The camera can only be sure the treatment has stopped once the missing usage is larger than its reading error:

`days to detect = level reading error (gallons) ÷ daily use (gallons a day)`

The field reading error still has to be measured on real tanks. The kitchen proof measured 2.4% of full between 4 and 10 cups (see the proof of concept below), which shows the method can get there, but a clear reservoir indoors is the easy case. So the useful question is how accurate the camera needs to be. The target is **about 3% of the tank's height**. On the fast well's 335-gallon tank, which uses about 0.84 gallons a day, that is about 10 gallons, so a stopped pump is caught in about 12 days and the wall loss is held to about 2%. That is far better than the days or weeks an interruption can last today. On the slow well, which uses about 0.02 gallons a day, no realistic camera accuracy catches a stopped pump in a useful time.

Zero consumption isn't always a fault. When a well is shut in, its chemical pump often stops too. On a pumpjack well, the same camera can see whether the pumpjack is moving and suppress the alert while the well is down. On other wells, the well's running status has to come from the operator's SCADA system.

### Optional upgrade: a precision level sensor

Where faster detection is worth extra hardware, a wired ultrasonic level sensor can be added to each tank as a precision input to the vision system. Ultrasonic sensors read the level without touching the liquid, to about [±3 mm](https://kyueinstruments.com/level-sensor-price-guide/), which is roughly 0.2% of a 335-gallon tank's height. Chemical vapor and foam can disturb the reading, so the sensor should be chosen for the chemical. It catches a stopped pump on the fast well in about a day instead of about 12, and on the slow well in roughly a month instead of never.

The sensor plugs into the site computer's RS-485 serial port, so it uses the box's existing cellular connection. There's no per-tank modem and no monthly fee like the [$10 a month](https://meterrasystems.com/solutions/chemical-dosing-tank-monitoring/) that standalone monitors charge. Industrial ultrasonic sensors cost about [$150–$1,500](https://kyueinstruments.com/level-sensor-price-guide/) each, more if the tank top is in a classified hazardous area.

The camera stays the core of the system. The sensor gives the level reading more precision. The camera still records who filled each tank, keeps the photo evidence, watches the pad for spills, and sees whether the pumpjack is running. The two readings also check each other: if they disagree, one of them needs attention.

The sensor is only an option if there is a spare port on this box or on the site RTU, and a legal place to mount it on the tank. If the existing RTU is full or the tank top is in a classified area, skip the sensor. The camera is then the whole retrofit.

## Costs

### Hardware per site (one-time)

A site needs a camera, a small computer to run the model, and a cellular connection. A GPU isn't necessary. The model reads one image every few minutes, and RF-DETR Nano takes about [0.7 seconds per image on a Raspberry Pi 5 and about 2.2 seconds on a Pi 4-class chip](https://camertronix.com/benchmarking-yolov9-and-rf-detr-on-pi-4-and-5/). Roboflow's inference server [supports both](https://inference.roboflow.com/install/raspberry-pi/). This proof measured about 1.6 to 1.9 seconds per RF-DETR Nano pass on its Raspberry Pi 4 CPU at 1280×720, running two models in a Roboflow Workflow every 7.5 seconds at about 50 to 60% CPU and 62 °C, with about half the Pi's 4 GB of memory free.

| Part | Price | Source |
|---|---|---|
| Fanless industrial computer (Seeed reComputer R1100, Raspberry Pi CM4, rated −30 to 70 °C) | $322 | [Seeed](https://www.seeedstudio.com/reComputer-R1126-10-p-6963.html), [specs](https://wiki.seeedstudio.com/recomputer_r1100_intro/) |
| Outdoor PoE camera (Reolink RLC-510A) | $60–$70 | [Amazon](https://www.amazon.com/Security-Detection-Assistant-Recording-RLC-510A/dp/B08F568BH1), [Newegg](https://www.newegg.com/reolink-rlc-510a-bullet-camera/p/2P0-0059-000D0) |
| LTE modem | ~$100 | Estimate |
| Mount, enclosure, cabling | ~$50–$100 | Estimate |
| **Total with site power** | **~$530–$600** | |
| Off-grid solar (Voltaic 25 W kit) | from $425 | [Voltaic](https://voltaicsystems.com/25-watt-core/) |
| **Total off-grid** | **~$955–$1,025** | |

Notes on these costs:

- **The camera's heat rating needs checking.** The Reolink is a consumer camera, so it should be checked against Permian summer temperatures before deployment. An industrial camera such as the [Axis M2036-LE](https://www.cdw.com/product/axis-m2036-le-network-surveillance-camera-bullet/7058347) adds about $400.
- **Off-grid sites need duty cycling.** The computer and camera together draw about 7–8 W if they run all the time, which is more than a 25 W panel produces averaged over a day. Off-grid boxes should wake every few minutes, take a photo, run the model, and sleep. They have to wake more often than a visit lasts, so no fill is missed. Otherwise they need the larger panel the kit supports.
- **Mount the camera outside the hazardous area.** If the camera has to sit inside a classified area around the wellhead or tank vents ([API RP 500](https://www.api.org/products-and-services/standards/important-standards-announcements/rp500article)), an explosion-proof camera costs [$3,200](https://cms.intrinsicallysafestore.com/product/ivc-amz-hd41-3-explosion-proof-cctv-camera/) or more. Mounting it on a pole outside that area, looking in, avoids the cost. The operator's area-classification drawing decides where the line is.
- **Installation isn't included.** It needs a quote.

### Running costs per site (yearly)

| Item | Cost | Source |
|---|---|---|
| Cellular data (10–25 MB a month) | ~$21–$28 a year | [Hologram](https://www.hologram.io/pricing/) |
| Roboflow inference on the site's own hardware | Free | [Roboflow pricing](https://roboflow.com/pricing) |
| **Total** | **~$25 a year** | |

The model runs on the site's own computer, so running it uses no Roboflow credits. In the field design the log goes into the operator's own systems, such as its SCADA system or data historian over MQTT, so no Roboflow-hosted storage is needed either.

### Roboflow costs for the fleet

Roboflow's charges come from managing the model, not from running it at each site:

- **Retraining.** The model will need occasional retraining as new tank types, seasons, and lighting conditions come up. Training costs [1 credit per 30 minutes of GPU time](https://roboflow.com/credits), and credits cost $4–$6.
- **Training images.** Only the images used for retraining are uploaded and stored.
- **A platform plan.** One plan covers the whole fleet. Managing hundreds of edge devices would likely need the Enterprise plan's deployment manager, which is custom-priced and not included here.

## Business value

### Treatment interruptions: one event pays for many sites

A long, unnoticed interruption eventually leads to a failure, and that failure has a cost that can be estimated. The useful question is how many sites the cost of one failure would equip.

| Input | Fast well | Slow well | Source |
|---|---|---|---|
| Days a failed well is down | 7 | Same | Assumption |
| Oil price | About $91 a barrel | Same | [FT](https://markets.ft.markitdigital.com/data/commodities/tearsheet/historical?c=WTI+Crude+Oil) |
| Repair (pulling the pipe) | $25,000 | $10,000 | Assumption |

The oil price is front-month WTI, which settled at $91.49 on October 8, 2026. Company X receives somewhat less after transport, so the lost-oil figures are slightly high.

One failure costs the repair plus seven days of lost oil (`oil rate × 7 × $91`), using the oil rates of the two example wells:

| | Fast well | Slow well |
|---|---|---|
| Repair | $25,000 | $10,000 |
| Lost oil | $31,850 | $1,530 |
| **One failure** | **$56,850** | **$11,530** |
| Sites equipped, with site power (~$600 each) | **~94** | **~19** |
| Sites equipped, off-grid (~$1,025 each) | **~55** | **~11** |

Running costs are small next to this. One fast-well failure also covers about 2,000 site-years of cellular data.

### Where this holds and where it doesn't

On the fast well, the camera can actually prevent the failure. The low-level alert catches a tank before it runs dry, and at the 3% accuracy target the consumption baseline catches a stopped pump in under two weeks. That keeps the wall loss from an interruption to a percent or two, instead of the 16–53% a three- to ten-month interruption would cause.

On the slow well, a failure is expensive, but the camera does little to prevent it. The tank holds enough for years, so it rarely runs dry, and a stopped pump can't be detected in a useful time. The slow-well figure shows what an interruption costs, not what the camera saves, so slow wells should be equipped for the other benefits below. The precision level sensor would bring a slow well's detection down to about a month, if the operator wanted that protection too.

The two wells are rate examples. Which real pads they map to depends on whether the chemical skid is already watched, not on the lift type:

- **Core.** Chemical tanks with no tank or pump telemetry. The well may already have SCADA. Both problems apply, and this is what the 94-site number is for.
- **Already monitored.** Tank-level or pump monitors are already sold into some high-rate pads. Interruption is covered there. The camera is still the billing and pad record, so do not sell the failure number as the reason to buy.
- **Low-rate.** Interruption stays weak without the ultrasonic upgrade. Billing, visits, and spills still apply.

### Benefits that aren't counted

These add value, but they can't be measured before the cameras go up, so they're left out of the figures above.

- **Billing.** Once cameras are watching the tanks, short fills will likely stop, so they can't be measured afterward either. There was no record before. The value is in deterring short fills and in every ticket being checked against a fill event. For scale, the fast well spends about $6,750 a year on corrosion inhibitor, and none of it is verified today.
- **Spills and environmental audits.** Spill penalties depend on how long the spill lasted as well as how much spilled. The Railroad Commission's penalty guidelines add [$100–$2,000 for each month out of compliance](https://www.sos.state.tx.us/texreg/archive/September52025/tables-and-graphics/202502988-1.pdf), under a ceiling of [$10,000 a day](https://statutes.capitol.texas.gov/Docs/NR/htm/NR.81.htm#81.0531). On a remote site, nobody can show when a spill started. In practice its duration runs back to the last time someone saw the site and can show there was no spill, which can add a month or more. If the camera sees the whole pad, the images show when the spill actually started. That gives the regulator a definite date and shortens the penalty period.
- **Visit records.** Every visit by a pumper, vendor, or anyone else is logged with a time and a photo.
- **Better delivery scheduling.** Company X can share tank levels with its treatment company, so trucks come when tanks are actually low instead of on a fixed schedule. That means fewer runouts and fewer wasted trips, which Company X can use in its next negotiation with the vendor.

## The proof of concept

The lab setup is a Ninja coffee maker's 70 fl oz reservoir, not a small copy of the well. A brew empties that reservoir, and a pad's pump does not, so the kitchen shows the mechanics: reading the level, logging visits, booking refills, and raising the alarm. It does not show field accuracy. The live demo and its talk track are in [presentation.md](presentation.md).

The error is the average absolute difference, in percent of full, on cup-line fills at or above 25%. Under 25% full is the refill alarm. There is no pass line. The 3% field target above is for the well, not the kitchen.

The accuracy experiment recorded three rounds of 4, 6, 8, 10, and 14 cups. Each round was scored with a cup table built from the other two, so no round grades itself:

- **4 to 10 cups:** an average error of **2.4% of full** over 12 readings, worst 12.1%. Nine of the twelve were within 1.5%.
- **14 cups, a full clear tank:** the weak point. In two of three rounds the model read it as about 74% full. The surface of clear water at the very top is hard to see. The 11 October rehearsal hit it once, a refill frame that read 52.5 of 70 fl oz.

The ledger is built around that weakness. A refill books 70 fl oz whatever the model reads, the highest settled reading after the refill becomes the full mark, and later readings are scaled to it, so an empty tank still reaches 0 and the alarm still fires. On the well, a tank that sits full after delivery is the same case, and a strapping table calibrated on site at the top of the tank would be part of commissioning.

In the 11 October rehearsal a full tank was taken, refilled, and brewed to empty. The board booked the refill at $7.00, showed Brewing for the whole brew, raised the alarm at 17.4 fl oz, and ended at 0 fl oz with 70.0 fl oz used, exactly what went in.

The models run as a Roboflow Workflow with Roboflow Inference on a Raspberry Pi 4's CPU: about 1.6 to 1.9 seconds per model, a reading every 7.5 seconds, at about 50 to 60% CPU and 62 °C. On 348 saved rehearsal frames, the Workflow agreed with the earlier in-process models within 1 fl oz on 329 of 336 readings and on every person flag, and where they differed by more, the Workflow was right.

A clear reservoir indoors will read more cleanly than a tank outdoors. Outdoor accuracy, summer heat, and uptime on solar still have to be confirmed on real tanks. The Pi in this kitchen already reached 79 °C at full load indoors before its camera feed was trimmed, so heat in a Permian enclosure is a real design input.

On the well, the 3% target is what makes one prevented failure pay for the hardware across dozens of sites. The kitchen measured 2.4% of full between 4 and 10 cups. That is not the field number, and the full tank still needs the ledger's help.
