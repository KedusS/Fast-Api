import logging
from datetime import timedelta, datetime, timezone
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette import status
from starlette.responses import RedirectResponse
from ..database import SessionLocal
from ..models import Users
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from fastapi.templating import Jinja2Templates

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)
logger = logging.getLogger(__name__)

SECRET_KEY = '197b2c37c391bed93fe80344fe73b806947a65e36206e05a1a23c2fa12702fe3'
ALGORITHM = 'HS256'

bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')


class CreateUserRequest(BaseModel):
    username: str
    email: str
    first_name: str
    last_name: str
    password: str
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str


# Provide a database session for each authentication request and close it afterward.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


### Pages ###

# Open a login page and show the current user when a valid session cookie exists.
@router.get("/login-page")
def render_login_page(request: Request):
    user = decode_access_token(request.cookies.get("access_token"))
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "user": user},
    )

# Open the account registration page and include any signed-in user information.
@router.get("/register-page")
def render_register_page(request: Request):
    user = decode_access_token(request.cookies.get("access_token"))
    return templates.TemplateResponse(request=request, name="register.html", context={"user": user})


# Check form credentials, then sign the browser in with a short-lived token cookie.
@router.post("/login")
async def login_from_form(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: db_dependency,
):
    """Validate credentials, then persist the token in a browser cookie."""
    user = authenticate_user(username, password, db)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Incorrect username or password.",
                "user": decode_access_token(request.cookies.get("access_token")),
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(user.username, user.id, user.role, timedelta(minutes=20))
    logger.info("Browser login succeeded user_id=%s", user.id)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=20 * 60,
        path="/",
        secure=request.url.scheme == "https",
        httponly=False,
        samesite="lax",
    )
    return response


### Endpoints ###
# Find the account by username and verify the submitted password against its hash.
def authenticate_user(username: str, password: str, db):
    user = db.query(Users).filter(Users.username == username).first()
    if not user:
        logger.warning("Authentication failed")
        return False
    # Compare the submitted password to the stored hash; never store or compare plain text.
    if not bcrypt_context.verify(password, user.hashed_password):
        logger.warning("Authentication failed")
        return False
    return user


# Create a signed token containing the user's identity, role, and expiration time.
def create_access_token(username: str, user_id: int, role: str, expires_delta: timedelta):
    # Put identity and role in the signed token so protected routes can authorize requests.
    encode = {'sub': username, 'id': user_id, 'role': role}
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({'exp': expires})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


# Decode a token and return its user details, or None when it is missing or invalid.
def decode_access_token(token: str | None) -> dict | None:
    """Return identity data for valid tokens; treat missing or invalid cookies as logged out."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

    username = payload.get("sub")
    user_id = payload.get("id")
    if username is None or user_id is None:
        return None
    return {"username": username, "id": user_id, "user_role": payload.get("role")}


# Require a valid bearer token and return the signed-in user's details.
async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    user = decode_access_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate user.",
        )
    return user


# Register a new account after hashing its password before it is stored.
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(db: db_dependency,
                      create_user_request: CreateUserRequest):
    create_user_model = Users(
        email=create_user_request.email,
        username=create_user_request.username,
        first_name=create_user_request.first_name,
        last_name=create_user_request.last_name,
        role=create_user_request.role,
        hashed_password=bcrypt_context.hash(create_user_request.password),
        is_active=True,
    )

    db.add(create_user_model)
    db.commit()
    db.refresh(create_user_model)
    logger.info("Account created user_id=%s", create_user_model.id)


# Authenticate API clients and return a bearer token for later requests.
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                                 db: db_dependency):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not validate user.')
    token = create_access_token(user.username, user.id, user.role, timedelta(minutes=20))
    logger.info("API login succeeded user_id=%s", user.id)

    return {'access_token': token, 'token_type': 'bearer'}
