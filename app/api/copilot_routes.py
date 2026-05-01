"""FastAPI endpoints for Copilot AI integration"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.services.ai_service import get_copilot_service

router = APIRouter(prefix="/api/ai", tags=["AI Integration"])


# ============================================================================
# Models/Schemas
# ============================================================================


class AuthorizationRequest(BaseModel):
    """Request to start OAuth Device Code Flow."""

    enterprise_url: Optional[str] = None


class AuthorizationResponse(BaseModel):
    """Response with OAuth device authorization info."""

    verification_uri: str
    user_code: str
    device_code: str
    expires_in: int


class TokenCheckResponse(BaseModel):
    """Response checking if token is valid."""

    ok: bool
    authenticated: bool
    message: str


class ModelsResponse(BaseModel):
    """List of available models."""

    models: list[dict]
    count: int


class GenerateRequest(BaseModel):
    """Request to generate content."""

    prompt: str
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = None


class GenerateResponse(BaseModel):
    """Response with generated content."""

    content: str
    model: str
    status: str = "success"


class RobotTestRequest(BaseModel):
    """Request to generate Robot Framework test."""

    prompt: str
    context: Optional[str] = None
    page_structure: Optional[dict] = None
    model: Optional[str] = None


class RobotTestResponse(BaseModel):
    """Response with generated Robot Framework test."""

    test_code: str
    model: str
    status: str = "success"


class HealthCheckResponse(BaseModel):
    """Health check response."""

    ok: bool
    authenticated: bool
    model: str
    message: str


# ============================================================================
# Routes
# ============================================================================


@router.post("/authorize", response_model=AuthorizationResponse)
async def start_oauth_flow(request: AuthorizationRequest) -> AuthorizationResponse:
    """Start OAuth Device Code Flow authorization.

    This endpoint initiates the Copilot OAuth authentication process.
    User will receive a link and code to visit for authorization.

    Args:
        request: Optional enterprise URL

    Returns:
        AuthorizationResponse with verification details
    """
    service = get_copilot_service()

    try:
        # Check if we already have a valid token
        try:
            token = await service.get_valid_token()
            if token:
                raise HTTPException(
                    status_code=200,
                    detail="Already authenticated"
                )
        except RuntimeError:
            pass  # No valid token, continue with auth flow
        except HTTPException:
            raise

        # Request device code ONLY (don't wait for user interaction)
        from httpx import AsyncClient
        from app.llm.copilot_auth import resolve_oauth_endpoints

        async with AsyncClient(timeout=10.0) as client:
            device_response = await service.auth_manager._request_device_code(client)

        # Return device code info for frontend to display
        return AuthorizationResponse(
            verification_uri=device_response.verification_uri,
            user_code=device_response.user_code,
            device_code=device_response.device_code,
            expires_in=device_response.expires_in,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {str(e)}")


@router.get("/token/check", response_model=TokenCheckResponse)
async def check_token() -> TokenCheckResponse:
    """Check if Copilot token is valid.

    Returns:
        TokenCheckResponse with authentication status
    """
    service = get_copilot_service()
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"📋 Checking token. Auth file exists: {service.auth_manager.auth_file_path.exists()}")
        token = await service.get_valid_token()
        logger.info(f"✓ Token found: {token[:20]}...")
        return TokenCheckResponse(
            ok=True,
            authenticated=bool(token),
            message="Copilot token is valid",
        )
    except Exception as e:
        logger.warning(f"⚠️ Token check failed: {str(e)}")
        return TokenCheckResponse(
            ok=False,
            authenticated=False,
            message=f"Token check failed: {str(e)}",
        )


class DeviceCodePollRequest(BaseModel):
    """Request to poll for device code authorization."""
    device_code: str


class DeviceCodePollResponse(BaseModel):
    """Response from device code polling."""
    authenticated: bool
    message: str
    slow_down: bool = False


@router.post("/authorize/poll", response_model=DeviceCodePollResponse)
async def poll_device_code(request: DeviceCodePollRequest) -> DeviceCodePollResponse:
    """Poll to check if device code authorization is complete.
    
    The frontend should call this endpoint periodically while showing
    the device code to the user. Once the user authorizes, this endpoint
    will return authenticated=true.

    Args:
        request: Device code to poll

    Returns:
        DeviceCodePollResponse with authentication status
    """
    service = get_copilot_service()

    try:
        from httpx import AsyncClient

        # Try to get token without blocking
        async with AsyncClient(timeout=5.0) as client:
            token_response = await service.auth_manager._request_token_by_device_code(
                request.device_code, client
            )

        if token_response.access_token:
            # Save the token so future requests recognize as authenticated
            from app.llm.copilot_auth import CopilotAuthRecord
            from datetime import datetime, timedelta
            import time
            import logging
            
            logger = logging.getLogger(__name__)
            logger.info(f"🔐 Token received. Saving auth record...")
            
            # Calculate expiry in Unix timestamp (milliseconds)
            # Classic GitHub tokens (gho_) have no expires_in — default to 28 days
            expires_at_ms = int((time.time() + (token_response.expires_in or 86400 * 28)) * 1000)
            
            record = CopilotAuthRecord(
                access_token=token_response.access_token,
                token_type=token_response.token_type or "Bearer",
                refresh_token=token_response.refresh_token,
                expires_at=expires_at_ms,
            )
            await service.auth_manager._save_auth_record(record)
            logger.info(f"✓ Auth record saved to {service.auth_manager.auth_file_path}")
            logger.info(f"✓ Auth record content: access_token={record.access_token[:20]}...")
            
            return DeviceCodePollResponse(
                authenticated=True,
                message="✅ Authorization successful! Copilot is ready."
            )

        if token_response.error == "authorization_pending":
            return DeviceCodePollResponse(
                authenticated=False,
                message="⏳ Waiting for authorization... Please complete login in your browser."
            )

        if token_response.error == "slow_down":
            return DeviceCodePollResponse(
                authenticated=False,
                slow_down=True,
                message="⏳ Please wait a moment before trying again..."
            )

        if token_response.error == "expired_token":
            return DeviceCodePollResponse(
                authenticated=False,
                message="❌ Device code expired. Please start the authorization process again."
            )

        return DeviceCodePollResponse(
            authenticated=False,
            message=f"Authorization pending... ({token_response.error})"
        )

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Poll failed: {str(e)}"
        )


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """Get list of available Copilot models.

    Returns:
        ModelsResponse with available models
    """
    service = get_copilot_service()

    try:
        models = await service.fetch_models()
        return ModelsResponse(
            models=[
                {
                    "id": m.id,
                    "name": m.name,
                    "family": m.family,
                    "capabilities": m.capabilities.model_dump(),
                    "limits": m.limits.model_dump(),
                }
                for m in models
            ],
            count=len(models),
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to fetch models: {str(e)}"
        )


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate content using Copilot.

    Args:
        request: Generation request with prompt and options

    Returns:
        GenerateResponse with generated content
    """
    service = get_copilot_service()

    try:
        content = await service.generate(
            prompt=request.prompt,
            model=request.model,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return GenerateResponse(
            content=content,
            model=request.model or "gpt-5-mini",
            status="success",
        )

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Generation failed: {str(e)}"
        )


@router.post("/robot-test", response_model=RobotTestResponse)
async def generate_robot_test(request: RobotTestRequest) -> RobotTestResponse:
    """Generate Robot Framework test code.

    Args:
        request: Test generation request

    Returns:
        RobotTestResponse with generated test code
    """
    service = get_copilot_service()

    try:
        test_code = await service.generate_robot_test(
            prompt=request.prompt,
            context=request.context,
            page_structure=request.page_structure,
            model=request.model,
        )

        return RobotTestResponse(
            test_code=test_code,
            model=request.model or "gpt-5-mini",
            status="success",
        )

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Test generation failed: {str(e)}"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Health check for Copilot integration.

    Returns:
        HealthCheckResponse with integration status
    """
    service = get_copilot_service()

    try:
        check = await service.check_connection()
        return HealthCheckResponse(
            ok=check.get("ok", False),
            authenticated=check.get("ok", False),
            model="gpt-5-mini",
            message=check.get("message", "Health check complete"),
        )
    except Exception as e:
        return HealthCheckResponse(
            ok=False,
            authenticated=False,
            model="gpt-5-mini",
            message=f"Health check failed: {str(e)}",
        )
