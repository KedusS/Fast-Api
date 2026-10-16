import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from .models import Base
from .database import engine
from .routers import auth, users, music
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "juicebox.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if not any(
    isinstance(handler, RotatingFileHandler)
    and Path(handler.baseFilename) == LOG_FILE
    for handler in root_logger.handlers
):
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory=APP_DIR / "templates")

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Request failed method=%s path=%s",
            request.method,
            request.url.path,
        )
        raise

    duration_ms = (perf_counter() - start_time) * 1000
    logger.info(
        "Request completed method=%s path=%s status_code=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Render the music app and pass along the signed-in user, if there is one.
@app.get("/")
def home(request: Request):
    user = auth.decode_access_token(request.cookies.get("access_token"))
    return templates.TemplateResponse(request=request, name="music.html", context={"user": user})


# Provide a simple endpoint for checking whether the API is running.
@app.get("/healthy")
def health_check():
    return {'status': 'Healthy'}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(music.router)
