from fastapi import FastAPI, Request
from .models import Base
from .database import engine
from .routers import auth, users, music
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .seed import seed_catalog

app = FastAPI()
templates = Jinja2Templates(directory="TodoApp/templates")

Base.metadata.create_all(bind=engine)
seed_catalog()

app.mount("/static", StaticFiles(directory="TodoApp/static"), name="static")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request=request, name="music.html", context={})


@app.get("/healthy")
def health_check():
    return {'status': 'Healthy'}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(music.router)
