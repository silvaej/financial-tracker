import argparse
import getpass
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app import crud, models
from app.auth import hash_password
from app.database import SessionLocal

MIN_PASSWORD_LENGTH = 12


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def create(email: str) -> None:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match.", file=sys.stderr)
        raise SystemExit(1)
    _validate_password(password)

    db = SessionLocal()
    try:
        if crud.get_user_by_email(db, email) is not None:
            print(f"A user with email {email!r} already exists.", file=sys.stderr)
            raise SystemExit(1)
        user = crud.create_user(db, email, hash_password(password))
        print(f"Created user {user.email!r} (id={user.id}).")
    finally:
        db.close()


def set_password(email: str) -> None:
    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        print("Passwords don't match.", file=sys.stderr)
        raise SystemExit(1)
    _validate_password(password)

    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, email)
        if user is None:
            print(f"No user with email {email!r}.", file=sys.stderr)
            raise SystemExit(1)
        user.hashed_password = hash_password(password)
        db.commit()
        print(f"Password updated for {user.email!r}.")
    finally:
        db.close()


def assign_orphans(email: str) -> None:
    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, email)
        if user is None:
            print(f"No user with email {email!r}.", file=sys.stderr)
            raise SystemExit(1)

        owned_models: tuple[type[Any], ...] = (
            models.Channel,
            models.PayoutPeriod,
            models.Expense,
            models.Transfer,
            models.Goal,
            models.CreditLine,
            models.Asset,
        )
        for model in owned_models:
            rows = db.scalars(select(model).where(model.user_id.is_(None))).all()
            for row in rows:
                row.user_id = user.id
            print(f"Assigned {len(rows)} orphaned {model.__tablename__} row(s) to {email!r}.")
        db.commit()
    finally:
        db.close()


def create_key(max_uses: int, expires_days: int | None) -> None:
    if max_uses < 1:
        print("--max-uses must be at least 1.", file=sys.stderr)
        raise SystemExit(1)
    expires_at = datetime.now(UTC) + timedelta(days=expires_days) if expires_days else None

    db = SessionLocal()
    try:
        key = crud.create_signup_key(db, max_uses=max_uses, expires_at=expires_at)
        print(f"Signup key: {key.key}")
        print(f"Max uses: {key.max_uses}")
        print(f"Expires: {key.expires_at.isoformat() if key.expires_at else 'never'}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage finance-tracker user accounts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new user account.")
    create_parser.add_argument("email")

    set_password_parser = subparsers.add_parser(
        "set-password", help="Change an existing user's password."
    )
    set_password_parser.add_argument("email")

    assign_orphans_parser = subparsers.add_parser(
        "assign-orphans",
        help="Assign every row with no owner (user_id IS NULL) across all tables to a user.",
    )
    assign_orphans_parser.add_argument("email")

    create_key_parser = subparsers.add_parser(
        "create-key", help="Create an invite key for /signup."
    )
    create_key_parser.add_argument(
        "--max-uses", type=int, default=1, help="How many accounts this key can create (default 1)."
    )
    create_key_parser.add_argument(
        "--expires-days",
        type=int,
        default=None,
        help="Key expires this many days from now (default: never).",
    )

    args = parser.parse_args()
    if args.command == "create":
        create(args.email)
    elif args.command == "set-password":
        set_password(args.email)
    elif args.command == "assign-orphans":
        assign_orphans(args.email)
    elif args.command == "create-key":
        create_key(args.max_uses, args.expires_days)


if __name__ == "__main__":
    main()
