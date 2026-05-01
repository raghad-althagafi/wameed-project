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

# test fire prediction integration
def test_fire_prediction_integration(client):
    payload = {
        "lat": 17.53960592243366,
        "lon": 42.93497900449253,
        "datetime": "2025-07-04T10:14:00+00:00"
    }

    response = client.post("/fire-prediction", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert "status" in data
    assert "risk_level" in data
    assert "predicted_at" in data
    assert "features" in data



# test missing fields in fire prediction
def test_missing_prediction(client):
    payload = {
        # lat is missing
        "lon": 42.93497900449253,
        "datetime": "2025-07-04T10:14:00+00:00"
    }

    response = client.post("/fire-prediction", json=payload)
    data = response.get_json()

    assert response.status_code == 400
    assert data["ok"] is False
    assert data["error"] == "missing_lat_lon"

# test save and fetch fire prediction
def test_save_fetch_prediction(client):
    payload = {
        "area_name": "test",
        "is_predicted": True,
        "lat": 17.53960592243366,
        "lng": 42.93497900449253,
        "risk_level": "high",
        "predicted_at": "2025-07-04T10:14:00+00:00"
    }

    # save
    post_response = client.post("/api/predictions", json=payload)
    post_data = post_response.get_json()

    assert post_response.status_code == 201
    assert post_data["ok"] is True
    assert "id" in post_data

    saved_id = post_data["id"]

    # fetch
    get_response = client.get("/api/predictions")
    get_data = get_response.get_json()

    assert get_response.status_code == 200
    assert get_data["ok"] is True
    assert "data" in get_data
    assert isinstance(get_data["data"], list)

    # make sure the saved prediction exists in fetched results
    found = False
    for item in get_data["data"]:
        if item.get("id") == saved_id:
            found = True
            assert item["Area_name"] == "test"
            assert item["risk_level"] == "high"
            assert item["is_Predicted"] is True
            break
    assert found is True

# test fire threat integration
def test_threat_integration(client):
    payload = {
        "lat": 17.53960592243366,
        "lon": 42.93497900449253,
        "datetime": "2025-07-04T10:14:00+00:00"
    }

    response = client.post("/fire-threat", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert "threat_score" in data
    assert "threat_level" in data
    assert isinstance(data["threat_score"], (int, float))
    assert isinstance(data["threat_level"], str)