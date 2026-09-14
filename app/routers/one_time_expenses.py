from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.image_uploads import read_receipt_upload
from app.templating import templates

router = APIRouter(prefix="/one-time-expenses", tags=["one-time-expenses"])

MAX_RECEIPT_BYTES = 5 * 1024 * 1024


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


def _parse_category_id(raw: str) -> int | None:
    return int(raw) if raw else None


async def _read_receipt(receipt: UploadFile | None) -> tuple[bytes, str] | None:
    return await read_receipt_upload(receipt, max_bytes=MAX_RECEIPT_BYTES, label="Receipt")


@router.post("")
async def create_one_time_expense(
    request: Request,
    name: str = Form(...),
    amount: float = Form(...),
    cycle_id: int = Form(...),
    channel_id: int = Form(...),
    category_id: str = Form(""),
    date: date = Form(...),
    receipt: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    receipt_payload = await _read_receipt(receipt)
    try:
        expense = crud.create_one_time_expense(
            db,
            schemas.OneTimeExpenseCreate(
                name=name,
                amount=amount,
                cycle_id=cycle_id,
                channel_id=channel_id,
                category_id=_parse_category_id(category_id),
                date=date,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if receipt_payload is not None:
        crud.set_one_time_expense_receipt(
            db, expense.id, receipt_payload[0], receipt_payload[1], current_user.id
        )
    return _render_page(request, db, current_user.id)


@router.patch("/{expense_id}")
async def update_one_time_expense(
    request: Request,
    expense_id: int,
    name: str = Form(...),
    amount: float = Form(...),
    cycle_id: int = Form(...),
    channel_id: int = Form(...),
    category_id: str = Form(""),
    date: date = Form(...),
    receipt: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    receipt_payload = await _read_receipt(receipt)
    try:
        crud.update_one_time_expense(
            db,
            expense_id,
            schemas.OneTimeExpenseUpdate(
                name=name,
                amount=amount,
                cycle_id=cycle_id,
                channel_id=channel_id,
                category_id=_parse_category_id(category_id),
                date=date,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if receipt_payload is not None:
        crud.set_one_time_expense_receipt(
            db, expense_id, receipt_payload[0], receipt_payload[1], current_user.id
        )
    return _render_page(request, db, current_user.id)


@router.delete("/{expense_id}")
def delete_one_time_expense(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_one_time_expense(db, expense_id, current_user.id)
    return _render_page(request, db, current_user.id)


@router.post("/clear")
def clear_one_time_expenses(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.clear_one_time_expenses(db, current_user.id)
    return _render_page(request, db, current_user.id)


@router.delete("/{expense_id}/receipt")
def delete_one_time_expense_receipt(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.clear_one_time_expense_receipt(db, expense_id, current_user.id)
    return _render_page(request, db, current_user.id)


@router.get("/{expense_id}/receipt")
def get_one_time_expense_receipt(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    expense = crud.get_one_time_expense_receipt(db, expense_id, current_user.id)
    if expense is None or expense.receipt_data is None or expense.receipt_mimetype is None:
        raise HTTPException(status_code=404, detail="No receipt for this expense.")
    return Response(
        content=expense.receipt_data,
        media_type=expense.receipt_mimetype,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
