-- EmberGrid weather layer. Weather lives at the POINT level (103 points for Bastar, ~3k nationally) and is joined to
-- cells through a map, instead of being copied into 57k cells x every day. Only the final feature copy is per-cell.

CREATE TABLE IF NOT EXISTS weather_points (
  weather_point_id varchar PRIMARY KEY,
  lat double precision NOT NULL,
  lon double precision NOT NULL,
  elevation_m double precision
);

CREATE TABLE IF NOT EXISTS cell_weather_map (
  cell_id          varchar PRIMARY KEY REFERENCES cells (cell_id),
  weather_point_id varchar NOT NULL REFERENCES weather_points (weather_point_id)
);
CREATE INDEX IF NOT EXISTS ix_cwm_point ON cell_weather_map (weather_point_id);

CREATE TABLE IF NOT EXISTS weather_daily (
  weather_point_id varchar NOT NULL REFERENCES weather_points (weather_point_id),
  date date NOT NULL,
  temperature_2m_mean double precision, temperature_2m_max double precision, temperature_2m_min double precision,
  precipitation_sum double precision, relative_humidity_2m_mean double precision,
  wind_speed_10m_mean double precision, wind_speed_10m_max double precision, wind_direction_10m_dominant double precision,
  ffmc double precision, dmc double precision, dc double precision,
  isi double precision, bui double precision, fwi double precision,
  PRIMARY KEY (weather_point_id, date)
);
CREATE INDEX IF NOT EXISTS ix_weather_daily_date ON weather_daily (date);

-- Copy weather onto daily_features. Rows only EXIST where ingest_scope says so; this job fills columns, never creates rows.
-- Owns: temp_c, rainfall_mm, wind_speed, wind_dir, fwi, weather_method. One month per chunk, logged in ingestion_runs.
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
             fwi = w.fwi, weather_method = 'era5_nearest'
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
