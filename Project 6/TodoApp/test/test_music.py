from fastapi import status
import pytest
from sqlalchemy import text

from ..models import PlaylistTracks, Playlists, Tracks
from ..routers.auth import get_current_user
from ..routers.music import get_db
from ..seed import SAMPLE_TRACKS
from .utils import TestingSessionLocal, app, client, engine, override_get_current_user, override_get_db

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user


def test_seed_catalog_uses_juice_wrld_song_titles():
    assert {track["artist"] for track in SAMPLE_TRACKS} == {"Juice WRLD"}
    assert {track["title"] for track in SAMPLE_TRACKS} == {
        "Lucid Dreams",
        "All Girls Are the Same",
        "Robbery",
        "Wishing Well",
        "Righteous",
    }
    versions_by_group = {}
    for track in SAMPLE_TRACKS:
        versions_by_group.setdefault(track["version_group"], set()).add(track["explicit"])
    assert all(versions == {True, False} for versions in versions_by_group.values())


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
    assert client.get("/music/playlists").json() == [source_playlist, variant]


def test_missing_variant_is_reported_and_not_created(music_catalog):
    source_response = client.post(
        "/music/playlists",
        json={
            "name": "Quiet afternoon",
            "track_ids": [music_catalog[("golden-hour", False)]],
        },
    )
    source_playlist = source_response.json()

    preview_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants/preview",
        json={"target_explicit": True},
    )
    assert preview_response.status_code == status.HTTP_200_OK
    assert preview_response.json()["unresolved_track_ids"] == [
        music_catalog[("golden-hour", False)]
    ]

    variant_response = client.post(
        f"/music/playlists/{source_playlist['id']}/variants",
        json={"name": "Explicit afternoon", "target_explicit": True},
    )
    assert variant_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert len(client.get("/music/playlists").json()) == 1


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
    finally:
        app.dependency_overrides[get_current_user] = override_get_current_user

    assert response.status_code == status.HTTP_404_NOT_FOUND
