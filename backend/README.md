# EmberGrid backend

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
