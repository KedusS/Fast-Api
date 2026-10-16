from fastapi.testclient import TestClient
from datetime import timedelta
from ..main import LOG_FILE, app
from ..routers.auth import create_access_token
from fastapi import status

client = TestClient(app)


def test_return_health_check():
    response = client.get("/healthy")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'Healthy'}


def test_request_logging_includes_method_path_status_and_duration(caplog):
    with caplog.at_level("INFO", logger="TodoApp.main"):
        response = client.get("/healthy")

    assert response.status_code == status.HTTP_200_OK
    assert any(
        "Request completed method=GET path=/healthy status_code=200 duration_ms=" in record.message
        for record in caplog.records
    )
    assert LOG_FILE.exists()
    assert "Request completed method=GET path=/healthy status_code=200 duration_ms=" in LOG_FILE.read_text()


def test_home_page_is_music_app():
    response = client.get("/")

    assert response.status_code == status.HTTP_200_OK
    assert "Discover tracks" in response.text
    assert "Your playlists" in response.text
    assert "Todo" not in response.text
    assert "/static/css/base.css" in response.text
    assert "/static/js/music.js" in response.text


def test_frontend_assets_are_served():
    assert client.get("/static/css/base.css").status_code == status.HTTP_200_OK
    assert client.get("/static/js/music.js").status_code == status.HTTP_200_OK


def test_todo_routes_are_not_mounted():
    assert client.get("/todos/todo-page").status_code == status.HTTP_404_NOT_FOUND
    assert client.get("/admin/todo").status_code == status.HTTP_404_NOT_FOUND


def test_auth_pages_render():
    assert client.get("/auth/login-page").status_code == status.HTTP_200_OK
    assert client.get("/auth/register-page").status_code == status.HTTP_200_OK


def test_login_and_signup_links_only_render_when_logged_out():
    anonymous_response = client.get("/")
    assert 'id="nav-login"' in anonymous_response.text
    assert 'id="nav-register"' in anonymous_response.text
    assert 'id="nav-logout"' not in anonymous_response.text

    token = create_access_token("web-user", 1, "user", timedelta(minutes=5))
    authenticated_response = client.get("/", cookies={"access_token": token})
    assert 'id="nav-login"' not in authenticated_response.text
    assert 'id="nav-register"' not in authenticated_response.text
    assert 'id="nav-logout"' in authenticated_response.text
    assert 'id="passwordForm"' in authenticated_response.text


def test_password_form_is_hidden_when_logged_out():
    response = client.get("/")
    assert 'id="passwordForm"' not in response.text
    assert 'id="addTrackForm"' not in response.text


def test_catalog_form_only_shows_for_admin():
    admin_token = create_access_token("admin", 1, "admin", timedelta(minutes=5))
    admin_response = client.get("/", cookies={"access_token": admin_token})
    assert 'id="addTrackForm"' in admin_response.text

    user_token = create_access_token("user", 1, "user", timedelta(minutes=5))
    user_response = client.get("/", cookies={"access_token": user_token})
    assert 'id="addTrackForm"' not in user_response.text
