from .database import SessionLocal
from .models import Tracks


SAMPLE_TRACKS = (
    {"title": "Midnight Drive", "artist": "Nova Lane", "explicit": True, "version_group": "midnight-drive"},
    {"title": "Midnight Drive (Clean)", "artist": "Nova Lane", "explicit": False, "version_group": "midnight-drive"},
    {"title": "Paper Moons", "artist": "The Skylines", "explicit": False, "version_group": "paper-moons"},
    {"title": "Paper Moons", "artist": "The Skylines", "explicit": True, "version_group": "paper-moons"},
    {"title": "Golden Hour", "artist": "Mira Sol", "explicit": False, "version_group": "golden-hour"},
    {"title": "Static Hearts", "artist": "Northbound", "explicit": True, "version_group": "static-hearts"},
    {"title": "Static Hearts (Clean)", "artist": "Northbound", "explicit": False, "version_group": "static-hearts"},
)


def seed_catalog() -> None:
    with SessionLocal() as db:
        if db.query(Tracks).first() is None:
            db.add_all(Tracks(**track) for track in SAMPLE_TRACKS)
            db.commit()
