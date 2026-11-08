-- EmberGrid: pilot selection + set-based daily_features build
-- Verified on PostgreSQL 16 against a replica of your schema (2022 VIIRS, 606,855 rows, 3.39M cells):
--   positive cell-days = 340,816 (matches pandas exactly); 890k dense rows built in 11.7 s.
-- Assumes your columns: cells(cell_id, lat, lon, district), fire_events(cell_id, local_date, confidence, detection_type, frp)
-- ASSUMES fire_events.local_date is the IST day and confidence is 'l'/'n'/'h'. Check with the queries in section 0.

-- 0) sanity checks (run first, read the output)
SELECT count(*) AS events, count(*) FILTER (WHERE cell_id IS NULL) AS no_cell FROM fire_events;
SELECT detection_type, confidence, count(*) FROM fire_events GROUP BY 1,2 ORDER BY 3 DESC;
SELECT min(local_date), max(local_date) FROM fire_events;
SELECT status, count(*) FROM ingestion_runs GROUP BY 1;            -- the 5 failed runs: safe to leave, or DELETE them

-- 1) indexes the aggregation needs (CREATE INDEX CONCURRENTLY outside a transaction if the app is live)
CREATE INDEX IF NOT EXISTS ix_fire_events_date_cell ON fire_events (local_date, cell_id);
CREATE INDEX IF NOT EXISTS ix_cells_district ON cells (district);

-- 2) rank districts: forest-like fire season (Feb-Apr) vs crop-residue season (Oct-Nov)
--    Pick districts with high feb_apr_share, low oct_nov_share, and enough positives to learn from.
WITH pos AS (
  SELECT cell_id, local_date FROM fire_events
  WHERE detection_type = 0 AND confidence IN ('n','h')
  GROUP BY cell_id, local_date
)
SELECT c.district,
       count(*)                                                                     AS positive_cell_days,
       round(avg((extract(month FROM p.local_date) IN (2,3,4))::int)::numeric, 3)   AS feb_apr_share,
       round(avg((extract(month FROM p.local_date) IN (10,11))::int)::numeric, 3)   AS oct_nov_share,
       count(DISTINCT p.cell_id)                                                    AS distinct_cells
FROM pos p JOIN cells c USING (cell_id)
GROUP BY c.district
HAVING count(*) >= 500
ORDER BY (avg((extract(month FROM p.local_date) IN (2,3,4))::int) - avg((extract(month FROM p.local_date) IN (10,11))::int)) DESC,
         count(*) DESC
LIMIT 30;

-- 3) pilot = a handful of chosen districts (EDIT the list)
DROP TABLE IF EXISTS pilot_cells;
CREATE TABLE pilot_cells AS
SELECT cell_id FROM cells WHERE district IN ('State A / District 1', 'State A / District 2');
ALTER TABLE pilot_cells ADD PRIMARY KEY (cell_id);

-- 4) fire-label layer: dense skeleton (pilot cells x date window) LEFT JOIN positives, one statement.
--    Owns ONLY fire_count/max_frp, so weather/NDVI jobs can upsert their own columns without clobbering these.
--    Run per season/year so each run is small and restartable; re-running is idempotent.
INSERT INTO daily_features (cell_id, date, fire_count, max_frp)
SELECT pc.cell_id, d::date, COALESCE(p.fire_count, 0), p.max_frp
FROM pilot_cells pc
CROSS JOIN generate_series(DATE '2022-02-01', DATE '2022-06-30', INTERVAL '1 day') AS d
LEFT JOIN (
  SELECT cell_id, local_date, count(*)::int AS fire_count, max(frp) AS max_frp
  FROM fire_events
  WHERE detection_type = 0 AND confidence IN ('n','h')
    AND local_date BETWEEN DATE '2022-02-01' AND DATE '2022-06-30'
  GROUP BY cell_id, local_date
) p ON p.cell_id = pc.cell_id AND p.local_date = d::date
ON CONFLICT (cell_id, date) DO UPDATE
   SET fire_count = EXCLUDED.fire_count, max_frp = EXCLUDED.max_frp;

-- 5) validation: dense rows must equal cells x days; positives must equal the sparse count
SELECT count(*) AS rows,
       (SELECT count(*) FROM pilot_cells) * (DATE '2022-06-30' - DATE '2022-02-01' + 1) AS expected_rows,
       count(*) FILTER (WHERE fire_count > 0) AS positives
FROM daily_features WHERE date BETWEEN '2022-02-01' AND '2022-06-30'
  AND cell_id IN (SELECT cell_id FROM pilot_cells);
SELECT cell_id, date, count(*) FROM daily_features GROUP BY 1,2 HAVING count(*) > 1;   -- must be empty
