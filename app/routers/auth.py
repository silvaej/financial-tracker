from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud
from app.auth import verify_password
from app.database import get_db

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
def login_form(request: Request) -> Response:
    if request.session.get("user_id") is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    user = crud.get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password."}, status_code=401
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
