from pydantic import BaseModel, Field
from typing import Optional

class IngestResponse(BaseModel):
    document_key: str
    version: int
    node_count: int
    warnings: list[str] = []

class SelectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    node_ids: list[int] = Field(min_length=1)

class GenerateRequest(BaseModel):
    selection_id: int
    regenerate: bool = False

class TestCase(BaseModel):
    title: str
    objective: str
    preconditions: list[str] = []
    steps: list[str] = []
    expected_result: str
    source_node_ids: list[int] = []
    risk: str = "medium"

class GenerationPayload(BaseModel):
    test_cases: list[TestCase] = Field(min_length=3, max_length=5)
