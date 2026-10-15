# Juicebox music app

Juicebox is a FastAPI music catalog and playlist app. Its local training catalog
uses Juice WRLD song titles and supports clean/explicit playlist versions. It
stores metadata only; it does not provide audio playback or call an external
music service.

## Run the app

From the `Project 6` directory, start the development server:

```sh
uvicorn TodoApp.main:app --reload
```

Open the app at `http://127.0.0.1:8000`. Browse the catalog without signing in;
create an account and log in to save playlists.

## Playlist API

The catalog is also available at `GET /music/tracks`. Register and log in via
`POST /auth/` and `POST /auth/token` to get a bearer token, then use it to
create and manage playlists:

- `POST /music/playlists` creates a source playlist from catalog track IDs.
- `GET /music/playlists` lists the signed-in user's playlists.
- `GET /music/playlists/{playlist_id}` returns one of their playlists.
- `POST /music/playlists/{playlist_id}/variants/preview` previews clean or
  explicit alternatives without saving a playlist.
- `POST /music/playlists/{playlist_id}/variants` creates a new playlist with
  the requested versions. It fails with `422` if any track has no matching
  version, instead of silently dropping that track.

Open `/docs` while the app is running to try the endpoints interactively.
