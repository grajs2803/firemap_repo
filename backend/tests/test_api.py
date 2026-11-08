import pytest

from tests.conftest import CELLS, PROBS

H = "/api/v1/heatmap"


def error_code(resp):
    j = resp.get_json()
    assert set(j["error"]) == {"code", "message", "details"}
    return j["error"]["code"]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json() == {"status": "ok", "database": "up"}


def test_status(client):
    j = client.get("/api/v1/status").get_json()
    assert j["data_window"] == {"start": "2018-04-01", "end": "2024-03-18"}
    assert j["feature_window"] == {"start": "2018-04-01", "end": "2020-12-31"}
    assert j["features"]["latest_date"] == "2019-04-11"
    assert j["risk"]["latest_date"] == "2019-04-11"
    assert j["fire_history"] == {"first_month": "2019-03-01", "last_month": "2019-04-01"}
    assert any(r["job"] == "label_layer" for r in j["last_runs"])


def test_heatmap_risk_defaults_to_latest_date_with_levels(client):
    j = client.get(H).get_json()
    assert j["metadata"]["date"] == "2019-04-11" and j["metadata"]["layer"] == "risk"
    by_id = {f["id"]: f["properties"] for f in j["features"]}
    assert {k: v["value"] for k, v in by_id.items()} == PROBS
    assert by_id["r2200c8500"]["level"] == "low" and by_id["r2200c8501"]["level"] == "high" and by_id["r2201c8500"]["level"] == "extreme"
    assert j["features"][0]["geometry"]["type"] == "Polygon"
    assert len(j["bbox"]) == 4 and j["metadata"]["truncated"] is False and j["metadata"]["next_offset"] is None


@pytest.mark.parametrize("layer,value", [("ndvi", 0.5), ("fwi", 12.0)])
def test_heatmap_feature_layers(client, layer, value):
    j = client.get(f"{H}?layer={layer}&date=2019-04-10").get_json()
    assert {f["properties"]["value"] for f in j["features"]} == {value}
    assert all(f["properties"]["level"] is None for f in j["features"])


def test_heatmap_ndmi_is_not_offered(client):
    r = client.get(f"{H}?layer=ndmi")
    assert r.status_code == 400 and error_code(r) == "bad_request"


def test_heatmap_no_data_for_date_is_404(client):
    r = client.get(f"{H}?layer=risk&date=2019-04-10")
    assert r.status_code == 404 and error_code(r) == "not_found"


def test_heatmap_empty_bbox_is_200_with_no_cells(client):
    j = client.get(f"{H}?bbox=0,0,1,1").get_json()
    assert j["features"] == [] and j["metadata"]["cell_count"] == 0


def test_heatmap_bbox_selects_cells_by_centre(client):
    j = client.get(f"{H}?bbox=85.0,22.0,85.01,22.01").get_json()
    assert [f["id"] for f in j["features"]] == ["r2200c8500"]


def test_heatmap_paging(client):
    a = client.get(f"{H}?limit=2").get_json()
    assert a["metadata"]["cell_count"] == 2 and a["metadata"]["next_offset"] == 2 and a["metadata"]["truncated"]
    b = client.get(f"{H}?limit=2&offset=2").get_json()
    assert b["metadata"]["cell_count"] == 1 and b["metadata"]["next_offset"] is None
    assert sorted(f["id"] for f in a["features"] + b["features"]) == sorted(c[0] for c in CELLS)


@pytest.mark.parametrize("q", ["limit=0", "limit=abc", "limit=999999", "offset=-1", "format=png", "bbox=1,2,3"])
def test_heatmap_bad_parameters(client, q):
    r = client.get(f"{H}?{q}")
    assert r.status_code == 400 and error_code(r) == "bad_request"


def test_heatmap_tiles_is_a_stub(client):
    j = client.get(f"{H}?format=tiles").get_json()
    assert j["format"] == "tiles" and j["metadata"]["stub"] is True


def test_cell_detail(client):
    j = client.get("/api/v1/cells/r2201c8500?date=2019-04-10").get_json()
    assert j["location"]["district"] == "D1" and j["static"]["elevation"] == 500.0
    p = j["prediction"]
    assert 0 < p["probability"] < 1 and p["level"] in {"low", "moderate", "high", "extreme"}
    assert set(p["contributions"]) == {"fwi", "ndvi", "rainfall_mm"}


