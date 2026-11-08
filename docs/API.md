# EmberGrid API

Base URL `http://localhost:5000`. JSON everywhere. CORS is enabled for `/api/*` (origins from `CORS_ORIGINS`) and responses over 1 KB are gzip-compressed.
Dates are `YYYY-MM-DD`. A bounding box is `bbox=min_lon,min_lat,max_lon,max_lat`. Cells are 0.01 degree squares with ids such as `r2200c8500`
(`row = floor(lat / 0.01)`, `col = floor(lon / 0.01)`).

## Errors (all endpoints)

```json
{"error": {"code": "bad_request", "message": "layer must be one of ['fwi', 'ndvi', 'risk']", "details": null}}
```
Codes: `bad_request` 400, `unauthorized` 401, `forbidden` 403, `not_found` 404, `conflict` 409, `database_error` 500.

## Service

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status":"ok","database":"up"}`; status 503 and `"degraded"` if the database is unreachable |
| `GET /api/v1/status` | what data is loaded: `data_window`, `feature_window`, `features{first_date,latest_date}`, `risk{model_version,latest_date,dates}`, `fire_history{first_month,last_month}`, `model{version,is_dummy}`, `last_runs[]`. Use it for "data updated on ..." |

## Risk and feature maps

`GET /api/v1/heatmap`

| Parameter | Default | Notes |
|---|---|---|
| `layer` | `risk` | `risk`, `ndvi`, `fwi` (`ndmi` is not available: nothing loads it) |
| `date` | latest date with data | `risk`: latest date with predictions for the active model |
| `bbox` | none | a cell is included if its centre is inside |
| `format` | `geojson` | `tiles` returns a URL template for a tile server that does not exist yet (`metadata.stub: true`) |
| `limit` | 15000 | 1 to 20000 |
| `offset` | 0 | cells are ordered by `cell_id` |

Response: GeoJSON `FeatureCollection`. Each feature has a square `Polygon` and `properties {cell_id, value, level}`
(`level` only for `risk`: `low` < 0.10, `moderate` < 0.25, `high` < 0.50, `extreme`). Also `bbox` and
`metadata {date, layer, model_version, cell_size_deg, legend, cell_count, total_matching, offset, limit, next_offset, truncated}`.
When `next_offset` is not null, request again with `offset=next_offset`.
404 if the date has no data for the layer; 200 with zero features if the bbox contains nothing.

## One cell

- `GET /api/v1/cells/{cell_id}?date=` : location, district, elevation, weather (`temp_c, rainfall_mm, wind_speed, wind_dir`) and
  `prediction {probability, logit, base_value, contributions{feature:{value,shap}}, level, model_version}`.
  Date defaults to the cell's latest day. The prediction is computed live, so it works for any day with features.
- `GET /api/v1/cells/{cell_id}/timeseries?feature=&start=&end=` : `feature` is one of `ndvi, fwi, rainfall_mm, temp_c, wind_speed, risk`;
  range at most 366 days. Returns `label`, `unit` and `points[{date, value, level?}]`.

Only cells of the loaded pilot districts have features; any other cell gives 404.

## Fire history (2018-04-01 to 2024-03-18, all India)

A fire is a satellite detection with confidence `n` or `h`, detection type 0, inside a known cell.

| Endpoint | Returns |
|---|---|
| `GET /api/v1/history/months` | `{first, last}` months with data |
| `GET /api/v1/history/grid?to=` | `{cell_deg: 0.1, cell_count, total_fires, max_count, cells: [[row, col, count], ...]}` summed from the first month up to `to`. Cell south-west corner = `(row * 0.1, col * 0.1)` |
| `GET /api/v1/history/detail?bbox=&to=` | same idea at `cell_deg: 0.01`, only inside `bbox` (required, at most 9 square degrees); `truncated: true` if more than 30000 cells |
| `GET /api/v1/history/point?lat=&lon=&deg=` | everything for a hover card at one point (`deg` = `0.1` block, default, or `0.01` cell): `cell_id`, `place{state,district,label}`, `elevation`, `fires{deg,area,total,yearly[{year,n,partial}],from,to}` (one entry per year of the data window; `partial` = the window covers only part of that year), `latest{date,ndvi,fwi,temp_c,rainfall_mm,wind_speed,risk{probability,level,model_version}}` or `null` outside the pilot districts. `place` is `null` where no cell exists. 400 for coordinates outside 6-38 N, 67-98 E |
| `GET /api/v1/history/risk?date=` | mean predicted probability per 0.1 degree block `[row, col, p]` for the active model (default: latest date) |

## Authentication

Only `/me` requires a token; the data endpoints above are open.

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/v1/auth/register` | `{email, password}` | 201 user |
| `POST /api/v1/auth/login` | `{email, password}` | `{access_token, refresh_token, expires_in: 900}` |
| `POST /api/v1/auth/refresh` | `{refresh_token}` | new tokens |
| `POST /api/v1/auth/logout` | `{refresh_token}` | `{status: "logged out"}` |
| `GET /api/v1/auth/me` | header `Authorization: Bearer <access_token>` | `{id, email, is_active}` |
