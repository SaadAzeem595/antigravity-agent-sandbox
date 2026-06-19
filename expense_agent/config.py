import os

from pydantic import BaseModel


class Config(BaseModel):
    expense_threshold: float = float(os.getenv("EXPENSE_THRESHOLD", "100.0"))
    model_name: str = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite")


settings = Config()
