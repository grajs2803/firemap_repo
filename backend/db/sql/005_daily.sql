-- EmberGrid daily run: schema additions. Safe to re-run.

-- Districts flagged rolling get to_date moved forward to the run date by run_daily.
ALTER TABLE ingest_scope  ADD COLUMN IF NOT EXISTS rolling boolean NOT NULL DEFAULT false;

-- Where a weather value came from: NULL/'era5' = ERA5 archive (final), 'forecast' = provisional, replaced by ERA5 once published.
ALTER TABLE weather_daily ADD COLUMN IF NOT EXISTS method varchar;

-- Copy weather onto daily_features, recording provenance in weather_method (era5_nearest | forecast_nearest).
CREATE OR REPLACE PROCEDURE build_weather_features(p_start date, p_end date)
LANGUAGE plpgsql AS $$
DECLARE m date; s date; e date; run_id bigint; n bigint;
BEGIN
  FOR m IN SELECT generate_series(date_trunc('month', p_start)::date, p_end, interval '1 month')::date LOOP
    s := greatest(m, p_start);
    e := least((m + interval '1 month')::date - 1, p_end);
    INSERT INTO ingestion_runs (source, job_type, start_date, end_date, status)
    VALUES ('weather_daily', 'weather_features', s, e, 'running') RETURNING id INTO run_id;
    COMMIT;
    BEGIN
      UPDATE daily_features f
         SET temp_c = w.temperature_2m_mean, rainfall_mm = w.precipitation_sum,
             wind_speed = w.wind_speed_10m_mean, wind_dir = w.wind_direction_10m_dominant,
             fwi = w.fwi, weather_method = coalesce(w.method, 'era5') || '_nearest'
        FROM cell_weather_map cm
        JOIN weather_daily w ON w.weather_point_id = cm.weather_point_id
       WHERE f.cell_id = cm.cell_id AND f.date = w.date AND f.date BETWEEN s AND e;
      GET DIAGNOSTICS n = ROW_COUNT;
      UPDATE ingestion_runs SET status = 'success', finished_at = now(), records_read = n, records_updated = n WHERE id = run_id;
    EXCEPTION WHEN OTHERS THEN
      UPDATE ingestion_runs SET status = 'failed', finished_at = now(), error_message = left(SQLERRM, 500) WHERE id = run_id;
    END;
    COMMIT;
  END LOOP;
END $$;

-- Mark the pilot districts as rolling (EDIT names; copy them exactly, diacritics included):
-- UPDATE ingest_scope SET rolling = true WHERE district IN ('Jhārkhand / Pashchimi Singhbhum', 'Chhattīsgarh / Bastar');
