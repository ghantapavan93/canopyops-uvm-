"""Pytest fixtures. Tests run against the Dockerized PostGIS on host 5433 and
reseed synthetic data before each test for isolation."""
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://canopyops:canopyops@localhost:5433/canopyops",
)

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed


@pytest.fixture(autouse=True)
def _reseed():
    """Fresh synthetic data per test."""
    seed()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def token(client: TestClient, email: str) -> str:
    res = client.post(
        "/api/auth/token", data={"username": email, "password": "canopyops"}
    )
    assert res.status_code == 200, res.text
    return res.json()["accessToken"]


def auth(client: TestClient, email: str) -> dict:
    return {"Authorization": f"Bearer {token(client, email)}"}


def inner_polygon(geometry: dict, scale: float = 0.6) -> dict:
    ring = geometry["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w = (max(xs) - min(xs)) / 2 * scale
    h = (max(ys) - min(ys)) / 2 * scale
    return {
        "type": "Polygon",
        "coordinates": [[[cx - w, cy - h], [cx + w, cy - h], [cx + w, cy + h], [cx - w, cy + h], [cx - w, cy - h]]],
    }
