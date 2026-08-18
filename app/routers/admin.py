from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import require_admin
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])


def _render_page(request: Request, db: Session) -> HTMLResponse:
    return templates.TemplateResponse(request, "partials/admin_page.html", crud.admin_page_data(db))


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
) -> HTMLResponse:
    template = "partials/admin_page.html" if request.headers.get("HX-Request") else "admin.html"
    return templates.TemplateResponse(request, template, crud.admin_page_data(db))


@router.post("/users/{user_id}/delete")
def delete_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> HTMLResponse:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account here.")
    if db.get(models.User, user_id) is None:
        raise HTTPException(status_code=404)
    crud.delete_user_and_data(db, user_id)
    return _render_page(request, db)


@router.post("/signup-keys")
def create_signup_key(
    request: Request,
    max_uses: int = Form(1),
    expires_days: str = Form(""),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
) -> HTMLResponse:
    data = schemas.SignupKeyCreate(
        max_uses=max_uses, expires_days=int(expires_days) if expires_days else None
    )
    expires_at = (
        datetime.now(UTC) + timedelta(days=data.expires_days) if data.expires_days else None
    )
    crud.create_signup_key(db, max_uses=data.max_uses, expires_at=expires_at)
    return _render_page(request, db)


@router.post("/signup-keys/{key_id}/revoke")
def revoke_signup_key(
    request: Request,
    key_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
) -> HTMLResponse:
    if db.get(models.SignupKey, key_id) is None:
        raise HTTPException(status_code=404)
    crud.revoke_signup_key(db, key_id)
    return _render_page(request, db)


@router.post("/orphans/{table_name}/assign")
def assign_orphans(
    request: Request,
    table_name: str,
    target_user_id: int = Form(...),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
) -> HTMLResponse:
    if db.get(models.User, target_user_id) is None:
        raise HTTPException(status_code=404, detail="No such user.")
    try:
        crud.assign_orphans_for_table(db, table_name, target_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db)
