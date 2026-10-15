from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import PlaylistTracks, Playlists, Tracks
from .auth import get_current_user

router = APIRouter(prefix="/music", tags=["music"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]


class TrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    explicit: bool


class PlaylistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    track_ids: list[int] = Field(min_length=1)


class VariantPreviewRequest(BaseModel):
    target_explicit: bool


class VariantCreateRequest(VariantPreviewRequest):
    name: str = Field(min_length=1, max_length=100)


class PlaylistResponse(BaseModel):
    id: int
    name: str
    source_playlist_id: int | None
    target_explicit: bool | None
    tracks: list[TrackResponse]


class VariantTrackPreview(BaseModel):
    source: TrackResponse
    target: TrackResponse | None


class VariantPreviewResponse(BaseModel):
    source_playlist_id: int
    target_explicit: bool
    tracks: list[VariantTrackPreview]
    unresolved_track_ids: list[int]


def _get_owned_playlist(db: Session, playlist_id: int, owner_id: int) -> Playlists:
    """Look up a playlist only within its owner's records."""
    playlist = (
        db.query(Playlists)
        .filter(Playlists.id == playlist_id, Playlists.owner_id == owner_id)
        .first()
    )
    if playlist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found.")
    return playlist


def _get_playlist_tracks(db: Session, playlist_id: int) -> list[Tracks]:
    return (
        db.query(Tracks)
        .join(PlaylistTracks, PlaylistTracks.track_id == Tracks.id)
        .filter(PlaylistTracks.playlist_id == playlist_id)
        .order_by(PlaylistTracks.position)
        .all()
    )


def _playlist_response(db: Session, playlist: Playlists) -> PlaylistResponse:
    return PlaylistResponse(
        id=playlist.id,
        name=playlist.name,
        source_playlist_id=playlist.source_playlist_id,
        target_explicit=playlist.target_explicit,
        tracks=[TrackResponse.model_validate(track) for track in _get_playlist_tracks(db, playlist.id)],
    )


def _build_variant_preview(
    db: Session, playlist: Playlists, target_explicit: bool
) -> VariantPreviewResponse:
    """Match each song to the requested version and collect missing matches."""
    preview_tracks = []
    unresolved_track_ids = []

    for source_track in _get_playlist_tracks(db, playlist.id):
        target_track = source_track
        if source_track.explicit != target_explicit:
            target_track = (
                db.query(Tracks)
                .filter(
                    Tracks.version_group == source_track.version_group,
                    Tracks.explicit == target_explicit,
                )
                .first()
            )
        if target_track is None:
            unresolved_track_ids.append(source_track.id)
        preview_tracks.append(
            VariantTrackPreview(
                source=TrackResponse.model_validate(source_track),
                target=TrackResponse.model_validate(target_track) if target_track else None,
            )
        )

    return VariantPreviewResponse(
        source_playlist_id=playlist.id,
        target_explicit=target_explicit,
        tracks=preview_tracks,
        unresolved_track_ids=unresolved_track_ids,
    )


@router.get("/tracks", response_model=list[TrackResponse])
async def list_tracks(db: db_dependency):
    return db.query(Tracks).order_by(Tracks.artist, Tracks.title, Tracks.explicit).all()


@router.post("/playlists", response_model=PlaylistResponse, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    user: user_dependency,
    db: db_dependency,
    playlist_request: PlaylistCreateRequest,
):
    # Reject unknown song IDs before saving the playlist or its track links.
    track_ids = set(playlist_request.track_ids)
    tracks_by_id = {
        track.id: track
        for track in db.query(Tracks).filter(Tracks.id.in_(track_ids)).all()
    }
    missing_track_ids = sorted(track_ids - tracks_by_id.keys())
    if missing_track_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Some tracks do not exist.", "track_ids": missing_track_ids},
        )

    playlist = Playlists(name=playlist_request.name, owner_id=user["id"])
    db.add(playlist)
    db.flush()
    db.add_all(
        PlaylistTracks(playlist_id=playlist.id, track_id=track_id, position=position)
        for position, track_id in enumerate(playlist_request.track_ids)
    )
    db.commit()
    db.refresh(playlist)
    return _playlist_response(db, playlist)


