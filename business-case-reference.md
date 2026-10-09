# Chemical tank route audit — reference

Sourced backup for the pitch in [business-case.md](business-case.md). Do not read this in the room. Open it when someone asks for a table.

The pitch prices one device over a five-year planning life. That life is a replacement budget for heat, the camera, and the radio. It is not a measured mean time between failures. A stripper can produce for 25 years or more. The box will not, and a replacement has to pay for itself again.

All assumptions are set for Permian Basin operations, both Delaware and Midland. Numbers marked *assumption* are estimates. Replace them with numbers from the Oxy route where you remember them, and say which ones are from memory.

## What the pitch defends

The pitch in [business-case.md](business-case.md) is Company X, the Permian operator with the brand removed. It prices one Delaware pad late in life on rod lift: a half-fill of about $2,760, a $25,000 pull, and about $31,850 of deferred oil for seven days at 50 barrels a day and about $91 a barrel. The $91 is the November 2026 WTI settlement of $91.49 on October 8, before basis. The national well census, the chemical-company resale, and WellAware are out of the spoken case. There is no frequency in the payback. Darby is SWPSC 2015, paper 2015025. The old `/ppdl/65` link is dead.

## Use case

### The site

A rod-pumped well sits on a small pad, often hours from the yard. The pumping unit has power, and many have a rod pump controller that records the dynamometer card (the stroke card) and sends it out over SCADA radio, cellular, or satellite. The chemical tanks are usually not on that link.

One to three poly tanks, usually a few hundred gallons each, feed a small injection pump:

| Chemical | Why the well needs it | When the tank runs dry |
|---|---|---|
| Corrosion inhibitor | CO₂, H₂S, and brine eat rods and tubing | Rod parts, tubing leaks, a workover rig |
| Paraffin inhibitor or solvent | Wax builds up in the tubing and flowline | Stuck rods, lost production, a hot-oil truck |
| Scale inhibitor | Mineral scale plugs the pump | A stuck pump, then acid or a workover |
| Biocide | Bacteria sour the well and pit the steel | H₂S, under-deposit corrosion |
| H₂S scavenger | Sour gas at the wellhead | A safety and sales-spec problem |
| Emulsion breaker | Oil and water won't separate | Off-spec oil, treating cost |

A pad carries the products that well needs, commonly one to three, not this whole list. Each product has its own tank and its own pump. Corrosion inhibitor and scale inhibitor are sometimes a tested blend in one tank. The Patricia program below is that case: paraffin inhibitor, corrosion inhibitor, and a little emulsion breaker in one vessel. Biocide and H₂S scavenger usually stay separate. Aldehyde biocides can drop solids with amine inhibitors, and triazine scavenger can foul an inhibitor film. In that same paper the emulsion breaker was injected at the tank battery, then shut off. It was not in the well tank.

