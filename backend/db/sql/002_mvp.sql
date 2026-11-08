-- EmberGrid MVP data layer: small slice now, same machinery for all-India later.
-- Safe to run when daily_features is EMPTY (it is, on firemap_real). Re-runnable (idempotent).
-- Postgres >= 12 (partitioned FK) and >= 11 (procedures with COMMIT). Works on 14.

-- 0) indexes the jobs depend on
CREATE INDEX IF NOT EXISTS ix_fire_events_date_cell ON fire_events (local_date, cell_id);
CREATE INDEX IF NOT EXISTS ix_cells_district        ON cells (district);

-- 1) daily_features -> monthly range partitions. Only valid while the table is empty.
--    Why: the heatmap reads ONE date (partition pruning touches 1 of N partitions), retention/rebuild = DROP/DETACH
--    a month instead of a giant DELETE+VACUUM, each month's index stays small, and national scale needs this.
DO $$
BEGIN
  IF (SELECT count(*) FROM daily_features) > 0 THEN
    RAISE EXCEPTION 'daily_features is not empty; migrate with a copy instead';
  END IF;
END $$;
ALTER TABLE daily_features RENAME TO daily_features_old;
CREATE TABLE daily_features (LIKE daily_features_old INCLUDING DEFAULTS) PARTITION BY RANGE (date);
DROP TABLE daily_features_old;            -- must go BEFORE the new indexes: a renamed table keeps its index names
ALTER TABLE daily_features ADD PRIMARY KEY (cell_id, date);
ALTER TABLE daily_features ADD FOREIGN KEY (cell_id) REFERENCES cells (cell_id);
CREATE INDEX ix_daily_features_date ON daily_features (date);

CREATE OR REPLACE FUNCTION ensure_df_partitions(p_start date, p_end date) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE m date;
BEGIN
  FOR m IN SELECT generate_series(date_trunc('month', p_start)::date, p_end, interval '1 month')::date LOOP
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF daily_features FOR VALUES FROM (%L) TO (%L)',
                   'daily_features_' || to_char(m, 'YYYY_MM'), m, (m + interval '1 month')::date);
  END LOOP;
END $$;

-- 2) scope = what is loaded. A (cell,date) row exists ONLY if its district is in scope for that date.
--    Absent row means "not loaded" (unknown), never "no fire". Growing coverage = INSERT a district / widen the dates.
CREATE TABLE IF NOT EXISTS ingest_scope (
  district  varchar PRIMARY KEY,
  from_date date NOT NULL,
  to_date   date NOT NULL,
  added_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (from_date <= to_date)
);

-- 3) the job: one month per chunk, own transaction, own ingestion_runs row, failure isolated to that chunk.
CREATE OR REPLACE PROCEDURE build_label_layer(p_start date, p_end date)
LANGUAGE plpgsql AS $$
DECLARE m date; s date; e date; run_id bigint; n_before bigint; n_after bigint; n_written bigint;
BEGIN
  PERFORM ensure_df_partitions(p_start, p_end);
  COMMIT;
  FOR m IN SELECT generate_series(date_trunc('month', p_start)::date, p_end, interval '1 month')::date LOOP
    s := greatest(m, p_start);
    e := least((m + interval '1 month')::date - 1, p_end);
    INSERT INTO ingestion_runs (source, job_type, start_date, end_date, status)
    VALUES ('fire_events', 'label_layer', s, e, 'running') RETURNING id INTO run_id;
    COMMIT;
    BEGIN
      SELECT count(*) INTO n_before FROM daily_features WHERE date BETWEEN s AND e;   -- index-only scan on one partition
      INSERT INTO daily_features (cell_id, date, fire_count, max_frp)
        SELECT c.cell_id, d::date, COALESCE(p.fire_count, 0), p.max_frp
        FROM ingest_scope sc
        JOIN cells c ON c.district = sc.district
        CROSS JOIN LATERAL generate_series(greatest(s, sc.from_date), least(e, sc.to_date), interval '1 day') AS d
        LEFT JOIN (
          SELECT cell_id, local_date, count(*)::int AS fire_count, max(frp) AS max_frp
          FROM fire_events
          WHERE confidence IN ('n','h') AND local_date BETWEEN s AND e
          GROUP BY cell_id, local_date
        ) p ON p.cell_id = c.cell_id AND p.local_date = d::date
        ON CONFLICT (cell_id, date) DO UPDATE
          SET fire_count = EXCLUDED.fire_count, max_frp = EXCLUDED.max_frp;
      GET DIAGNOSTICS n_written = ROW_COUNT;
      SELECT count(*) INTO n_after FROM daily_features WHERE date BETWEEN s AND e;
      UPDATE ingestion_runs SET status = 'success', finished_at = now(), records_read = n_written,
             records_inserted = n_after - n_before, records_updated = n_written - (n_after - n_before) WHERE id = run_id;
    EXCEPTION WHEN OTHERS THEN
      UPDATE ingestion_runs SET status = 'failed', finished_at = now(), error_message = left(SQLERRM, 500) WHERE id = run_id;
    END;
    COMMIT;
  END LOOP;
END $$;

-- 4) MVP slice: ONE region, ONE season (latest complete one in your data). ~9k cells x 90 days = ~0.8M rows.
INSERT INTO ingest_scope (district, from_date, to_date) VALUES
  ('Mizoram / Lunglei',   '2023-02-01', '2023-04-30'),
  ('Mizoram / Lawngtlai', '2023-02-01', '2023-04-30'),
  ('Mizoram / Mamit',     '2023-02-01', '2023-04-30')
ON CONFLICT (district) DO UPDATE SET from_date = EXCLUDED.from_date, to_date = EXCLUDED.to_date;

CALL build_label_layer('2023-02-01', '2023-04-30');

-- 5) check the run, then the data
SELECT id, job_type, start_date, end_date, status, records_inserted, records_updated, left(error_message,80) AS err
FROM ingestion_runs WHERE job_type = 'label_layer' ORDER BY id DESC LIMIT 6;

SELECT (SELECT count(*) FROM daily_features) AS rows,
       (SELECT count(*) FROM daily_features WHERE fire_count > 0) AS positives,
       (SELECT count(*) FROM cells c JOIN ingest_scope s USING (district)) * 89 AS expected_rows;  -- 89 days = Feb 28 + Mar 31 + Apr 30
-- ~ later, to GROW: INSERT more districts into ingest_scope, widen to_date, then CALL build_label_layer(<range>) again.
