"""FastAPI dependencies exposing the authenticated request identity."""

from fastapi import Depends, HTTPException, Request, status

from .models import CurrentUser


def require_current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "current_user", None)
    if not isinstance(user, CurrentUser):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
        )
    return user


def optional_current_user(request: Request) -> CurrentUser | None:
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, CurrentUser) else None


def current_user_id(user: CurrentUser = Depends(require_current_user)) -> str:
    return user.id


def current_user_is_admin(
    user: CurrentUser = Depends(require_current_user),
) -> bool:
    return user.is_admin


def require_admin_user(
    user: CurrentUser = Depends(require_current_user),
) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_required",
        )
    return user
