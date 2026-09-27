from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    # Upper bound keeps hashing work bounded; real passwords are far shorter.
    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    """Only safe metadata: never a password hash, session token, or session hash."""

    authenticated: bool
    username: str | None = None
    # For the X-CSRF-Token header. Kept in frontend memory only.
    csrf_token: str | None = None
