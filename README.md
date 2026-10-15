"# Fastapi-The-Complete-Course"

Course and code created by: Eric Roby

## Playlist variant API

The Todo app also includes a self-contained music playlist API under `/music`.
It uses a small local catalog of fictional tracks and does not call Spotify or
any other external music service. The sample catalog is seeded when the app
starts and is available at `GET /music/tracks`.

Use the existing registration and login endpoints (`POST /auth/` and
`POST /auth/token`) to get a bearer token. Then use that token to create and
manage your own playlists:

- `POST /music/playlists` creates a source playlist from catalog track IDs.
- `GET /music/playlists` lists the signed-in user's playlists.
- `GET /music/playlists/{playlist_id}` returns one of their playlists.
- `POST /music/playlists/{playlist_id}/variants/preview` previews clean or
  explicit alternatives without saving a playlist.
- `POST /music/playlists/{playlist_id}/variants` creates a new playlist with
  the requested versions. It fails with `422` if any track has no matching
  version, instead of silently dropping that track.

Open `/docs` while the app is running to try the endpoints interactively.
