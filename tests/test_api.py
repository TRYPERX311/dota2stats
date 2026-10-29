import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

api_app = FastAPI()


@api_app.get("/logout")
def logout_handler():
    return RedirectResponse("/")


@pytest.fixture
def client():
    with TestClient(api_app) as c:
        yield c


def test_logout_returns_redirect(client):
    # Откл автоматическое следование редиректу
    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/"