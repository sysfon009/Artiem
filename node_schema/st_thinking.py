from pydantic import BaseModel, Field
from typing import List

# Model untuk struktur di dalam list
class ThoughtItem(BaseModel):
    text: str
    thought: bool = Field(default=True)

# Model utama (schema) yang dipanggil di node 1
class SchemaThought(BaseModel):
    thought_process: List[ThoughtItem]