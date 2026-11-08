# EmberGrid backend

Flask + PostgreSQL API for fire-risk maps and fire history. Endpoint reference: [`docs/API.md`](../docs/API.md).
Background for the model person: [`docs/MODELING_HANDOFF.md`](../docs/MODELING_HANDOFF.md).

## Run it (after the data is loaded)

From `backend/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env            # then edit DATABASE_URL, JWT_SECRET_KEY, CORS_ORIGINS

# one-time SQL (in order; see db/sql/README.md): 006 fire view + data window, 007 label layer, 008 feature window
psql -d firemap_real -f db/sql/006_fire_view.sql -f db/sql/007_label_layer_v_fire.sql -f db/sql/008_feature_window.sql

# after the data load (python -m app.jobs.load_ndvi features 2018-04-01 2020-12-31 and the steps before it):
python -m app.jobs.predict_day 2018-04-01 2020-12-31 15     # risk for every 15th day (about 70 days); drop the 15 to score every day
python -m app.jobs.build_fire_grid                          # fire history map; must end with OK

python run.py                                               # http://localhost:5000
```

The map page (`/map`) shows a card when you rest the mouse on a place: its name, fires per year as a bar chart, and the latest NDVI, fire weather index,
temperature, rain, wind and predicted risk (conditions exist only inside the pilot districts). It uses `GET /api/v1/history/point`.

Check it: `curl localhost:5000/health`, `curl localhost:5000/api/v1/status`, open `http://localhost:5000/map`.
Production: `gunicorn --bind 0.0.0.0:5000 --workers 2 run:app` with `FLASK_ENV=production` (needs `JWT_SECRET_KEY` and `CORS_ORIGINS`), or the `Dockerfile`.

Without the `predict_day` step the `risk` layer has no data for the loaded years. The `ndvi` and `fwi` layers, the cell endpoints and the
fire history work without it. A date range is only visible in the `risk` layer for the days that were scored.

### Tests

```bash
createdb embergrid_pytest                    # scratch database: its name must contain "test", all its tables are rebuilt
export TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/embergrid_pytest
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Demo: fire history grid over India
A map of India split into 0.1 degree cells (about 11 km). Each cell is coloured by the number of
fires detected there up to the month chosen on the slider (cumulative). Only `fire_events` is used.

### Run

From `backend/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
echo 'DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/firemap_real' > .env
psql -d firemap_real -f db/sql/006_fire_view.sql
python -m app.jobs.build_fire_grid
python run.py
```

Open http://localhost:5000/map. A `@` in the password must be written `%40`.
The job ends with `OK` when the grid total equals the `fire_events` total. Re-run it after loading more fire data.

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /map` | the page |
| `GET /api/v1/history/months` | `{first, last}` month with data |
| `GET /api/v1/history/risk?date=YYYY-MM-DD` | mean `calibrated_prob` per 0.1 degree block for the active model (default: latest date with predictions) |
| `GET /api/v1/history/detail?bbox=w,s,e,n&to=YYYY-MM-DD` | fire counts per 0.01 degree cell inside the bbox (max 9 square degrees, 30,000 cells) |
| `GET /api/v1/history/grid?to=YYYY-MM-DD` | cells `[row, col, count]` summed from the first month up to `to` (default: all) |

Cell rectangle: south = row x 0.1, north = (row + 1) x 0.1, west = col x 0.1, east = (col + 1) x 0.1.
A fire is a `fire_events` row with confidence `n` or `h` and detection type 0 (or NULL).

### Page controls

History / Risk toggle at the top of the panel. In History mode, zooming to level 9 or closer swaps the 0.1 degree
grid for 0.01 degree cells of the current viewport. Risk mode only shows areas that have predictions (the pilot districts).

### Loading more fire history

```bash
export FIRMS_MAP_KEY=your_key
python -m app.jobs.backfill_fire 2024-03-19 2025-12-31 [SOURCE]   # default source VIIRS_NOAA20_SP, one request per month
python -m app.jobs.build_fire_grid
```

The backfill refuses dates outside `data_window` (2018-04-01 to 2024-03-18); widen the window first if you really want more. Re-running is safe (duplicates are skipped). Use `run_daily` for the most recent days; `purge_nrt` removes NRT rows that overlap SP data.
Only rows with a `cell_id` are counted, so fires outside the loaded cells are ignored.
