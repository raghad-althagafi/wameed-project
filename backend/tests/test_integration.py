# test fire detection
def test_fire_detection_integration(client):
    payload = {
        "lat": 18.1863929,
        "lon": 42.7553159,
        "datetime": "2023-09-10T10:00:00"
    } #input data

    response = client.post("/fire-detection", json=payload) # send request and recieve response
    data = response.get_json() # convert the response

    # make sure
    assert response.status_code == 200
    assert data["ok"] is True
    assert "is_detected" in data
    assert "lat" in data
    assert "lon" in data

# test invalid input in detections 
def test_invalid_input_in_detection(client):
    payload = {
        "lat": "invalid",
        "lon": 42.7553159,
        "datetime": "2023-09-10T10:00:00"
    }

    response = client.post("/fire-detection", json=payload)
    data = response.get_json()

    assert response.status_code == 500
    assert data["ok"] is False
    assert data["error"] == "internal_server_error"

# test fire spread direction
def test_fire_spread_direction_integration(client):
    payload = {
        "lat": 18.1863929,
        "lon": 42.7553159,
        "datetime": "2023-09-10T10:00:00"
    }

    response = client.post("/fire-spread-direction", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert "spread_direction_ar" in data
    assert isinstance(data["spread_direction_ar"], str)

# test fire burned area
def test_fire_burned_area_integration(client):
    payload = {
        "lat": 18.1863929,
        "lon": 42.7553159,
        "datetime": "2023-09-10T10:00:00"
    }

    response = client.post("/fire-burned-area", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert "burned_area_km2" in data
    assert isinstance(data["burned_area_km2"], float)