import pytest

pytestmark = pytest.mark.e2e


class TestRootEndpoint:
    def test_root_returns_app_info(self, real_client):
        response = real_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SpeakNative API Gateway"
        assert "version" in data
        assert isinstance(data["supported_languages"], list)
        assert len(data["supported_languages"]) > 0
