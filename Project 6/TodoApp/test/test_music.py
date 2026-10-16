from fastapi import status
import pytest
from sqlalchemy import text

from ..models import PlaylistTracks, Playlists, Tracks
from ..routers.auth import get_current_user
from ..routers.music import get_db
from .utils import TestingSessionLocal, app, client, engine, override_get_current_user, override_get_db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user


@pytest.fixture
def music_catalog():
    db = TestingSessionLocal()
    db.query(PlaylistTracks).delete()
    db.query(Playlists).delete()
    db.query(Tracks).delete()
    tracks = [
        Tracks(title="Midnight Drive", artist="Nova Lane", explicit=True, version_group="midnight-drive"),
        Tracks(title="Midnight Drive (Clean)", artist="Nova Lane", explicit=False, version_group="midnight-drive"),
        Tracks(title="Paper Moons", artist="The Skylines", explicit=False, version_group="paper-moons"),
        Tracks(title="Golden Hour", artist="Mira Sol", explicit=False, version_group="golden-hour"),
    ]
    db.add_all(tracks)
    db.commit()
    for track in tracks:
        db.refresh(track)
    ids = {
        (track.version_group, track.explicit): track.id
        for track in tracks
    }
    db.close()
    yield ids
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM playlist_tracks;"))
        connection.execute(text("DELETE FROM playlists;"))
        connection.execute(text("DELETE FROM tracks;"))
        connection.commit()


def test_list_local_catalog(music_catalog):
    response = client.get("/music/tracks")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 4
    assert {track["explicit"] for track in response.json()} == {True, False}


def test_list_catalog_when_empty(music_catalog):
    db = TestingSessionLocal()
    db.query(Tracks).delete()
    db.commit()
    db.close()

    response = client.get("/music/tracks")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_admin_can_add_catalog_track(music_catalog):
    response = client.post(
        "/music/tracks",
        json={
            "title": "New Song",
            "artist": "New Artist",
            "explicit": True,
            "version_group": "new-song",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["title"] == "New Song"
    assert any(track["id"] == response.json()["id"] for track in client.get("/music/tracks").json())


def test_regular_user_cannot_add_catalog_track(music_catalog):
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "regular-user",
        "id": 1,
        "user_role": "user",
    }
    try:
        response = client.post(
            "/music/tracks",
            json={
                "title": "Unauthorized Song",
                "artist": "Someone",
                "explicit": False,
                "version_group": "unauthorized-song",
            },
        )
    finally:
        app.dependency_overrides[get_current_user] = override_get_current_user

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_cannot_add_duplicate_track_version(music_catalog):
    request_data = {
        "title": "New Song",
        "artist": "New Artist",
        "explicit": True,
        "version_group": "new-song",
    }

    first_response = client.post("/music/tracks", json=request_data)
    duplicate_response = client.post("/music/tracks", json=request_data)

    assert first_response.status_code == status.HTTP_201_CREATED
    assert duplicate_response.status_code == status.HTTP_409_CONFLICT


def test_preview_and_create_clean_playlist_variant(music_catalog):
    source_response = client.post(
        "/music/playlists",
        json={
            "name": "Road trip",
            "track_ids": [
                music_catalog[("midnight-drive", True)],
                music_catalog[("paper-moons", False)],
            ],
        },
    )
    assert source_response.status_code == status.HTTP_201_CREATED
    source_playlist = source_response.json()

    preview_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants/preview",
        json={"target_explicit": False},
    )
    assert preview_response.status_code == status.HTTP_200_OK
    preview = preview_response.json()
    assert preview["unresolved_track_ids"] == []
    assert [track["target"]["id"] for track in preview["tracks"]] == [
        music_catalog[("midnight-drive", False)],
        music_catalog[("paper-moons", False)],
    ]

    variant_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants",
        json={"name": "Road trip clean", "target_explicit": False},
    )
    assert variant_response.status_code == status.HTTP_201_CREATED
    variant = variant_response.json()
    assert variant["source_playlist_id"] == source_playlist["id"]
    assert variant["target_explicit"] is False
    assert [track["explicit"] for track in variant["tracks"]] == [False, False]
    listed_playlists = client.get("/music/playlists").json()
    assert [playlist["id"] for playlist in listed_playlists] == [
        source_playlist["id"],
        variant["id"],
    ]


