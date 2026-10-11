-- One file, learn/tank.sqlite. Python's sqlite3. No extra package.
-- One process writes. One transaction per tick.
-- Photos stay files in learn/frames/. This database does not store JPEG bytes.
-- The page reads machine, the newest events, and the 8 files. It does not scan reading.
-- day is the America/Chicago calendar day.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- gauge_oz is null when the reservoir box is missing.
-- gauge_oz is 0 when the reservoir is present and no liquid line is found.
-- booked_oz is what we kept. On a fill it is 70 even when gauge_oz is lower.
-- Later seated ticks move booked_oz by the gauge change. A still gauge leaves 70 in place.
CREATE TABLE reading (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  day TEXT NOT NULL,
  gauge_oz REAL,
  booked_oz REAL,
  person INTEGER NOT NULL CHECK (person IN (0, 1)),
  capture_ms INTEGER NOT NULL,
  tank_ms INTEGER NOT NULL,
  person_ms INTEGER NOT NULL,
  gauge_ms INTEGER NOT NULL,
  ledger_ms INTEGER NOT NULL,
  total_ms INTEGER NOT NULL,
  rss_mb INTEGER,
  temp_c REAL
);

CREATE INDEX reading_ts ON reading (ts);
CREATE INDEX reading_day ON reading (day);

-- One row when an appearance starts, the reservoir comes back, activity changes, or the alarm changes.
-- kind is person, taken, fill, dump, put_back, brewing, idle, out, alarm_on, or alarm_off.
-- A return tick may also write the alarm event. Stale is not an event.
-- model_oz is the gauge. ounces is the booked level after the event.
-- delta_oz is 70 minus taken_oz on a fill, and null otherwise.
CREATE TABLE event (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  day TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  model_oz REAL,
  ounces REAL,
  delta_oz REAL
);

CREATE INDEX event_id_desc ON event (id DESC);

-- The page reads this row. The ledger replaces it every tick.
-- activity is idle, brewing, or out.
-- person is 1 when this frame has a person. person_open stays 1 until two ticks have no person.
-- seen_today increments when person_open goes from 0 to 1.
-- reservoir_out stays 1 from the confirmed take until the return tick classifies.
-- The box coming back while a person is still in frame does not clear it.
-- taken_oz is the booked ounces saved when the take confirmed.
-- gap_ticks counts consecutive misses while reservoir_out is 0.
-- gap_person is 1 when any tick in the current gap had a person.
-- At 2 with gap_person 1, the take confirms and the gap clears.
-- At 4 with gap_person 0, the page says stale and the other fields stay put.
-- pending_oz is the quiet-jump candidate. pending_count is ticks on that candidate, including the jump.
-- Accept at 3, which is the jump plus two further ticks within 1 fl oz.
-- Any other tick clears both. A seated person, a take, and a return clear both.
-- An accepted rise updates booked ounces, does not bill, and does not book 70.
-- out_15m and out_today are sums of downward booked_oz steps. A rise adds 0.
-- filled_oz is the sum of today's fill delta_oz values. refills_today counts those fills.
-- coffee_month is the mean of logged days of coffee, times 30. Coffee today is filled_oz / 5 * 0.50.
CREATE TABLE machine (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  booked_oz REAL,
  activity TEXT NOT NULL,
  activity_started TEXT NOT NULL,
  alarm INTEGER NOT NULL CHECK (alarm IN (0, 1)),
  alarm_started TEXT NOT NULL,
  person INTEGER NOT NULL CHECK (person IN (0, 1)),
  person_open INTEGER NOT NULL CHECK (person_open IN (0, 1)),
  seen_today INTEGER NOT NULL,
  reservoir_out INTEGER NOT NULL CHECK (reservoir_out IN (0, 1)),
  taken_oz REAL,
  gap_ticks INTEGER NOT NULL,
  gap_person INTEGER NOT NULL CHECK (gap_person IN (0, 1)),
  pending_oz REAL,
  pending_count INTEGER NOT NULL,
  out_15m REAL NOT NULL,
  out_today REAL NOT NULL,
  filled_oz REAL NOT NULL,
  refills_today INTEGER NOT NULL,
  coffee_month REAL NOT NULL
);
