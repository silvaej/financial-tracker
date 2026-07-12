from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/goal-contributions", tags=["goal-contributions"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/cashflow_page.html", crud.cashflow_page_data(db, user_id)
    )


@router.post("")
def create_goal_contribution(
    request: Request,
    goal_id: int = Form(...),
    channel_id: int = Form(...),
    payout_period_id: int = Form(...),
    amount: float = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_goal_contribution(
            db,
            schemas.GoalContributionCreate(
                goal_id=goal_id,
                channel_id=channel_id,
                payout_period_id=payout_period_id,
                amount=amount,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/{contribution_id}")
def update_goal_contribution(
    request: Request,
    contribution_id: int,
    amount: float = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.update_goal_contribution(
        db, contribution_id, schemas.GoalContributionUpdate(amount=amount), current_user.id
    )
    return _render_page(request, db, current_user.id)


@router.delete("/{contribution_id}")
def delete_goal_contribution(
    request: Request,
    contribution_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_goal_contribution(db, contribution_id, current_user.id)
    return _render_page(request, db, current_user.id)
