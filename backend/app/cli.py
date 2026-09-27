"""Owner account administration (ADR-007). There is no registration or reset endpoint.

    python -m app.cli create-owner --username NAME
    python -m app.cli set-password --username NAME

Passwords are read with getpass (never echoed) or, for automation with synthetic test
credentials, as one line from standard input (--password-stdin). Never as an argument.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import AuthUser
from app.services import auth


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise auth.OwnerError("Passwords don't match.")
    return password


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Owner account administration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("create-owner", "create the single owner account"),
        ("set-password", "rotate a password and revoke that user's sessions"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--username", required=True)
        command.add_argument(
            "--password-stdin",
            action="store_true",
            help="read the password from standard input (automation with test credentials)",
        )
    args = parser.parse_args(argv)

    action: Callable[[Session, str, str], AuthUser] = (
        auth.create_owner if args.command == "create-owner" else auth.set_password
    )
    try:
        password = _read_password(args.password_stdin)
        with Session(get_engine()) as db:
            action(db, args.username, password)
            db.commit()
    except auth.OwnerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    done = "Created owner" if args.command == "create-owner" else "Password updated for"
    print(f"{done} {args.username!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
