from .database import Base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint


class Users(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True)
    username = Column(String, unique=True)
    first_name = Column(String)
    last_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String)
    phone_number = Column(String)


class Tracks(Base):
    __tablename__ = 'tracks'
    __table_args__ = (
        UniqueConstraint('version_group', 'explicit', name='uq_track_version_explicit'),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    explicit = Column(Boolean, nullable=False)
    version_group = Column(String, nullable=False, index=True)


class Playlists(Base):
    __tablename__ = 'playlists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=True)
    target_explicit = Column(Boolean, nullable=True)


class PlaylistTracks(Base):
    __tablename__ = 'playlist_tracks'

    playlist_id = Column(Integer, ForeignKey("playlists.id"), primary_key=True)
    position = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
