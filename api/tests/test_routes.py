def test_health_needs_no_login(anonymous_client):
    response = anonymous_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_returns_user_and_shared_dataset(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json() == {"username": "guest", "groups": [], "dataset": "shared"}


def test_reads_json_file(client):
    response = client.get("/api/data/rides.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"rides": []}


def test_reads_png_file(client):
    response = client.get("/api/data/spec_ride_001.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"\x89PNG fake"


def test_missing_file_is_404(client):
    response = client.get("/api/data/ride_ride_999.json")
    assert response.status_code == 404


def test_unsafe_file_name_is_400(client):
    response = client.get("/api/data/rides.csv")
    assert response.status_code == 400


def test_data_without_login_is_401(anonymous_client):
    assert anonymous_client.get("/api/data/rides.json").status_code == 401
    assert anonymous_client.get("/api/me").status_code == 401
