from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = "sqlite:///./pharmaflow_test.db"
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base, engine, SessionLocal  # noqa: E402
import app.models  # noqa: E402,F401
from app.db.guards import install_guards  # noqa: E402
from app.main import app  # noqa: E402
from app.services.demo import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    db_file = Path("./pharmaflow_test.db")
    if db_file.exists():
        db_file.unlink()
    Base.metadata.create_all(bind=engine)
    install_guards(engine)
    yield


@pytest.fixture()
def db(_schema):
    s = SessionLocal()
    seed(s)
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(db):
    return TestClient(app)


def login(client: TestClient, email: str, password: str = "demo1234") -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def retailer_a(client):
    return login(client, "retailer.a@pharmaflow.demo")


@pytest.fixture()
def retailer_b(client):
    return login(client, "retailer.b@pharmaflow.demo")


@pytest.fixture()
def retailer_c(client):
    return login(client, "retailer.c@pharmaflow.demo")


@pytest.fixture()
def distributor(client):
    return login(client, "distributor@pharmaflow.demo")


@pytest.fixture()
def manufacturer(client):
    return login(client, "manufacturer@pharmaflow.demo")


@pytest.fixture()
def regulator(client):
    return login(client, "regulator@pharmaflow.demo")


@pytest.fixture()
def admin(client):
    return login(client, "admin@pharmaflow.demo")