A treater truck carries the products apart. The sourced body is a 30- or 50-barrel flush tank, 1,260 or 2,100 gallons, plus chemical packs of 60 gallons. Twelve packs is the option, 720 gallons if every pack is the same product ([FTSR](https://www.ftsrgroup.com/trucks-trailers/chemical-treater-trucks)). The barrel tank is the flush. The packs are the neat chemical. One stop can refill every tank whose product was loaded, up to the gallons in that pack. A product left in the yard is a second trip. The fastest tank sets the day the truck goes.

### Two customers, one set of pictures

**The operator buys the chemical.**

- They pay for gallons and visits they can't verify. When monitoring does exist, the service company often installed it, so the operator is checking the vendor against the vendor's own data.
- A tank that ran dry for a week shows up months later as a failure. By then, nobody can tie the failure back to the missed delivery.
- A tank that drains faster than the planned dose rate points to waste, a leak, or theft.

**The chemical service company runs the route.**

- Labor is scarce, and drives take hours. On a fixed check of continuous-injection tanks, part of the day is wells that didn't need a drop. On a batch route, the stop is the treatment, and the camera does not cancel it.
- Dispatch only to tanks at or below the refill line shortens a route of look-in visits. It does not shorten a batch route. A full refill still ends the day when the packs are empty, which on a large tank is a couple of wells.
- Knowing the gallons each well needs before leaving the yard means the truck is loaded correctly.
- Proof of delivery leads to faster payment, fewer disputes, and evidence when a failure gets blamed on the chemical program.
- Verified delivery is something they can sell when bidding for contracts.

The operator uses the pictures to audit the vendor. The service company uses the same pictures to defend its invoices and plan its route.

## Market size

| Fact | Source |
|---|---|
| 918,481 producing U.S. oil and gas wells in 2024. 78% made 15 barrels of oil equivalent a day or less. | [EIA 2025](https://www.eia.gov/petroleum/wells/pdf/WDR2025_Full%20Report.pdf) |
| About 394,000 stripper oil wells in 2009, averaging 2.4 barrels a day. Together they produced about 20% of U.S. oil. | [IOGCC 2010](https://oklahoma.gov/content/dam/ok/en/iogcc/documents/publications/2010marginalwell.pdf) |
| About 350,000 U.S. wells on sucker-rod pumps. | Secondary source ([market.us](https://market.us/report/artificial-lift-systems-market/)). Verify before using it on a slide. |
| Corrosion inhibitor is the largest segment of production chemicals. Market totals range from about $4B to over $20B depending on scope. | Paid market reports. Give the range or skip it. |

Don't claim a dollar market you can't source. Build it bottom-up instead:

```text
reachable pads = rod-pumped wells with chemical injection ÷ wells per pad
annual value   = reachable pads × value per pad (below)
```

The share of wells with chemical injection is an *assumption*. Ask the room what they would use.

## Fault impact

| Fault | Who pays | How it shows up |
|---|---|---|
| A tank runs dry | Operator | Under-treatment, then a rod part, a tubing leak, or a stuck pump months later. The cost is a workover plus the production lost while the well is down. |
| A ticket is billed with no delivery, or for more than was delivered | Operator | Money lost on every invoice that isn't checked |
| A stop at a tank that didn't need it | Service company, then the operator through rates | Driver hours, fuel, truck wear, and the well that didn't get serviced instead |
| The tank drains too fast | Operator | Wasted chemical, a leak, or theft. A spill becomes an environmental report. |
| Driving | Everyone | The leading cause of work-related death in oil and gas extraction: 28% of deaths in 2003–2009, at 8.5 times the all-industry rate. Well-servicing workers have the highest risk. ([NIOSH](https://stacks.cdc.gov/view/cdc/194349)) |

Fewer unnecessary drives is a safety argument the NIOSH data supports without any assumption.

## Financial cost

### How much chemical a well uses

Dose is set in parts per million of total produced fluid, oil plus water. Each tank gets its own rate. The dollars below do not stack the whole chemical menu onto one tank.

```text
gallons per day = total fluid (bbl/day) × 42 × ppm ÷ 1,000,000
```

| Anchor | Value | Source |
|---|---|---|
| Continuous corrosion inhibitor | 25–50 ppm of total fluid. The profiles below use 50 ppm, the top of this range, so the fast tank is not understated. | [SWPSC](https://www.swpshortcourse.org/ppdl/601), Exxon Midcontinent rod-pump practice |
| Batch corrosion inhibitor | Under 50 bbl/day of fluid: monthly. From 50 to 150: every other week. A sour-well trial went to 1–2 gal every other month. | [SWPSC](https://www.swpshortcourse.org/ppdl/687) |
| Permian paraffin and corrosion blend, one tank | Trial well: 26 bopd, 50 bwpd, 3.5 qt/day, $19 a day. Loop of 14 wells near Patricia, Texas: 22 bopd, 59 bwpd, $16.89 a day, $0.20 per total barrel. The paper's target for that loop was $0.12, and the area average on this equipment was $0.09. | [SWPSC](https://www.swpshortcourse.org/paper/2015025-improving-paraffin-treating-modernizing-chemical) |
| Implied price of that blend | About $22 a gallon ($19 a day ÷ 3.5 qt). Used below on the ppm cases as an *assumption*. | Same source |
| Scale inhibitor, second tank | 25 ppm of total fluid | *Assumption*, half the corrosion rate used here. It does not set the trip unless it exceeds the corrosion tank. |

Water cut has to match the well. The Central Basin Platform figure and the old-waterflood figure are different populations:

| Water-to-oil ratio | Source |
|---|---|
| Permian average 3–5:1, Delaware 5–10:1, Midland 3–5:1, Central Basin Platform 2–4:1 | [Permian Produced Water](https://www.permianproducedwater.com/basics.html) |
| Delaware Wolfcamp starts near 2:1, reaches about 5:1 by year four, and eventually about 7:1 | [Wood Mackenzie](https://www.woodmac.com/press-releases/permian-produced-water/) |
| Conventional Permian wells about 13:1 over 2005–2015, against about 2.6:1 for horizontals | [Scanlon et al., ES&T 2017](https://pubs.acs.org/doi/full/10.1021/acs.est.7b02185) |
| The Patricia loop, the only well here with both rates measured | 59 bwpd ÷ 22 bopd, about 2.7:1 | Same SWPSC paper |

Three profiles, one well per pad. Profile A uses the Platform midpoint, 3:1, not the 13:1 waterflood ratio. Profile B is the sourced blend, one tank, and that $6,165 is not reused on the other two. Profile C is a corrosion tank plus a scale tank at the ppm rates, not the paraffin blend.

| Profile | Oil | Water | Total fluid | Fast tank | Program per year |
|---|---|---|---|---|---|
| **A. Platform or Northwest Shelf stripper** | 2.4 bopd ([IOGCC](https://oklahoma.gov/content/dam/ok/en/iogcc/documents/publications/2010marginalwell.pdf) prose average) | 7.2 bwpd (3:1, midpoint of the Platform 2–4:1 range, *assumption*) | 9.6 bbl/day | Corrosion inhibitor, 0.020 gal/day | **About $240.** Corrosion about $160, scale about $80. |
| **B. Patricia loop** (sourced) | 22 bopd | 59 bwpd | 81 bbl/day | One blend, about 0.8 gal/day | **$6,165.** $16.89 × 365. Dawson County, not the Delaware. |
| **C. Delaware horizontal, late life on rod lift** | 50 bopd (*assumption*) | 350 bwpd (7:1, the "eventually" case) | 400 bbl/day | Corrosion inhibitor, 0.84 gal/day | **About $10,120.** Corrosion about $6,750, scale about $3,370. |

The spoken case prices two wells. The fast well is this row: 50 barrels of oil a day, 350 barrels of water a day, and 0.84 gallons a day from the chemical tank. The dose is 50 ppm of total fluid, oil plus water: `400 × 42 × 50 / 1,000,000 = 0.84`. The slow well is profile A: 2.4 barrels of oil a day, about 7 barrels of water, and 0.02 gallons a day, about $240 a year for two tanks. The water is produced with the oil. It is not liquid in the chemical tank. The seven-to-one ratio is the late Wolfcamp case ([Wood Mackenzie](https://www.woodmac.com/press-releases/permian-produced-water/)). The alert wait is the level error, about ±10–17 gallons, divided by the daily dose. That is a few weeks on the fast well and about a year or two on the slow well. A tighter level reading shortens both. The slow well stays in the price.

A waterflood stripper at 13:1 is a different well: about 34 bbl/day of fluid, a corrosion tank at 0.071 gal/day, and a two-product program of about $850 a year. It still lands on the quarterly visit below. Pricing that fluid at the paraffin blend's $0.20 a barrel comes to about $2,480 a year, which is the blend price, not a 50 ppm corrosion program.

Profile C at that same $0.20 is about $29,200 a year, and at the paper's $0.12 target about $17,500. That is a paraffin-problem well, not the base program. Another well in the paper took 6 gal/day of H₂S scavenger. That rate empties a tank in weeks. It is a sour-well example, not a rate to put on every pad.

Four hundred barrels a day is the top of what a pump jack does on a Permian horizontal, about 300–400 bbl/day, with long-stroke units used to reach toward 1,000 ([PB Oil & Gas](https://pboilandgasmagazine.com/oils-workhorse/), [LPS](https://www.lpsus.com/news-item/High-Rate-ESP-Conversions)). Below 8,000 ft a conventional jack has trouble above about 300. Profile C is a long-stroke well, or it is at the ceiling. Delaware horizontals usually reach rod lift after an electric submersible pump and gas lift.

On the stripper, 50 ppm is about 7 gallons a year. A monthly batch of 1–2 gallons, or the sour-well trial at 1–2 gallons every other month, is the same order of money. The injection pump's minimum rate can sit above the ppm math. Confirm what the Oxy wells used.

### Tank size and how long the fast tank lasts

Standard wellsite chemical injection tanks are 65, 125, 225, and 335 gallons ([Snyder](https://www.snydernet.com/products/industrial-tanks/chemical-injection-tanks)). Refilling at the 25% line leaves 75% usable. Days below are for the fast tank only. The slower tank lasts longer and is filled on the same stop.

| Tank | A: 0.020 gal/day | B: 0.8 gal/day | C: 0.84 gal/day |
|---|---|---|---|
| 65 gal | About 6.7 years | 61 days | 58 days |
| 125 gal | About 13 years | 117 days | 112 days |
| 225 gal | About 23 years | 211 days | 201 days |
| 335 gal | About 34 years | 314 days | 299 days |

The working size below is 125 gallons. A quarterly check is safe on that tank for all three profiles, because each one holds more than 90 days. A 65-gallon tank on profile B or C holds about two months, so the refill itself is the schedule, about six visits a year.

Two kinds of truck visit, and only one of them shrinks to quarterly:

| Pattern | A. Stripper, about 10 bbl/day of fluid | B. Loop, 81 bbl/day | C. Delaware, 400 bbl/day |
|---|---|---|---|
| Batch treatment, Evans and Doran, SWPSC 1983, restated for Permian practice in 2003 | Monthly, 12 visits, for wells up to 50 bbl/day of fluid | Every two weeks, 26 visits, for 50–150 | Twice a week, about 104, for 350–800. One Permian practice went continuous above about 300. |
| What the camera does to a batch visit | Nothing to the stop count. It checks the ticket. | The same. Leaving an all-weekly schedule cut stops about 28% on one Permian unit, not down to quarterly. | A twice-a-week batch is the treatment. The camera does not delete it. |

Cite Murphy in the room, not the 1983 table. Murphy Exploration and Production, about 700 rod-pump wells, was on a fixed batch every 15 days. Data from 2019 showed about 15,000 treatments a year. A data-driven schedule brought that to about 7,000 treatments, an average of about 28 days, and about 51% less batch-treatment spend ([JPT, March 22, 2021](https://jpt.spe.org/data-driven-automated-batch-treatment-program-streamlines-rod-pump-maintenance)). That program did not use a camera, and it did not go to quarterly.

The rate ladder in the table above is from Evans and Doran, Conoco, SWPSC 1983, for the MCA Unit at Maljamar and then the Hobbs area ([paper](https://www.swpshortcourse.org/sites/default/files/papers/1983023.pdf)). Moving that unit off an all-weekly schedule cut truck stops from 648 a month to 469, about 28%, and inhibitor gallons from 1,814 to 906. A 2003 Permian test found trucks already coming between twice a week and once a month, and a better inhibitor doubled the interval on the test wells ([SWPSC 2003](https://www.swpshortcourse.org/sites/default/files/papers/2003033.pdf)). Keep both as background. Neither is what you lead with.

Continuous injection is a refill, not that calendar. Published practice puts it on higher-rate wells, because a pump and a tank at every well is expensive, and the *Lease Pumper's Handbook* says the pumper is the one who keeps the injection record. How often the chemical company comes back to inventory a continuous tank is not in the sources. The quarterly floor below is an *assumption*, and it is the only case in which the 22 avoided stops exist.

The truck comes when the fast tank needs a refill, and at least quarterly on that assumption. Other products on the truck are filled on that stop, up to the gallons loaded.

| Continuous injection, 125-gal fast tank | A | B | C |
|---|---|---|---|
| Check every two weeks today (*assumption*) | 26 | 26 | 26 |
| Need-based | 4 | 4 | 4 |
| **Avoided** | **22** | **22** | **22** |
| Check monthly today (*assumption*) | 12 | 12 | 12 |
| **Avoided from monthly** | **8** | **8** | **8** |

A 65-gallon tank on B or C needs about 6 refills, so the avoided count from a two-week check is about 20, not 22. A scavenger tank at the paper's 6 gal/day needs about 23 refills a year on a 125-gallon tank. A two-week check is barely enough, and the camera's job there is to keep the tank from running dry.

### Drive time and cost per stop

| Anchor | Value | Source |
|---|---|---|
| A lease operator's day, used here as a dense-route stand-in | 15–20 pads, 150–250 miles, 20–30 minutes per site including drive | [WorkSync](https://www.work-sync.ai/insights/pumper-route-optimization), a pumper-software blog, not a measured chemical route |
| Miles per stop | About 11 (200 miles ÷ 17.5 stops) | Derived from that blog |
| Vehicle cost | $0.76 per mile | IRS business mileage rate from July 1, 2026. This is the automobile rate, so a treater truck costs more and the route savings below are a floor. |
| Treater pay in Midland and Odessa | Treater truck driver about $25–31 an hour ([posting](https://talents.vaia.com/companies/imperative-chemical-partners-inc/midland/treater-truck-driver-153393261/)). The $28.02 median is BLS chemical technicians in Midland, a plant and lab occupation ([Wages by City](https://wagesbycity.com/salary/chemical-technicians/midland-tx/)). | Postings and BLS |
| Loaded labor | $40 an hour: $28 × 1.4 for payroll taxes, benefits, and overtime | *Assumption* on the 1.4 |

```text
cost per stop = hours per stop × labor rate + miles per stop × $/mile
```

| Route | Hours per stop | Miles per stop | Cost per stop |
|---|---|---|---|
| Dense route (stand-in) | 0.5 | 11 | **About $28** |
| Remote Delaware: Reeves, Loving, Culberson, or Eddy County | 1.0 (*assumption*) | 30 (*assumption*) | **About $63** |

Profile B is Dawson County. Use the dense-route cost for it unless the drive is actually an hour. The remote cost is for the Delaware counties, and for a stripper placed there.

**What the truck can finish.** A refill from the 25% line is 75% of the tank: about 94 gallons on a 125-gallon tank, about 251 gallons on a 335-gallon tank. On the 12-pack truck, all 720 gallons in one product finishes **two** 335-gallon refills (502 gallons) or **seven** 125-gallon refills (658 gallons). Split 6 and 6 across two products, 360 gallons each, one load finishes **three** two-tank pads of 125 gallons and **no** 335-gallon tank, because 360 is more than 94 and less than 251. Check stops, and batch stops, are not held to that count. A batch is about 1–2 gallons of inhibitor plus a flush of about 2–3 barrels. The flush tank, not the pack, is what runs out, and 2,100 gallons of flush is on the order of 15 wells at 3 barrels each. No open source states how many of those stops fit in a day. The 15–20 pads a day figure is a pumper blog. Do not use it as a treater's day, and do not turn 26 visits into 4 and call the driver 6× more productive. The fills that remain are the stops that empty the truck.

**Driver capacity, batch.** There is no sourced wells-per-day for a chemical treater. Until the route provides one, do not claim a headcount change. The camera does not remove the batch stop.

### Failures

A failure costs the workover plus the oil not produced while the well is down. Assume 7 days down, about $91 per barrel, and 0.05 avoided failures per pad per year: 1 pad in 20 has a dry-tank failure that monitoring would have caught. Front-month WTI settled at $91.49 on October 8, 2026, before basis. The $65 figure is retired. All three rates are *assumptions*. The expected-value row is not a measured rate. The spoken case uses the Delaware event once, and leaves the 1-in-20 rate out.

| | A. Stripper | B. Loop well | C. Delaware horizontal |
|---|---|---|---|
| Workover (*assumption*) | $10,000 (shallow vertical) | $15,000 | $25,000 (deep, deviated) |
| Lost production at about $91 | $1,529 | $14,014 | $31,850 |
| **Expected value per year** | **About $576** | **About $1,450** | **About $2,840** |

Paraffin stripping jobs in the Permian can exceed $100,000 in extreme cases ([SWPSC](https://www.swpshortcourse.org/paper/2015025-improving-paraffin-treating-modernizing-chemical)). That sentence is about a stuck-rod stripping job, not a typical chemical-related failure.

### Billing

Discrepancies caught at 3% of chemical spend (*assumption*):

| | A. Stripper, $240 | B. Loop, $6,165 | C. Delaware, $10,120 |
|---|---|---|---|
| Billing caught | About $7 | About $185 | About $300 |

On a stripper this is noise. The audit's value is leverage: a vendor who knows every visit is photographed bills accurately, and the operator negotiates renewals with evidence. Present the audit as the reason the operator buys, not as the dollar line.

### Value per well per year — Murphy, 2019

This replaces the 22-avoided-stop case. That case assumed a chemical truck looking at continuous tanks every two weeks. Murphy's measured program is a truck batch, and it is the schedule to price.

```text
15,000 treatments ÷ 700 wells = 21.4 treatments per well per year
7,000 ÷ 700 = 10 per well per year
avoided by their scheduler = 8,000 fleet-wide = 11.4 per well
```

Stop cost is unchanged: about $28 dense, about $63 remote. Both are a floor. The mileage rate is the IRS automobile rate, and the hours and miles are a pumper-route stand-in.

| | Dense, $28 | Remote, $63 |
|---|---|---|
| 11.4 treatments their scheduler removed | **$320 a year** | **$720 a year** |
| Five years of that cut | $1,600 | $3,600 |
| Treatments this camera removes | **$0** | **$0** |

The article also reports about 51% less batch-treatment spend. It does not give the dollar base, so the 51% is not converted to money here. The $320 and $720 count truck stops only, at our floor rate. They do not include the inhibitor gallons Murphy also cut.

Their old dose was 10 gallons of inhibitor and 42 gallons of water per treatment. At 21.4 treatments that is about 214 gallons of inhibitor a well a year. At $22 a gallon, about $4,700. A 3% billing discrepancy on that is about $140 a year, about $700 over five years. The dose is pumped from the truck down the annulus. A camera on a day tank does not see it. The box costs about $1,100–$2,200 over five years. Billing does not pay it back, and the route cut is not the camera's.

WellAware at $420 a tank remains $4,200 over five years for two tanks, against about $1,100–$2,200 for this box. Use that comparison only where a tank is on the pad. Murphy's program carries the chemical on the truck.

The failure assumption is unchanged and still stays out of the payback: about $555, $1,250, and $2,390 a year on profiles A, B, and C.

**Fleet, Murphy's 700 wells.** 8,000 avoided treatments are about $224,000 a year at $28 a stop and about $504,000 at $63. Hardware for a camera on every well would be about $350,000–$700,000 before data. Those route dollars were earned without the camera.

### Cost of the alternatives

| Option | Year 1 | Each later year | Source |
|---|---|---|---|
| WellAware, two tanks | $840 | $840 | $420 per tank per year ([AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-cbiscubymcub4)). Three tanks is $1,260. |
| AFTI WatchDog camera | About $3,600 | $600 | 2021 deck: $2,800 hardware + $59 activation + $150 mounting + $600 a year ([NSWA](https://nswa.us/wp-content/uploads/2021/12/NSWA-WatchDog-Presentation-12.9.21.pdf)). Current quotes start at $1K–$5K ([AFTI](https://aftiwatchdog.com/solutions/remote-monitoring/)). |
| Radar sensors, self-installed | $4,000+ for two tanks | Your own telemetry | $2,000+ per tank, from WellAware's own sensor guide ([WellAware](https://wellaware.us/blog/whats-the-best-tank-level-sensor-choose-for-accuracy-and-reliability)) |
| Camera and edge box (this proposal) | About $500–$1,000 | About $120–$240 | Parts list below. Data is the later-year cost. |

Over five years, WellAware on two tanks costs $4,200, and on three tanks $6,300. This build costs about $1,100–$2,200, hardware once plus five years of data. Per-tank pricing is the weak spot of sensors on a multi-tank pad.

That comparison isn't complete. WellAware's price includes the sensor, warranty replacement, the platform, and support. Ours excludes the labor to keep the devices running and the cost of a software platform. Add both before claiming the full gap. They are why the parts list below favors an industrial box over a hobby board.

## The solution

1. An outdoor camera on a post, outside the hazardous area, sees every tank on the pad.
2. A fanless edge box runs a Roboflow Workflow:
   - A crop for each tank.
   - A level reader. It finds the liquid surface and converts its height to gallons with that tank's strap table.
   - A person detector, which logs the visit.
   - A custom block that matches visits to tickets and produces the dashboard.
3. Only results leave the pad: the level per tank, the event, and the ticket status. Pictures go out when the link allows, or when someone requests them for a dispute.
4. The dashboard shows tanks at or below the refill line, visits by type, and dollars at stake.

### Why not another sensor

Every option below can read a level. What sinks them on a low-producing pad is the same set of problems: they touch the chemical, they cost money and wiring per tank, and they produce a number but no proof of a visit.

| Sensor | What it gets right | Why it doesn't fit here |
|---|---|---|
| Float, mechanical or reed switch | Cheap, simple | It sits in the chemical. Paraffin, scale, and solids make it stick, and solvents and biocides attack the seals. A switch only reports one point, not a level. Fitting it means draining the tank or cutting a new port. |
| Hydrostatic pressure transducer | Accurate, cheap per unit | It needs a bottom port and a wetted part rated for each chemical. The reading depends on density, so changing products means recalibrating. |
| Ultrasonic | No contact | Foam, vapor, condensation, and heat throw off the echo. Small tanks fall inside its dead zone near the top. |
| Radar | The most accurate option, sub-inch, no contact | About $2,000 or more per tank ([WellAware](https://wellaware.us/blog/whats-the-best-tank-level-sensor-choose-for-accuracy-and-reliability)). That's $6,000 or more for a three-tank pad that grosses about $57,000 a year. |
| Load cells under the tank | Measures gallons directly | The tank has to be lifted onto a scale frame, one per tank |
| Pump stroke counter | Already sits on the injection pump | It measures what was pumped, not what's in the tank. It misses leaks, theft, and padded deliveries. |

The problems they share:

- **Retrofit.** A wetted sensor means draining, cleaning, and opening a tank that holds hazardous chemical. Its material has to be compatible with that chemical, and it gets re-checked every time the product changes.
- **Cost and wiring per tank.** Each sensor needs power, a cable run, and an input on the controller or a radio node. A pad with three tanks needs three of everything.
- **No evidence.** A sensor says the level rose 40 gallons. It can't say who came, when, or whether the truck delivered what the ticket says. When the vendor installed the sensor, the operator is checking the vendor against the vendor's own data.
- **Blind to the pad.** It sees one tank and nothing else.

### Why vision makes sense

- **Nothing to touch.** The camera mounts on a post outside the hazardous area. It never contacts the tank or the chemical, so nothing gets drained or opened, and changing chemicals changes nothing.
- **One device per pad.** It reads every tank in view. Adding a tank is a new crop and a strap table, not new hardware.
- **Proof of the visit.** It records who came, when, and the level before and after, from a camera the operator can own separately from the vendor.
- **The rest of the pad.** The same camera can watch for leaks, containment, whether the pump jack is running, and the gate.
- **Opaque tanks still work.** It can read a sight tube or the dial of a pressure gauge instead.
- **Accurate enough for the job.** Route dispatch and delivery checks need a few percent, not sub-inch accuracy. When a pad needs custody-grade precision, keep the radar and use the camera for proof of visits.

### How accurate the level reading can be

The model finds the liquid surface, not quarter steps. Height converts to gallons through each tank's strap table, which maps level to volume. Any method needs one, because the markings on poly tanks are rough ([Detechtion](https://www.detechtion.com/hubfs/Chemical-Injection-Monitoring-and-Control-2.pdf)).

Controlled camera results land near 1–2%: a lab water-column camera at 0.9% ([MDPI](https://www.mdpi.com/1424-8220/24/23/7699)) and analog gauge reading around 2% when the scale is read correctly ([ETH Zürich](https://arxiv.org/html/2404.08785)). A later gauge study reports about 2.4–4.4% after fine-tuning ([arXiv](https://arxiv.org/html/2608.17723)). Those are not outdoor poly tanks. The field rows below are the numbers to use.

Our estimates, to test in the lab:

| Setting | Estimated error, % of tank height | On a 335-gal tank | Why |
|---|---|---|---|
| Lab: coffee reservoir, fixed camera, locked exposure | ±2% | — | The surface spans 300 or more pixels in the crop, and a few pixels of edge error is about 1%. The meniscus and the plastic wall add the rest. |
| Field: translucent poly tank, daylight | ±3–5% | ±10–17 gal | Sun, shadow, dirty walls, and a camera farther away |
| Field: night under infrared, or a stained tank | ±5–10%, or `review` | ±17–34 gal | Low contrast. Low-confidence readings go to review instead of dispatching a truck. |

What that precision buys in the field:

- **Delivery checks.** On a 125-gallon tank the usable refill is about 95 gallons, so a ±10–17 gallon error is about 10–20% of the delivery. A half-load is still outside that error. On a 335-gallon tank the refill is about 250 gallons, and the same error is under 10%.
- **Dispatch.** On the stripper, and on a 125-gallon tank at profiles B and C, the quarterly check arrives with weeks of chemical left. A 65-gallon tank on B or C, and any scavenger tank at several gallons a day, has less margin. Low-confidence readings stay on `review`.
- **Dose rate.** The stripper's fast tank is 0.020 gal/day, so one still cannot see a day's use. The trend is a monthly one. The Delaware corrosion tank is 0.84 gal/day, so a drain trend shows in a couple of weeks. Averaging stills cuts the random error. The strap table fixes the bias.
- **Small padding.** A ticket padded by 5–10 gallons is inside the error. Put that in the risks, and state it plainly.

## Hardware: cheap, fanless, rated for heat

| Part | Choice | Why | Rough cost |
|---|---|---|---|
| Edge box | Seeed reComputer R1025-10: Raspberry Pi CM4, 4 GB RAM, 32 GB eMMC ([Seeed](https://www.seeedstudio.com/reComputer-R1025-10-p-5895.html)) | Fanless, rated −30 to 70 °C, 9–36 V DC input, about 2.9 W idle. Hardware watchdog, eMMC instead of an SD card, isolated RS485 for Modbus ([spec](https://wiki.seeedstudio.com/recomputer_r/)). Seeed lists it at $297 and has shown it out of stock. | $297 list |
| Cellular | Quectel EC25-AF mini-PCIe module (North America), tested with the R1000 | LTE Cat 4 | About $50–80 (*estimate*) |
| Camera | Outdoor PoE IP camera, IP67, rated −40 to 60 °C, RTSP and ONVIF. Some carry these ratings ([example spec](https://www.brovotech.com/products/5mp-2mp-motorized-dome-lite-ir-network-camera)). | Built for outdoor sun. Many consumer models stop at 50–55 °C ([Reolink spec](https://home-cdn.reolink.us/files/docs/specs/CX410-IP-Camera-Specifications.pdf)). | About $50–120 (*estimate*) |
| PoE injector | 12–24 V DC input | PoE into the R1000 is an optional module, and the Ethernet port does not power the camera | About $20–40 (*estimate*) |
| Enclosure | NEMA 4X, sun shield, vented | The R1000 is only IP40 and has to stay below 70 °C inside the box | About $60–120 (*estimate*) |
| Power | DC supply off the controller panel. Solar plus battery where needed. | The pumping unit already has power | About $20–40 from the panel, $200–350 for solar (*estimate*) |
| **Per pad** | | | **About $500–$700 on panel power, $700–$1,000 on solar** |

Power budget: about 3 W for the box plus up to 10 W for the camera with its infrared lights at night, so 10 W average is about 240 Wh a day. On solar, power the camera through a relay only when a still is needed. Use the camera's built-in person detection as the wake trigger, so the box doesn't watch video all day.

Compute: the level reader is a small detector on a single still every few minutes, which should run on the CM4's CPU. Measure it on the box. Measure the RF-DETR Nano person check on the box. It only needs to finish within a few seconds per still. If it's too slow, the R1000 accepts an AI accelerator.

## Connectivity: one plan for every link

Inference always runs on the edge box. The link only carries results, so the same Workflow runs everywhere and only the sender changes.

| Link | What leaves the pad | Pictures |
|---|---|---|
| **Cellular (default)** | An event message with each visit or level change, the jpeg with it, and a daily health check | Yes, compressed |
| **Existing SCADA radio** | Modbus registers the host already polls with the stroke card: level and confidence per tank, last event code, counters. The R1000 connects over RS485 or Ethernet. | No. Pull them over cellular, or during a visit, when there is a dispute. |
| **LoRaWAN** | Tank, level, confidence, event code, and a time offset. On US915 the long-range setting carries 11 bytes, so this event has to fit in that or step up to the next rate, which carries 53 ([The Things Network](https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/us915/)). | No. Pictures don't fit ([MDPI survey](https://www.mdpi.com/1424-8220/25/23/7128)). |
| **Satellite** | Same as cellular | Yes. Use it only if a terminal is already on site, because it draws a lot of power. |
| **No link** | Nothing. The device stores and forwards. | Kept on the eMMC |

LoRa specifics: each pad needs a LoRa end-node radio. A single R1000 with a LoRaWAN gateway module, placed at a hub with cellular, can serve many pads around it.

Every result carries an id, so a message sent twice is applied once. Records are written locally first, so a dropped link loses nothing.

## Roboflow's cost to the customer

| Item | Cost | Source |
|---|---|---|
| Labeling and training | Free tier: 10 credits a month. Core plan: $39 a month. Priced for the whole workspace, not per device. | [Pricing](https://roboflow.com/pricing) |
| Self-hosted inference | $0. It uses no credits, and no per-device fee is listed. | [Docs](https://docs.roboflow.com/deployment/self-hosted/self-hosted) |
| Inference server | Open source, Apache 2.0 core | [GitHub](https://github.com/roboflow/inference/blob/main/README.md) |
| Model licenses | ResNet and the standard RF-DETR sizes can be self-hosted commercially. RF-DETR 2XL and Ultralytics YOLO weights need a paid commercial license. Use RF-DETR, not YOLO, for the person detector. | [Pricing](https://roboflow.com/pricing) |
| Fleet management, documented offline mode, Vision Events export, Workflow versions, SLA | Enterprise only, custom pricing | [Enterprise docs](https://docs.roboflow.com/deployment/self-hosted/enterprise) |

A pilot costs about $0–$39 a month in Roboflow fees for the whole project. A production fleet of hundreds of pads likely needs Enterprise for remote fleet updates and support. That's a quote, not a published number.

Ask them in the interview: "How do you price a few hundred self-hosted edge devices, and what does a device do when it's offline?" It shows you read their pricing, and it's a real input to this business case.

### What the camera can call

A declining level means liquid left the tank. It does not mean the dose reached the perforations, or that the film is still working. Daylight error on a 335-gallon tank is about ±10–17 gallons. A stall has to clear about twice that before it is a confident flat line, because the call is the difference of two readings.

| Dose | One reading, ±10 to ±17 gal | Confident flat line |
|---|---|---|
| Stripper, 0.020 gal/day | 500–850 days | A few years. A stalled pump does not show up as a level. |
| Loop or Delaware corrosion, about 0.8 gal/day | 12–21 days | About a month |
| Scavenger example, 6 gal/day | 2–3 days | A few days |

Worth saying: a ticket for a fill the level never made, an empty tank on a gallons-per-day product before the next scheduled stop, a step of tens of gallons with nobody in frame, and standing liquid in the containment if it is in the shot. Not worth saying: the well is protected, a stripper's pump failed this month, the balls and seats are worn, the batch was skipped, or the wrong chemical went in the tank. The pump card already knows whether the jack is running. A stroke counter on the chemical pump, which this camera does not read, is what splits "not stroking" from "stroking and moving nothing."

## Calculated value

Read the close in [business-case.md](business-case.md). The dashboard dollar is disputed gallons times $22. On the demo that is about $2,760, half of a refill from the 25% line on a 335-gallon tank. A workover price stays off the screen. The chemical company's number is the $2,000–$3,100 spread against WellAware over five years, before install and support.

The notes under this heading are background. They are not the close.

**Batch, which is the published route.** Stops stay. A monthly stripper is 12 treatments a year. A two-week well is 26. A 400 bbl/day well on that table is about 104, unless it has already been moved to continuous injection. The camera checks a tank. It does not check a dose pumped down the annulus. Do not put a payback on deleted batch visits.

**Murphy's batch.** About 21 treatments a well a year, cut to 10 by their scheduler. That is about $320 a year of stops on a dense route and about $720 remote, and none of it belongs to the camera. The 22-stop, 5–11 month case is withdrawn.

**Operator, older lines.** On the stripper, about $7 of billing. The $555 failure term is an assumption, and a stalled stripper pump will not show in the level for months. On the Delaware well, billing is about $300. The $2,390 failure term pays the box back only if 1 pad in 20 is real. Those rates are not in the pitch.

**Against per-tank monitoring.** WellAware is $840 a year on two tanks, $4,200 over five years. This build is about $1,100–$2,200. That is the chemical company's spread, before install and support. It is not the operator's reason to buy.

## Risks

| Risk | Mitigation |
|---|---|
| A device fails and costs a truck roll | Industrial fanless box, hardware watchdog, eMMC, a read-only filesystem, remote updates. The camera checks its own health daily. |
| Heat | Hardware rated to 70 °C (box) and 60 °C (camera). Shaded, vented enclosure, and a sun shield on the camera. |
| Hazardous area | Mount everything outside the classified zone, aimed at the tanks |
| Night, glare, dirty lens | Infrared camera. Low-confidence readings go to `review` and never dispatch a truck. Flag a lens that needs cleaning. |
| Small padding is inside the reading error | Set the ticket tolerance from the measured error and state it in the contract. For custody-grade pads, pair the camera with radar. |
| The camera gets bumped and the calibration shifts | The model also finds the tank outline. If it moves more than a few pixels, readings go to `review` and the pad gets flagged for recalibration. |
| Vendor refuses the audit | Sell to the operator, who owns the camera. Offer the vendor the same proof of delivery. |
| The visit is a batch, not a tank check | Count no route savings. The picture still checks the ticket. The published cut from rescheduling batches is about 28% of stops. |
| A refill day is a couple of wells | Price driver capacity off gallons on the truck, not off 17 pumper stops a day. Twelve 60-gallon packs finish two large refills. |
| The level looks fine and the well is not protected | Do not claim corrosion, scale, or paraffin control from the trend. A stripper pump that stopped injecting stays inside the error bar for months. |
| Software cost at scale | Get a Roboflow fleet quote before the pilot ends |

## Pilot

Run 10 pads for 90 days alongside the current route.

| Measure | Target |
|---|---|
| Camera level against a manual gauge | Within ±5% of tank height on 95% of daylight readings |
| Delivered gallons against a metered delivery | Within ±10% of the delivery |
| Check stops the camera would have avoided | Count them, and price them with the real cost per stop |
| Ticket discrepancies found | Count them, and add up the dollars |
| Device uptime | 98% or better |
| Truck rolls to fix the device | Fewer than one per pad per year, projected |

Go further if the disputed gallons on the pilot cover the hardware. Do not use avoided stops as the gate. The camera does not delete a batch route.

## Numbers to fill in from the route

- Whether the truck is refilling a tank or pumping a batch down the annulus. The payback in the pitch is one visible half-fill, about $2,760, and one assumed $15,000 pull. Murphy's treatments are not in it.
- How many wells one treater finishes in a day, and whether that day ends because the packs are empty. The model caps a full refill load at two 335-gallon tanks or three 125-gallon two-product pads.
- Drive hours, miles, and loaded labor. The model uses 0.5–1 hour, 11 or 30 miles, $40 an hour, and $0.76 a mile. The mileage rate is a car rate.
- Gallons per day for each product, and the tank size. The fast tanks in the model are 0.020, 0.8, and 0.84 gal/day, on a 125-gallon tank.
- How many products are on the pad, and whether one truck loads all of them.
- Chemical price. The ppm cases use $22 a gallon from one 2015 blend invoice. The Patricia loop uses its own $16.89 a day.
- Water cut. Profile A uses 3:1. The 13:1 waterflood is a separate well. Profile C uses 7:1.
- Wells per pad on the Delaware side.
- Workover cost, and how often a chemical-related failure actually followed a dry tank.
- Whether the pumping units had power at the controller panel.
