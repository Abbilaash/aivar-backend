import uuid
import hashlib
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserCreate, UpdateMonitoringSettings


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _hash_password(self, password: str) -> str:
        """
        Hashes password securely using SHA-256 with a fixed salt.
        """
        salt = "aivar-secure-salt-string-99"
        return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def create(self, schema: UserCreate) -> User:
        user = User(
            username=schema.username,
            password_hash=self._hash_password(schema.password),
            monitored_namespaces={}
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def verify_credentials(self, username: str, password: str) -> Optional[User]:
        user = await self.get_by_username(username)
        if not user:
            return None
        hashed = self._hash_password(password)
        if user.password_hash == hashed:
            return user
        return None

    async def update_monitoring_settings(self, user: User, schema: UpdateMonitoringSettings) -> User:
        user.monitored_namespaces = schema.monitored_namespaces
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_password(self, user: User, new_password: str) -> User:
        user.password_hash = self._hash_password(new_password)
        await self.session.commit()
        await self.session.refresh(user)
        return user
