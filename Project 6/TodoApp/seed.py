from .database import SessionLocal
from .models import Tracks


SAMPLE_TRACKS = (
    {"title": "Lucid Dreams", "artist": "Juice WRLD", "explicit": True, "version_group": "lucid-dreams"},
    {"title": "Lucid Dreams", "artist": "Juice WRLD", "explicit": False, "version_group": "lucid-dreams"},
    {
        "title": "All Girls Are the Same",
        "artist": "Juice WRLD",
        "explicit": True,
        "version_group": "all-girls-are-the-same",
    },
    {
        "title": "All Girls Are the Same",
        "artist": "Juice WRLD",
        "explicit": False,
        "version_group": "all-girls-are-the-same",
    },
    {"title": "Robbery", "artist": "Juice WRLD", "explicit": True, "version_group": "robbery"},
    {"title": "Robbery", "artist": "Juice WRLD", "explicit": False, "version_group": "robbery"},
    {"title": "Wishing Well", "artist": "Juice WRLD", "explicit": True, "version_group": "wishing-well"},
    {"title": "Wishing Well", "artist": "Juice WRLD", "explicit": False, "version_group": "wishing-well"},
    {"title": "Righteous", "artist": "Juice WRLD", "explicit": True, "version_group": "righteous"},
    {"title": "Righteous", "artist": "Juice WRLD", "explicit": False, "version_group": "righteous"},
)


def seed_catalog() -> None:
    with SessionLocal() as db:
        if db.query(Tracks).first() is None:
            db.add_all(Tracks(**track) for track in SAMPLE_TRACKS)
            db.commit()
