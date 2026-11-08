-- EmberGrid NDVI layer. Composites are extracted ONCE per (cell, composite) into ndvi_composites (scope cells only),
-- then copied onto daily_features by an as-of join, so the leakage rule lives in one auditable place.

CREATE TABLE IF NOT EXISTS ndvi_composites (
  cell_id  varchar NOT NULL REFERENCES cells (cell_id),
  obs_date date    NOT NULL,          -- composite START date (the band name, e.g. 2020_02_18_NDVI)
  ndvi     real,                      -- NULL where the pixel was masked/invalid
  PRIMARY KEY (cell_id, obs_date)
);
CREATE INDEX IF NOT EXISTS ix_ndvi_comp_date ON ndvi_composites (obs_date);

-- For day d the cell sees the LATEST composite that was already available on d:
--     obs_date <= d - p_avail_days            (p_avail_days = 16-day composite period + processing latency)
-- The 20-day window is just a lookback bound (composites start every 16 days; the last one of a year is shorter).
-- Owns: ndvi, ndvi_obs_date. One month per chunk, logged in ingestion_runs.
CREATE OR REPLACE PROCEDURE build_ndvi_features(p_start date, p_end date, p_avail_days int DEFAULT 18)
LANGUAGE plpgsql AS $$
DECLARE m date; s date; e date; run_id bigint; n bigint;
BEGIN
  FOR m IN SELECT generate_series(date_trunc('month', p_start)::date, p_end, interval '1 month')::date LOOP
    s := greatest(m, p_start);
    e := least((m + interval '1 month')::date - 1, p_end);
    INSERT INTO ingestion_runs (source, job_type, start_date, end_date, status)
    VALUES ('ndvi_composites', 'ndvi_features', s, e, 'running') RETURNING id INTO run_id;
    COMMIT;
    BEGIN
      -- LEFT JOIN LATERAL so a day with NO usable composite is explicitly set to NULL (never keeps a stale value)
      UPDATE daily_features f
         SET ndvi = x.ndvi, ndvi_obs_date = x.obs_date
        FROM (
          SELECT d.cell_id, d.date, c.ndvi, c.obs_date
            FROM daily_features d
            LEFT JOIN LATERAL (
              SELECT n.ndvi, n.obs_date FROM ndvi_composites n
               WHERE n.cell_id = d.cell_id
                 AND n.ndvi IS NOT NULL
                 AND n.obs_date <= d.date - p_avail_days
                 AND n.obs_date >  d.date - p_avail_days - 20
               ORDER BY n.obs_date DESC LIMIT 1
            ) c ON true
           WHERE d.date BETWEEN s AND e
        ) x
       WHERE f.cell_id = x.cell_id AND f.date = x.date AND f.date BETWEEN s AND e;
      GET DIAGNOSTICS n = ROW_COUNT;
      UPDATE ingestion_runs SET status = 'success', finished_at = now(), records_read = n, records_updated = n WHERE id = run_id;
    EXCEPTION WHEN OTHERS THEN
      UPDATE ingestion_runs SET status = 'failed', finished_at = now(), error_message = left(SQLERRM, 500) WHERE id = run_id;
    END;
    COMMIT;
  END LOOP;
END $$;
