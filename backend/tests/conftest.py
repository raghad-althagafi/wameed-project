import pytest
from FlaskMain import app
import auth_utils

@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True # turn test mode in flask

    def fake_verify_request_token(): # fake token
        return {
            "uid": "test_user_123",
            "email": "test@example.com"
        }, None

    monkeypatch.setattr(auth_utils, "verify_request_token", fake_verify_request_token)

    with app.test_client() as client: # client send request
        yield client