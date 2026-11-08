# SQL files

Run once, in order, in psql against the main database (for example `psql -d firemap_real -f 002_mvp.sql`).
The tables `cells`, `fire_events`, `ingestion_runs`, `daily_features` and `risk_predictions` must already exist
(they come from the ORM models).

| Order | File | Purpose |
|---|---|---|
| 1 | `001_pilot.sql` | Optional analysis: sanity checks, district ranking, `pilot_cells`. |
| 2 | `002_mvp.sql` | Monthly partitions for `daily_features`, `ingest_scope`, procedure `build_label_layer`. |
| 3 | `003_weather.sql` | `weather_points`, `cell_weather_map`, `weather_daily`, procedure `build_weather_features`. |
| 4 | `004_ndvi.sql` | `ndvi_composites`, procedure `build_ndvi_features`. |
| 5 | `005_daily.sql` | `ingest_scope.rolling`, `weather_daily.method`, updated `build_weather_features`. |
| 6 | `006_fire_view.sql` | View `v_fire` (the one definition of a fire) and table `data_window` (the project's date range, 2018-04-01 to 2024-03-18). |
| 7 | `007_label_layer_v_fire.sql` | `build_label_layer` reads `v_fire`, so labels and the map agree. |

Notes
- `002_mvp.sql` ends with an example scope for three Mizoram districts and a `CALL build_label_layer`. Edit the district
  names to your pilot (for example West Singhbhum and Bastar) before running, or delete those last lines.
- `005_daily.sql` has a commented `UPDATE ingest_scope SET rolling = true ...`; uncomment it for the districts that the daily run should extend.
- `v_fire` = `cell_id` known, confidence `n` or `h`, `detection_type` 0 or NULL. To change the date range, `UPDATE data_window SET start_date = ..., end_date = ...;`
  and re-run `build_fire_grid`. The window is applied by the map, the grid job, the detail endpoint and the backfill; the label layer is not clipped (the live pipeline writes later dates).
- `002_mvp.sql` only works while `daily_features` is empty (it converts the table to partitions).
