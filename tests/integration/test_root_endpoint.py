from importlib.metadata import version as get_version


class TestRootEndpoint:
    def test_root_returns_info(self, client):
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SpeakNative API Gateway"
        assert data["version"] == get_version("sn-api-gateway")
        assert "supported_languages" in data
        assert isinstance(data["supported_languages"], list)

    def test_root_includes_supported_languages(self, client):
        response = client.get("/")

        data = response.json()
        assert "en" in data["supported_languages"]
        assert "es" in data["supported_languages"]
