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

Notes
- `002_mvp.sql` ends with an example scope for three Mizoram districts and a `CALL build_label_layer`. Edit the district
  names to your pilot (for example West Singhbhum and Bastar) before running, or delete those last lines.
- `005_daily.sql` has a commented `UPDATE ingest_scope SET rolling = true ...`; uncomment it for the districts that the daily run should extend.
- `build_label_layer` counts a fire when `confidence IN ('n','h')`. The history map (`build_fire_grid`) also requires
  `COALESCE(detection_type, 0) = 0`. Make them the same if the labels will be used for training.
- `002_mvp.sql` only works while `daily_features` is empty (it converts the table to partitions).
