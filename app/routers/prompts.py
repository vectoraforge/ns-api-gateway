import logging
from fastapi import APIRouter, Query, Request

from app.schema import AnalyzeRequest, AnalyzeResponse, ExamplesResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts")


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    service = request.app.state.service

    logger.info(f"Analyzing {body.lang} phrase: '{body.phrase}'")

    return await service.analyze(body.phrase, body.lang)


@router.get("/examples", response_model=ExamplesResponse)
async def get_examples(
    request: Request,
    lang: str = Query(..., description="Language code (e.g., 'en', 'es')")
) -> ExamplesResponse:
    service = request.app.state.service

    return service.get_examples(lang)
