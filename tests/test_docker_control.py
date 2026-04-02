import json

import pytest

from ops import docker_control


class _Resp:
    def __init__(self, status: int, payload: str):
        self.status = status
        self._payload = payload.encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_control_service_rejects_invalid_action():
    with pytest.raises(docker_control.DockerControlError):
        docker_control.control_service("rm")


def test_get_service_status_running(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://proxy:2375")
    monkeypatch.setenv("DOCKER_TARGET_SERVICE", "bot")

    def fake_open(req, timeout=0):  # noqa: ARG001
        url = req.full_url
        if "/containers/json?" in url:
            return _Resp(200, json.dumps([{"Id": "abc123"}]))
        if "/containers/abc123/json" in url:
            return _Resp(200, json.dumps({"State": {"Running": True}}))
        raise AssertionError(url)

    monkeypatch.setattr(docker_control, "urlopen", fake_open)
    st = docker_control.get_service_status()
    assert st["state"] == "running"
    assert st["container_id"] == "abc123"


def test_find_container_falls_back_when_compose_project_wrong(monkeypatch):
    """Неверный COMPOSE_PROJECT_NAME: сначала пустой список, затем поиск только по сервису."""
    monkeypatch.setenv("DOCKER_HOST", "tcp://proxy:2375")
    monkeypatch.setenv("DOCKER_TARGET_SERVICE", "bot")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "wrong_project")

    def fake_open(req, timeout=0):  # noqa: ARG001
        url = req.full_url
        if "/containers/json?" in url:
            if "wrong_project" in url:
                return _Resp(200, json.dumps([]))
            return _Resp(200, json.dumps([{"Id": "fallback-id"}]))
        if "/containers/fallback-id/stop" in url:
            return _Resp(204, "")
        raise AssertionError(url)

    monkeypatch.setattr(docker_control, "urlopen", fake_open)
    out = docker_control.control_service("stop")
    assert out["container_id"] == "fallback-id"
    assert out["action"] == "stop"


def test_control_service_not_found_message(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://proxy:2375")
    monkeypatch.setenv("DOCKER_TARGET_SERVICE", "bot")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "p")

    def fake_open(req, timeout=0):  # noqa: ARG001
        if "/containers/json?" in req.full_url:
            return _Resp(200, json.dumps([]))
        raise AssertionError(req.full_url)

    monkeypatch.setattr(docker_control, "urlopen", fake_open)
    with pytest.raises(docker_control.DockerControlError) as ei:
        docker_control.control_service("stop")
    assert "DOCKER_TARGET_SERVICE" in str(ei.value)
    assert "COMPOSE_PROJECT_NAME" in str(ei.value)
