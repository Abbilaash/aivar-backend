import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import httpx

from app.db.session import get_db_session
from app.models.asset import Asset
from app.models.cluster import Cluster
from app.core.security import verify_api_key
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotChatRequest(BaseModel):
    message: str


class CopilotChatResponse(BaseModel):
    response: str


@router.post(
    "/chat",
    response_model=CopilotChatResponse,
    summary="Send a message to AIVAR Copilot (proxied through EKS chatbot service)",
    dependencies=[Depends(verify_api_key)]
)
async def copilot_chat(
    payload: CopilotChatRequest,
    x_user_username: Optional[str] = Header(None, alias="X-User-Username"),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Proxy endpoint that:
    1. Fetches live asset inventory from the database (scoped to current user)
    2. Formats it as context for the LLM prompt
    3. Forwards the message + context to the EKS Chatbot Pod (Groq-powered)
    4. Returns the LLM response back to the frontend
    """

    # 1. Fetch live asset data from DB scoped to the current user
    stmt = select(Asset)
    if x_user_username:
        stmt = stmt.join(Cluster).where(
            or_(Cluster.created_by == x_user_username, Cluster.created_by == None)
        )
    
    result = await db.execute(stmt)
    assets = result.scalars().all()

    # 2. Build a structured context string for the LLM
    if assets:
        lines = [f"Total active AI assets: {len(assets)}\n"]
        for a in assets:
            lines.append(
                f"• **{a.asset_name}** | Type: {a.asset_type} | "
                f"Namespace: {a.namespace} | Risk: {a.risk_tier.upper()} | "
                f"Status: {a.status.upper()} | Owner: {a.owner} | "
                f"Workload: {a.workload_kind}/{a.workload_name}"
            )
        context = "\n".join(lines)
    else:
        context = "No AI assets are currently registered in the AIVAR system."

    logger.info(f"Copilot proxy: forwarding to {settings.CHATBOT_SERVICE_URL}")

    # 3. Call the EKS chatbot service
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                settings.CHATBOT_SERVICE_URL,
                json={"text": payload.message, "context": context},
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            return CopilotChatResponse(response=data.get("response", "No response received."))

        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail="AIVAR Copilot is not reachable. Make sure the chatbot pod is running in EKS."
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="AIVAR Copilot took too long to respond. Please try again."
            )
        except Exception as e:
            logger.error(f"Copilot proxy error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Copilot error: {str(e)}")
