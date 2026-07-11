import argparse
import getpass
import sys
from typing import Any

from sqlalchemy import select

from app import crud, models
from app.auth import hash_password
from app.database import SessionLocal


def create(email: str) -> None:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match.", file=sys.stderr)
        raise SystemExit(1)

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

    args = parser.parse_args()
    if args.command == "create":
        create(args.email)
    elif args.command == "set-password":
        set_password(args.email)
    elif args.command == "assign-orphans":
        assign_orphans(args.email)


if __name__ == "__main__":
    main()
