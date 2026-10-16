# Juicebox music app

Juicebox is a FastAPI music catalog and playlist app. The catalog starts empty;
an administrator can add tracks and pair clean/explicit versions. It stores
metadata only; it does not provide audio playback or call an external music
service.

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
  available requested versions and reports tracks that could not be converted.
  It fails with `422` if no tracks can be converted.

Open `/docs` while the app is running to try the endpoints interactively.

## Basic logging

The app writes request method, path, response status, and duration to the
development server's console and to `Project 6/TodoApp/logs/juicebox.log`.
The log file rotates after 1 MB and keeps up to three older files. It also logs
key account and playlist actions.
Passwords, tokens, and request bodies are not included. The `/healthy` endpoint
provides a basic application health check; this project does not include metrics,
distributed tracing, or a persistent audit history.
