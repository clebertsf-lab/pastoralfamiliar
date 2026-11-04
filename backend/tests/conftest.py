"""Pre-scaffolded pytest fixtures for the FastAPI backend.

Tests hit the live uvicorn process managed by supervisor (not an in-process ASGI app), so
the app under test is the same one the frontend and Playwright see. Do NOT re-create this
file — add app-specific fixtures below the marker at the bottom.
"""

import os

import httpx
import pytest
import pytest_asyncio

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
API_URL = f"{BACKEND_URL}/api"


def api_url(path: str = "") -> str:
    """Absolute URL for an /api route: api_url("/status") -> http://localhost:8001/api/status."""
    return f"{API_URL}{path}"


@pytest.fixture(scope="session")
def backend_url() -> str:
    return BACKEND_URL


@pytest.fixture
def client():
    """Sync httpx client rooted at /api — the default for endpoint tests.

    Example:
        def test_status(client):
            assert client.get("/status").status_code == 200
    """
    with httpx.Client(base_url=API_URL, timeout=30.0) as c:
        yield c


@pytest_asyncio.fixture
async def aclient():
    """Async variant, for tests that also await motor/backend helpers directly."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as c:
        yield c


# --- app-specific fixtures below this line ---

COOKIE_NAME = "pastoral_session"


def login(client: httpx.Client, username: str, password: str) -> None:
    """Log in and pin the session cookie onto `client` for subsequent requests.

    The backend sets the session cookie with `Secure` (correct for the real HTTPS
    ingress). httpx's stdlib-backed cookie jar refuses to replay a `Secure` cookie over
    the plain `http://localhost:8001` connection this suite talks to, so we copy the
    token into a manual `Cookie` header instead of relying on the jar.
    """
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.cookies.get(COOKIE_NAME)
    assert token, "login did not set a session cookie"
    client.headers["Cookie"] = f"{COOKIE_NAME}={token}"
