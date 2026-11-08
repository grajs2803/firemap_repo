# Modelling handoff

What the model person needs from the backend, in the order they will need it.

## 1. Prediction task

For a pilot cell `c` (0.01 degree, about 1 km) and day `d`, predict
`y(c, d) = 1` if the cell has at least one valid fire on any of days `d+1 .. d+H`, else 0 (default `H = 1`).

- **Valid fire** = a row in view `v_fire`: known `cell_id`, confidence `n` or `h`, detection type 0. VIIRS NOAA-20, 375 m pixels.
- Positives are rare (base rate of order 1e-3 per cell-day). Do not report accuracy or ROC-AUC alone. Use **PR-AUC**
  (a random classifier scores about the base rate) and the **Brier score** `BS = (1/N) * sum (p_i - y_i)^2` after calibration.
- Fires are not only forest fires: crop-residue burning and shifting cultivation are in the labels. There is no forest mask yet.

## 2. Data window

| What | Dates | Where it is set |
|---|---|---|
| Fire history (map, grid, backfill) | 2018-04-01 .. 2024-03-18 | `data_window.start_date / end_date` |
| Features + labels for training | 2018-04-01 .. 2020-12-31 (for now) | `data_window.feature_start / feature_end` |

The training period is shorter because weather files exist only for 2018-2020. NDVI rasters exist to 2024. When weather for
2021-2024 is loaded, widen the window: `UPDATE data_window SET feature_end = '2024-03-18';` and re-run the export.
Pilot area: West Singhbhum (Jharkhand) and Bastar (Chhattisgarh), 10,800 cells (`ingest_scope`).

## 3. Tables you will touch

| Table | Content |
|---|---|
| `cells` | 0.01 degree cells: `cell_id`, `lat`, `lon`, `district`, `elevation` |
| `fire_events` / `v_fire` | one row per VIIRS detection / the valid ones |
| `daily_features` | one row per cell per day: `ndvi`, `ndmi`, `fwi`, `temp_c`, `rainfall_mm`, `wind_speed`, `wind_dir`, `fire_count`, `max_frp` |
| `risk_predictions` | `(cell_id, date, model_version)` -> `raw_score`, `calibrated_prob` |

NDVI is attached with an as-of rule: day `d` sees the latest 16-day composite that started at least 18 days earlier (`ndvi_obs_date`).
This is what prevents future information entering the features.

## 4. Getting the training table

```bash
psql -d firemap_real -f backend/db/sql/008_feature_window.sql
cd backend
python -m app.jobs.export_training ../training_data --horizon 1 --neg-rate 0.1
```

Writes one Parquet file per month plus `_meta.json` (label, window, sampling, feature list), and prints the base rate,
positives per year and the percentage of missing values per feature.

Columns: `cell_id, date, fold_space, fold_time, w, <features>, y`.

- Features: `ndvi, ndmi, fwi, temp_c, rainfall_mm, wind_speed, wind_dir, elevation, fires_7d, fires_30d, rain_7d, doy_sin, doy_cos`.
- `fires_7d`, `fires_30d`, `rain_7d` use days `d-7..d-1` and `d-30..d-1` only (the day itself is excluded, so nothing from the label window leaks in).
- `doy_sin, doy_cos` = `sin, cos (2 pi * day_of_year / 365.25)`, so 31 December and 1 January are close.
- `--neg-rate q` keeps all positives and a fraction `q` of negatives. `w` is the weight that undoes the sampling
  (positives 1, kept negatives `1/q`). Train with `sample_weight=w`, or correct afterwards:
  `p = p' * r / (p' * r + (1 - p'))` where `p'` is the probability from a model trained on sampled data and `r` is the ratio of
  the sampled to the true negative-to-positive odds. Using `w` is simpler.
- Rows without all `H` future days are dropped. The first 30 days of the table have a partial `fires_30d`.

## 5. Validation (the part people get wrong)

Neighbouring cells and consecutive days are strongly correlated. A random train/test split leaks and gives inflated scores.

- Split by **time**: `fold_time` (calendar year). Train on earlier years, test on a later one.
- Split by **space**: `fold_space` (district). Train on one district and test on the other.
- Report both. Tune thresholds and calibration only on validation folds.

With 2018-2020 this means three time folds and two space folds. Treat results as a pipeline check, not a final number.

## 6. Plugging a model into the backend

`app/ml/__init__.py: get_model()` returns the model object the API and `run_daily` use. A replacement must provide:

- attributes `version` (string, stored in `risk_predictions.model_version`), `feature_list`, `trained_at`, `metrics`, `is_dummy`;
- `predict_proba(row: dict) -> float` (calibrated probability) and `explain(row: dict) -> dict`.

Important limits at serving time: `build_feature_row` currently passes only `fwi, ndvi, rainfall_mm`. A model that uses
`fires_7d`, `temp_c`, `elevation` etc. needs `build_feature_row` and the daily pipeline extended to produce them
(live fires arrive through `run_daily`, with a lag). Train only on features that can be produced the same way every day.

## 7. Known traps

- No NDVI after 2024, and NDVI is NULL in monsoon cloud: expect missing values; decide how the model handles them.
- FWI is the Canadian system with Canadian day-length constants; it is a feature, not ground truth in the tropics.
- Weather is ERA5 reanalysis at about 0.1 degree points mapped onto 0.01 degree cells, so all cells near a point share values.
- NRT and SP FIRMS data can differ slightly; the project uses the standard-processing archive for history.
