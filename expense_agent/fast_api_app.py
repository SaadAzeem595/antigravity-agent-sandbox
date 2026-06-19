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
import logging
import os
import json

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expense_agent.agent import root_agent
from expense_agent.app_utils.telemetry import setup_telemetry
from expense_agent.app_utils.typing import Feedback

# Set up standard logging to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fast_api_app")

load_dotenv()
setup_telemetry()

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

# Telemetry: Set otel_to_cloud=False
otel_to_cloud = False

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=otel_to_cloud,
)
app.title = "ambient-expense-agent"
app.description = "API for interacting with the Agent ambient-expense-agent"

# In-memory session service instance for the webhook
session_service = InMemorySessionService()


@app.post("/")
async def handle_pubsub(request: Request):
    """Accepts Pub/Sub trigger messages and feeds each one into the workflow."""
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        return {"status": "error", "message": "Invalid JSON body"}

    logger.info(f"Received Pub/Sub message body: {body}")

    # Extract fully-qualified subscription path (e.g. "projects/my-project/subscriptions/my-subscription")
    sub_path = body.get("subscription", "projects/default/subscriptions/default-sub")
    
    # Normalize to short name (e.g. "my-subscription") to keep session records readable
    sub_name = sub_path.split("/")[-1]
    logger.info(f"Normalized subscription path '{sub_path}' to short name '{sub_name}'")

    # Get or create session for the subscriber name to keep track of its history cleanly
    sessions_response = await session_service.list_sessions(user_id=sub_name, app_name="expense_agent")
    if sessions_response.sessions:
        session = sessions_response.sessions[0]
    else:
        session = await session_service.create_session(user_id=sub_name, app_name="expense_agent")

    # Run the ambient expense workflow
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="expense_agent",
    )

    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=json.dumps(body))]
    )

    events = []
    async for event in runner.run_async(
        new_message=message,
        user_id=sub_name,
        session_id=session.id,
    ):
        events.append(event)

    # Search for the final decision output (from either auto_approve or record_outcome)
    final_output = None
    for event in events:
        if event.node_name in ("record_outcome", "auto_approve"):
            final_output = event.output
            break

    logger.info(f"Workflow execution completed for subscription '{sub_name}'. Final output: {final_output}")

    return {
        "status": "success",
        "subscription": sub_name,
        "session_id": session.id,
        "final_output": final_output,
    }


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.info(f"Feedback Log: {feedback.model_dump()}")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
