import pytest


@pytest.mark.db
class TestHealthEndpoint:
    def test_health_ready_returns_up(self, real_client):
        response = real_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}