@router.get("/playlists", response_model=list[PlaylistResponse])
async def list_playlists(user: user_dependency, db: db_dependency):
    playlists = (
        db.query(Playlists)
        .filter(Playlists.owner_id == user["id"])
        .order_by(Playlists.id)
        .all()
    )
    return [_playlist_response(db, playlist) for playlist in playlists]


@router.put("/playlists/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    user: user_dependency,
    db: db_dependency,
    playlist_request: PlaylistCreateRequest,
    playlist_id: int = Path(gt=0),
):
    # Validate the replacement list first so an invalid edit leaves the playlist unchanged.
    playlist = _get_owned_playlist(db, playlist_id, user["id"])
    track_ids = set(playlist_request.track_ids)
    tracks_by_id = {
        track.id: track
        for track in db.query(Tracks).filter(Tracks.id.in_(track_ids)).all()
    }
    missing_track_ids = sorted(track_ids - tracks_by_id.keys())
    if missing_track_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Some tracks do not exist.", "track_ids": missing_track_ids},
        )

    playlist.name = playlist_request.name
    db.query(PlaylistTracks).filter(PlaylistTracks.playlist_id == playlist.id).delete(
        synchronize_session=False
    )
    db.add_all(
        PlaylistTracks(playlist_id=playlist.id, track_id=track_id, position=position)
        for position, track_id in enumerate(playlist_request.track_ids)
    )
    db.commit()
    db.refresh(playlist)
    return _playlist_response(db, playlist)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    user: user_dependency,
    db: db_dependency,
    playlist_id: int = Path(gt=0),
):
    playlist = _get_owned_playlist(db, playlist_id, user["id"])
    # Remove song links and detach derived versions before deleting the source.
    db.query(PlaylistTracks).filter(PlaylistTracks.playlist_id == playlist.id).delete(
        synchronize_session=False
    )
    db.query(Playlists).filter(Playlists.source_playlist_id == playlist.id).update(
        {Playlists.source_playlist_id: None},
        synchronize_session=False,
    )
    db.delete(playlist)
    db.commit()


@router.get("/playlists/{playlist_id}", response_model=PlaylistResponse)
async def read_playlist(
    user: user_dependency,
    db: db_dependency,
    playlist_id: int = Path(gt=0),
):
    playlist = _get_owned_playlist(db, playlist_id, user["id"])
    return _playlist_response(db, playlist)


@router.post(
    "/playlists/{playlist_id}/variants/preview",
    response_model=VariantPreviewResponse,
)
async def preview_playlist_variant(
    user: user_dependency,
    db: db_dependency,
    variant_request: VariantPreviewRequest,
    playlist_id: int = Path(gt=0),
):
    playlist = _get_owned_playlist(db, playlist_id, user["id"])
    return _build_variant_preview(db, playlist, variant_request.target_explicit)


@router.post(
    "/playlists/{playlist_id}/variants",
    response_model=PlaylistResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_playlist_variant(
    user: user_dependency,
    db: db_dependency,
    variant_request: VariantCreateRequest,
    playlist_id: int = Path(gt=0),
):
    source_playlist = _get_owned_playlist(db, playlist_id, user["id"])
    # Do not create a partial variant when any song lacks the requested version.
    preview = _build_variant_preview(db, source_playlist, variant_request.target_explicit)
    if preview.unresolved_track_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "A variant is unavailable for one or more tracks.",
                "track_ids": preview.unresolved_track_ids,
            },
        )

    playlist = Playlists(
        name=variant_request.name,
        owner_id=user["id"],
        source_playlist_id=source_playlist.id,
        target_explicit=variant_request.target_explicit,
    )
    db.add(playlist)
    db.flush()
    db.add_all(
        PlaylistTracks(playlist_id=playlist.id, track_id=track.target.id, position=position)
        for position, track in enumerate(preview.tracks)
        if track.target is not None
    )
    db.commit()
    db.refresh(playlist)
    return _playlist_response(db, playlist)