def test_cell_unknown_and_no_features(client):
    assert client.get("/api/v1/cells/r0000c0000").status_code == 404
    assert client.get("/api/v1/cells/r2201c8500?date=2019-01-01").status_code == 404


def test_timeseries(client):
    j = client.get("/api/v1/cells/r2200c8500/timeseries?feature=fwi&start=2019-04-01&end=2019-04-30").get_json()
    assert [p["date"] for p in j["points"]] == ["2019-04-10", "2019-04-11"] and j["points"][0]["value"] == 12.0
    r = client.get("/api/v1/cells/r2200c8500/timeseries?feature=risk&start=2019-04-10&end=2019-04-11").get_json()
    assert all(0 < p["value"] < 1 and "level" in p for p in r["points"])


@pytest.mark.parametrize("q", ["feature=ndmi&start=2019-04-01&end=2019-04-02", "feature=fwi&start=bad&end=2019-04-02",
                               "feature=fwi&start=2019-04-05&end=2019-04-01", "feature=fwi&start=2018-01-01&end=2019-12-31"])
def test_timeseries_bad_parameters(client, q):
    r = client.get(f"/api/v1/cells/r2200c8500/timeseries?{q}")
    assert r.status_code == 400 and error_code(r) == "bad_request"


def test_history_months_and_grid_count_only_valid_fires_inside_the_window(client):
    assert client.get("/api/v1/history/months").get_json() == {"first": "2019-03-01", "last": "2019-04-01"}
    g = client.get("/api/v1/history/grid").get_json()
    assert g["total_fires"] == 3 and g["cell_deg"] == 0.1          # e1, e2, e3 only
    assert client.get("/api/v1/history/grid?to=2019-03-31").get_json()["total_fires"] == 2


def test_history_detail(client):
    j = client.get("/api/v1/history/detail?bbox=85,22,85.1,22.1").get_json()
    assert j["cell_deg"] == 0.01 and sorted(j["cells"]) == [[2200, 8500, 2], [2200, 8501, 1]]
    assert client.get("/api/v1/history/detail?bbox=85,22,85.1,22.1&to=2019-03-31").get_json()["cells"] == [[2200, 8500, 2]]
    assert client.get("/api/v1/history/detail").status_code == 400
    assert client.get("/api/v1/history/detail?bbox=60,5,90,30").status_code == 400


def test_history_risk(client):
    j = client.get("/api/v1/history/risk").get_json()
    assert j["date"] == "2019-04-11" and j["cells"] == [[220, 850, round((0.05 + 0.30 + 0.80) / 3, 4)]]
    assert client.get("/api/v1/history/risk?date=2001-01-01").status_code == 404


def test_cors_and_gzip(client):
    r = client.get(f"{H}?limit=3", headers={"Origin": "http://localhost:5173", "Accept-Encoding": "gzip"})
    assert r.headers["Access-Control-Allow-Origin"] in ("*", "http://localhost:5173")
    assert r.headers.get("Content-Encoding") == "gzip"
    pre = client.options(f"{H}", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
                                          "Access-Control-Request-Headers": "authorization"})
    assert pre.status_code == 200 and "authorization" in pre.headers["Access-Control-Allow-Headers"].lower()


def test_auth_flow_and_error_shape(client):
    creds = {"email": "tester@example.com", "password": "a-long-enough-password-1"}
    assert client.post("/api/v1/auth/register", json=creds).status_code == 201
    dup = client.post("/api/v1/auth/register", json=creds)
    assert dup.status_code == 409 and error_code(dup) == "conflict"
    bad = client.post("/api/v1/auth/login", json={**creds, "password": "wrong"})
    assert bad.status_code == 401 and error_code(bad) == "unauthorized"
    tokens = client.post("/api/v1/auth/login", json=creds).get_json()
    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tokens["access_token"]})
    assert me.status_code == 200 and me.get_json()["email"] == creds["email"]
    assert client.get("/api/v1/auth/me").status_code == 401
    assert error_code(client.get("/api/v1/auth/me")) == "unauthorized"
    new = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert new.status_code == 200 and "access_token" in new.get_json()
    out = client.post("/api/v1/auth/logout", json={"refresh_token": new.get_json().get("refresh_token", tokens["refresh_token"])})
    assert out.status_code == 200
