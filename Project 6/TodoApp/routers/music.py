import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import PlaylistTracks, Playlists, Tracks
from .auth import get_current_user

router = APIRouter(prefix="/music", tags=["music"])
logger = logging.getLogger(__name__)


# Open a database session for a request and close it when the request finishes.
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


class TrackCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)
    explicit: bool
    version_group: str = Field(min_length=1, max_length=100)


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


class PlaylistVariantResponse(PlaylistResponse):
    unconverted_tracks: list[TrackResponse]


class VariantTrackPreview(BaseModel):
    source: TrackResponse
    target: TrackResponse | None


class VariantPreviewResponse(BaseModel):
    source_playlist_id: int
    target_explicit: bool
    tracks: list[VariantTrackPreview]
    unresolved_track_ids: list[int]


# Find a playlist only when it belongs to the requesting user.
def _get_owned_playlist(db: Session, playlist_id: int, owner_id: int) -> Playlists:
    playlist = (
        db.query(Playlists)
        .filter(Playlists.id == playlist_id, Playlists.owner_id == owner_id)
        .first()
    )
    if playlist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found.")
    return playlist


# Stop non-admin users from changing the shared music catalog.
def _require_admin(user: dict) -> None:
    if user.get("user_role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can add catalog tracks.",
        )


# Load a playlist's tracks in the order chosen by its owner.
def _get_playlist_tracks(db: Session, playlist_id: int) -> list[Tracks]:
    return (
        db.query(Tracks)
        .join(PlaylistTracks, PlaylistTracks.track_id == Tracks.id)
        .filter(PlaylistTracks.playlist_id == playlist_id)
        .order_by(PlaylistTracks.position)
        .all()
    )


# Build the API response for a playlist, including its ordered track details.
def _playlist_response(db: Session, playlist: Playlists) -> PlaylistResponse:
    return PlaylistResponse(
        id=playlist.id,
        name=playlist.name,
        source_playlist_id=playlist.source_playlist_id,
        target_explicit=playlist.target_explicit,
        tracks=[TrackResponse.model_validate(track) for track in _get_playlist_tracks(db, playlist.id)],
    )


# Match playlist tracks to the requested clean/explicit versions and report missing matches.
def _build_variant_preview(
    db: Session, playlist: Playlists, target_explicit: bool
) -> VariantPreviewResponse:
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


# List catalog tracks in a predictable artist-and-title order.
@router.get("/tracks", response_model=list[TrackResponse])
async def list_tracks(db: db_dependency):
    return db.query(Tracks).order_by(Tracks.artist, Tracks.title, Tracks.explicit).all()


# Add a clean or explicit track to the catalog; only admins may do this.
@router.post("/tracks", response_model=TrackResponse, status_code=status.HTTP_201_CREATED)
async def add_track(
    user: user_dependency,
    db: db_dependency,
    track_request: TrackCreateRequest,
):
    _require_admin(user)
    track = Tracks(**track_request.model_dump())
    db.add(track)
    try:
        db.commit()
    except IntegrityError as error:
        # The database uniqueness rule prevents duplicate clean/explicit entries per song.
        db.rollback()
        logger.warning("Duplicate track version rejected user_id=%s", user["id"])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A track with this version group and clean/explicit status already exists.",
        ) from error
    db.refresh(track)
    logger.info("Catalog track added user_id=%s track_id=%s", user["id"], track.id)
    return track


# Save a new playlist and its tracks in the order submitted by the user.
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
    # Keep the submitted order by storing each track's position in the playlist.
    db.add_all(
        PlaylistTracks(playlist_id=playlist.id, track_id=track_id, position=position)
        for position, track_id in enumerate(playlist_request.track_ids)
    )
    db.commit()
    db.refresh(playlist)
    logger.info(
        "Playlist created user_id=%s playlist_id=%s track_count=%s",
        user["id"],
        playlist.id,
        len(playlist_request.track_ids),
    )
    return _playlist_response(db, playlist)


# List only the playlists owned by the currently signed-in user.
@router.get("/playlists", response_model=list[PlaylistResponse])
async def list_playlists(user: user_dependency, db: db_dependency):
    playlists = (
        db.query(Playlists)
        .filter(Playlists.owner_id == user["id"])
        .order_by(Playlists.id)
        .all()
    )
    return [_playlist_response(db, playlist) for playlist in playlists]


# Replace a playlist's name and track order after validating its new track list.
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
    # Rebuild ordered links only after every requested track has been validated.
    db.query(PlaylistTracks).filter(PlaylistTracks.playlist_id == playlist.id).delete(
        synchronize_session=False
    )
    db.add_all(
        PlaylistTracks(playlist_id=playlist.id, track_id=track_id, position=position)
        for position, track_id in enumerate(playlist_request.track_ids)
    )
    db.commit()
    db.refresh(playlist)
    logger.info(
        "Playlist updated user_id=%s playlist_id=%s track_count=%s",
        user["id"],
        playlist.id,
        len(playlist_request.track_ids),
    )
    return _playlist_response(db, playlist)


# Delete a playlist and its track links while keeping any derived playlists valid.
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
    logger.info("Playlist deleted user_id=%s playlist_id=%s", user["id"], playlist_id)


# Return one playlist only if it belongs to the currently signed-in user.
@router.get("/playlists/{playlist_id}", response_model=PlaylistResponse)
async def read_playlist(
    user: user_dependency,
    db: db_dependency,
    playlist_id: int = Path(gt=0),
):
    playlist = _get_owned_playlist(db, playlist_id, user["id"])
    return _playlist_response(db, playlist)


# Show matching clean/explicit tracks without saving a new playlist.
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


# Save a clean/explicit copy and report tracks that lack a matching version.
@router.post(
    "/playlists/{playlist_id}/variants",
    response_model=PlaylistVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_playlist_variant(
    user: user_dependency,
    db: db_dependency,
    variant_request: VariantCreateRequest,
    playlist_id: int = Path(gt=0),
):
    source_playlist = _get_owned_playlist(db, playlist_id, user["id"])
    preview = _build_variant_preview(db, source_playlist, variant_request.target_explicit)
    converted_tracks = [track.target for track in preview.tracks if track.target is not None]
    unconverted_tracks = [track.source for track in preview.tracks if track.target is None]
    if not converted_tracks:
        if unconverted_tracks:
            missing_names = ", ".join(
                f"{track.title} · {track.artist}" for track in unconverted_tracks
            )
            detail = f"No tracks were converted, so the playlist was not created. Missing versions: {missing_names}."
        else:
            detail = "This playlist has no tracks, so a version could not be created."
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
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
        PlaylistTracks(playlist_id=playlist.id, track_id=track.id, position=position)
        for position, track in enumerate(converted_tracks)
    )
    db.commit()
    db.refresh(playlist)
    logger.info(
        "Playlist variant created user_id=%s playlist_id=%s source_playlist_id=%s "
        "converted_track_count=%s unconverted_track_count=%s",
        user["id"],
        playlist.id,
        source_playlist.id,
        len(converted_tracks),
        len(unconverted_tracks),
    )
    response = _playlist_response(db, playlist).model_dump()
    response["unconverted_tracks"] = unconverted_tracks
    return response
