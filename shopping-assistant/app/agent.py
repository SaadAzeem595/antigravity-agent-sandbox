# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

import os
import google.auth
from dotenv import load_dotenv

load_dotenv()

# Check if we have default credentials, otherwise fallback to standard GenAI with API Key
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"


# In-memory store for single-use discount codes and registered user IDs
DISCOUNT_CODES = {
    "WELCOME50": {"discount": 50, "redeemed_by": None},
    "SUMMER20": {"discount": 20, "redeemed_by": None},
}
REGISTERED_USERS = {"user123", "user456", "kaggle_student", "student", "shopper1"}


def redeem_discount_code(code: str, user_id: str) -> dict:
    """Redeems a single-use discount code for a registered user ID.

    Args:
        code: The discount code to redeem (e.g., WELCOME50, SUMMER20).
        user_id: The registered user ID of the customer redeeming the code.

    Returns:
        A dictionary indicating the status and results of the redemption.
    """
    code_clean = code.strip().upper()
    user_clean = user_id.strip()

    if user_clean not in REGISTERED_USERS:
        return {"status": "error", "message": f"User ID '{user_clean}' is not registered."}

    if code_clean not in DISCOUNT_CODES:
        return {"status": "error", "message": f"Discount code '{code_clean}' is invalid."}

    discount_info = DISCOUNT_CODES[code_clean]
    if discount_info["redeemed_by"] is not None:
        return {
            "status": "error",
            "message": f"Discount code '{code_clean}' has already been redeemed by user '{discount_info['redeemed_by']}'."
        }

    discount_info["redeemed_by"] = user_clean
    return {
        "status": "success",
        "message": f"Discount code '{code_clean}' successfully redeemed for user '{user_clean}'. Enjoy your {discount_info['discount']}% discount!"
    }


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyD-mock-key-value-12345"),
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="You are a helpful AI shopping assistant for a retail store. Help customers find products, answer shopping queries, and assist them in redeeming discount codes when they provide their registered user ID. You must use the redeem_discount_code tool to redeem discount codes.",
    tools=[redeem_discount_code],
)

app = App(
    root_agent=root_agent,
    name="app",
)
