-- build_label_layer now counts fires through v_fire (same definition as the map). Run after 006.
CREATE OR REPLACE PROCEDURE public.build_label_layer(IN p_start date, IN p_end date)
 LANGUAGE plpgsql
AS $procedure$
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
      SELECT count(*) INTO n_before FROM daily_features WHERE date BETWEEN s AND e;
      INSERT INTO daily_features (cell_id, date, fire_count, max_frp)
        SELECT c.cell_id, d::date, COALESCE(p.fire_count, 0), p.max_frp
        FROM ingest_scope sc
        JOIN cells c ON c.district = sc.district
        CROSS JOIN LATERAL generate_series(greatest(s, sc.from_date), least(e, sc.to_date), interval '1 day') AS d
        LEFT JOIN (
          SELECT cell_id, local_date, count(*)::int AS fire_count, max(frp) AS max_frp
          FROM v_fire
          WHERE local_date BETWEEN s AND e
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
END $procedure$;
