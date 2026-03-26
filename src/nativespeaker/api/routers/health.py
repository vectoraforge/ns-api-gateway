from fastapi import APIRouter
from starlette.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health/ready",
            summary="Readiness probe",
            description="Kubernetes readiness check. Returns 200 when the service is ready.")
async def readiness() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "up"})
