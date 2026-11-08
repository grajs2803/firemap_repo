# EmberGrid backend

## Demo: fire history grid over India

A bare-minimum working model: a map of India where each grid cell is coloured by how many
fires were detected there, with a month slider (and play button) so the grid fills in over time.
It uses only the `fire_events` table.

```
fire_events --(build_fire_grid job)--> fire_grid_01 --(/api/v1/history/*)--> /map page
```

### Run it

From `backend/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

# point the app at the database that holds fire_events (note the +psycopg2 driver)
echo 'DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/firemap_real' > .env
# if the password contains "@", write it as %40

python -m app.jobs.build_fire_grid     # one-off, builds fire_grid_01; ends with "check: ... -> OK"
python run.py                           # then open http://localhost:5000/map
```

The map needs internet (Leaflet and OpenStreetMap tiles are loaded from public servers).

### Endpoints

| Endpoint | Meaning |
|---|---|
| `GET /map` | the demo page |
| `GET /api/v1/history/months` | first/last month with data and fires per month |
| `GET /api/v1/history/grid?res=0.5&from=2022-03-01&to=2022-03-31&bbox=min_lon,min_lat,max_lon,max_lat` | cells as `[row, col, count]`; `res` is 0.1, 0.5 or 1.0 degrees; `from`, `to`, `bbox` optional |

A cell's rectangle is south = row x cell_deg, north = (row + 1) x cell_deg, west = col x cell_deg,
east = (col + 1) x cell_deg. A fire is a `fire_events` row with confidence `n` or `h` and detection type 0
(or NULL). Re-run the job after loading more fire data; it rebuilds each month idempotently.
