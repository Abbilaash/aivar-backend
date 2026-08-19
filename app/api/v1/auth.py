from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db_session
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserLogin, UserResponse, UpdateMonitoringSettings, UserChangePassword

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account"
)
async def register(
    schema: UserCreate,
    db: AsyncSession = Depends(get_db_session)
):
    repo = UserRepository(db)
    
    # Check if username exists
    existing = await repo.get_by_username(schema.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
        
    user = await repo.create(schema)
    return user


@router.post(
    "/login",
    response_model=UserResponse,
    summary="Login and verify user credentials"
)
async def login(
    schema: UserLogin,
    db: AsyncSession = Depends(get_db_session)
):
    repo = UserRepository(db)
    user = await repo.verify_credentials(schema.username, schema.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    return user


@router.post(
    "/monitored-settings/{user_id}",
    response_model=UserResponse,
    summary="Update monitored clusters and namespaces configuration for a user"
)
async def update_settings(
    user_id: UUID,
    schema: UpdateMonitoringSettings,
    db: AsyncSession = Depends(get_db_session)
):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    updated_user = await repo.update_monitoring_settings(user, schema)
    return updated_user


@router.post(
    "/change-password/{user_id}",
    response_model=UserResponse,
    summary="Change password for a user account"
)
async def change_password(
    user_id: UUID,
    schema: UserChangePassword,
    db: AsyncSession = Depends(get_db_session)
):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    updated_user = await repo.update_password(user, schema.password)
    return updated_user
