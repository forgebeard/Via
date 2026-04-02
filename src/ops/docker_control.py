from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class DockerControlError(RuntimeError):
    pass


def _docker_base_url() -> str:
    host = (os.getenv("DOCKER_HOST") or "").strip()
    if host.startswith("tcp://"):
        return "http://" + host.removeprefix("tcp://")
    if host.startswith("http://") or host.startswith("https://"):
        return host
    raise DockerControlError("DOCKER_HOST не настроен для runtime-control")


def _service_name() -> str:
    name = (os.getenv("DOCKER_TARGET_SERVICE") or "").strip()
    return name or "bot"


def _project_name() -> str | None:
    v = (os.getenv("COMPOSE_PROJECT_NAME") or os.getenv("DOCKER_COMPOSE_PROJECT") or "").strip()
    return v if v else None


def _docker_request(method: str, path: str) -> tuple[int, Any]:
    base = _docker_base_url().rstrip("/")
    # Пустое тело + явный Content-Length: часть прокси/urllib некорректно обрабатывает POST без data
    data: bytes | None = b"" if method == "POST" else None
    req = Request(f"{base}{path}", data=data, method=method)
    try:
        with urlopen(req, timeout=5.0) as r:
            payload = r.read().decode("utf-8", errors="replace")
            if not payload:
                return r.status, None
            try:
                return r.status, json.loads(payload)
            except json.JSONDecodeError:
                return r.status, payload
    except HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        raise DockerControlError(f"Docker API HTTP {e.code}: {text}") from e
    except URLError as e:
        raise DockerControlError(f"Docker API недоступен: {e}") from e


def _containers_with_labels(service: str, compose_project: str | None) -> list[dict[str, Any]]:
    labels = [f"com.docker.compose.service={service}"]
    if compose_project:
        labels.append(f"com.docker.compose.project={compose_project}")
    filters = {"label": labels}
    query = urlencode({"all": "1", "filters": json.dumps(filters)})
    _, payload = _docker_request("GET", f"/containers/json?{query}")
    return payload if isinstance(payload, list) else []


def _find_target_container_id() -> str | None:
    """
    Ищем контейнер по меткам compose.

    Если задан COMPOSE_PROJECT_NAME и он не совпадает с реальной меткой проекта у контейнеров,
    список будет пустой — тогда повторяем поиск только по имени сервиса (типичный сбой UI Stop/Start).
    """
    service = _service_name()
    project = _project_name()
    if project:
        rows = _containers_with_labels(service, project)
        if rows:
            return rows[0].get("Id")
    rows = _containers_with_labels(service, None)
    if rows:
        return rows[0].get("Id")
    return None


def get_service_status() -> dict[str, Any]:
    cid = _find_target_container_id()
    if not cid:
        return {"service": _service_name(), "state": "not_found"}
    _, payload = _docker_request("GET", f"/containers/{cid}/json")
    state = "unknown"
    running = False
    if isinstance(payload, dict):
        st = payload.get("State") or {}
        running = bool(st.get("Running"))
        state = "running" if running else "stopped"
    return {"service": _service_name(), "state": state, "running": running, "container_id": cid}


def control_service(action: str) -> dict[str, Any]:
    allowed = {"start", "stop", "restart"}
    if action not in allowed:
        raise DockerControlError("Недопустимая операция")
    cid = _find_target_container_id()
    if not cid:
        hint = (
            f"не найден контейнер с com.docker.compose.service={_service_name()}"
            + (f" и project={_project_name()!r}" if _project_name() else "")
            + ". Проверьте DOCKER_TARGET_SERVICE; при необходимости уберите или исправьте COMPOSE_PROJECT_NAME в .env"
        )
        raise DockerControlError(hint)
    _docker_request("POST", f"/containers/{cid}/{action}")
    return {"service": _service_name(), "action": action, "container_id": cid}
