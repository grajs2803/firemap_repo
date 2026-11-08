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
| `GET /api/v1/history/grid?to=YYYY-MM-DD` | cells `[row, col, count]` summed from the first month up to `to` (default: all) |

Cell rectangle: south = row x 0.1, north = (row + 1) x 0.1, west = col x 0.1, east = (col + 1) x 0.1.
A fire is a `fire_events` row with confidence `n` or `h` and detection type 0 (or NULL).
