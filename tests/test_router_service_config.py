import importlib

from app import router_service


def test_master_url_default_does_not_collide_with_edge_02(monkeypatch):
    monkeypatch.delenv("MASTER_URL", raising=False)
    try:
        importlib.reload(router_service)
        assert router_service.MASTER_URL == "http://localhost:8003"
    finally:
        importlib.reload(router_service)


def test_master_url_respects_env_override(monkeypatch):
    monkeypatch.setenv("MASTER_URL", "http://master-test:9000")
    try:
        importlib.reload(router_service)
        assert router_service.MASTER_URL == "http://master-test:9000"
    finally:
        monkeypatch.delenv("MASTER_URL", raising=False)
        importlib.reload(router_service)
