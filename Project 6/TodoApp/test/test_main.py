from fastapi.testclient import TestClient
from datetime import timedelta
from ..main import app
from ..routers.auth import create_access_token
from fastapi import status

client = TestClient(app)


def test_return_health_check():
    response = client.get("/healthy")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'Healthy'}


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
