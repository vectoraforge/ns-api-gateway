from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    phrase: str = Field(..., description="The phrase to analyze")
    lang: str | None = Field(default="en", description="Language code (e.g., 'en', 'es')")


class Issue(BaseModel):
    phrase_part: str = Field(..., description="The problematic part of the phrase")
    explanation: str = Field(..., description="Explanation of why this is an issue")


class AnalyzeResponse(BaseModel):
    phrase: str = Field(..., description="The original phrase")
    lang: str = Field(..., description="Language code used")
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    alternatives: list[str] = Field(default_factory=list, description="Corrected alternatives")
    assessment: str = Field(..., description="Overall assessment of naturalness")


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")