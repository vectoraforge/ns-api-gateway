from fastapi import APIRouter
from starlette.responses import JSONResponse

router = APIRouter()


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "up"})