def test_update_playlist_changes_name_and_track_order(music_catalog):
    create_response = client.post(
        "/music/playlists",
        json={
            "name": "Road trip",
            "track_ids": [
                music_catalog[("midnight-drive", True)],
                music_catalog[("paper-moons", False)],
            ],
        },
    )
    playlist_id = create_response.json()["id"]

    response = client.put(
        f"/music/playlists/{playlist_id}",
        json={
            "name": "Quiet drive",
            "track_ids": [music_catalog[("paper-moons", False)]],
        },
    )

    assert response.status_code == status.HTTP_200_OK
    updated = response.json()
    assert updated["name"] == "Quiet drive"
    assert [track["id"] for track in updated["tracks"]] == [
        music_catalog[("paper-moons", False)]
    ]


def test_cannot_update_another_users_playlist(music_catalog):
    create_response = client.post(
        "/music/playlists",
        json={
            "name": "Private playlist",
            "track_ids": [music_catalog[("paper-moons", False)]],
        },
    )
    playlist_id = create_response.json()["id"]
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "another-user",
        "id": 999,
        "user_role": "user",
    }
    try:
        response = client.put(
            f"/music/playlists/{playlist_id}",
            json={
                "name": "Stolen playlist",
                "track_ids": [music_catalog[("paper-moons", False)]],
            },
        )
    finally:
        app.dependency_overrides[get_current_user] = override_get_current_user

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_partial_variant_is_created_and_reports_tracks_without_matches(music_catalog):
    source_response = client.post(
        "/music/playlists",
        json={
            "name": "Quiet afternoon",
            "track_ids": [
                music_catalog[("midnight-drive", True)],
                music_catalog[("golden-hour", False)],
            ],
        },
    )
    source_playlist = source_response.json()

    preview_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants/preview",
        json={"target_explicit": True},
    )
    assert preview_response.status_code == status.HTTP_200_OK
    assert preview_response.json()["unresolved_track_ids"] == [music_catalog[("golden-hour", False)]]

    variant_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants",
        json={"name": "Explicit afternoon", "target_explicit": True},
    )
    assert variant_response.status_code == status.HTTP_201_CREATED
    variant = variant_response.json()
    assert [track["id"] for track in variant["tracks"]] == [
        music_catalog[("midnight-drive", True)]
    ]
    assert variant["unconverted_tracks"] == [
        {
            "id": music_catalog[("golden-hour", False)],
            "title": "Golden Hour",
            "artist": "Mira Sol",
            "explicit": False,
        }
    ]
    assert len(client.get("/music/playlists").json()) == 2


def test_cannot_create_empty_playlist_or_variant(music_catalog):
    empty_playlist_response = client.post(
        "/music/playlists",
        json={"name": "Empty playlist", "track_ids": []},
    )
    assert empty_playlist_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    source_response = client.post(
        "/music/playlists",
        json={
            "name": "Quiet afternoon",
            "track_ids": [music_catalog[("golden-hour", False)]],
        },
    )
    source_playlist = source_response.json()
    variant_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants",
        json={"name": "Explicit afternoon", "target_explicit": True},
    )

    assert variant_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Golden Hour" in variant_response.json()["detail"]
    assert "Mira Sol" in variant_response.json()["detail"]
    assert len(client.get("/music/playlists").json()) == 1


def test_delete_playlist_keeps_variants_and_removes_playlist_tracks(music_catalog):
    source_response = client.post(
        "/music/playlists",
        json={
            "name": "Road trip",
            "track_ids": [music_catalog[("midnight-drive", True)]],
        },
    )
    source_id = source_response.json()["id"]
    variant_response = client.post(
        f"/music/playlists/{source_id}/variants",
        json={"name": "Road trip clean", "target_explicit": False},
    )
    variant_id = variant_response.json()["id"]

    response = client.delete(f"/music/playlists/{source_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    remaining = client.get("/music/playlists").json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == variant_id
    assert remaining[0]["source_playlist_id"] is None
    assert client.get(f"/music/playlists/{source_id}").status_code == status.HTTP_404_NOT_FOUND


def test_playlist_is_not_visible_to_another_user(music_catalog):
    source_response = client.post(
        "/music/playlists",
        json={
            "name": "Private playlist",
            "track_ids": [music_catalog[("paper-moons", False)]],
        },
    )
    playlist_id = source_response.json()["id"]
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "another-user",
        "id": 999,
        "user_role": "user",
    }
    try:
        response = client.get(f"/music/playlists/{playlist_id}")
        delete_response = client.delete(f"/music/playlists/{playlist_id}")
    finally:
        app.dependency_overrides[get_current_user] = override_get_current_user

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND
