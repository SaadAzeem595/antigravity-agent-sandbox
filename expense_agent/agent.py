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

import base64
import datetime
import json
import os
import re
from typing import Any
from zoneinfo import ZoneInfo

import google.auth
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.models import Gemini
from google.adk.workflow import Workflow, node
from google.genai import types
from pydantic import BaseModel, Field

from .config import settings

# Load local environment config
load_dotenv()

# Setup authentication dynamically based on API key vs GCP/Vertex presence
if os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
else:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    try:
        _, project_id = google.auth.default()
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    except Exception:
        pass
    os.environ["GOOGLE_CLOUD_LOCATION"] = os.getenv("GOOGLE_CLOUD_LOCATION", "global")


# 1. Define Schemas
class ExpenseReport(BaseModel):
    amount: float = Field(description="The numeric expense amount in USD.")
    submitter: str = Field(description="The name or email of the submitter.")
    category: str = Field(description="Expense category (e.g., travel, meals).")
    description: str = Field(description="Brief explanation of the expense.")
    date: str = Field(description="Date when the expense was incurred.")


class RiskAssessment(BaseModel):
    risk_score: int = Field(
        description="Risk assessment score from 1 (low) to 10 (high)."
    )
    risk_factors: list[str] = Field(
        description="List of risk factors or company policy violations found."
    )
    alert_raised: bool = Field(
        description="Whether a security or compliance alert should be raised."
    )
    reason: str = Field(description="Explanation of the risk evaluation and verdict.")


# 2. Define Workflow Nodes
def parse_expense_report(ctx: Context, node_input: Any) -> Event:
    """Parses raw Pub/Sub or testing input event data."""
    raw_text = ""
    if hasattr(node_input, "parts"):
        raw_text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, str):
        raw_text = node_input
    elif isinstance(node_input, dict):
        raw_text = json.dumps(node_input)
    else:
        raw_text = str(node_input)

    try:
        event_dict = json.loads(raw_text)
    except Exception as e:
        raise ValueError(f"Input is not a valid JSON event: {e}") from e

    # Resolve "data" field (handles real Pub/Sub wrapper vs direct test events)
    data_content = event_dict.get("data")
    if data_content is None:
        message = event_dict.get("message")
        if isinstance(message, dict):
            data_content = message.get("data")
        else:
            data_content = event_dict

    # Check for Base64 or plain JSON in "data"
    if isinstance(data_content, str):
        try:
            decoded_dict = json.loads(data_content)
        except Exception:
            try:
                decoded_bytes = base64.b64decode(data_content)
                decoded_dict = json.loads(decoded_bytes.decode("utf-8"))
            except Exception as e:
                raise ValueError(
                    f"Could not parse 'data' key as JSON or Base64 JSON: {e}"
                ) from e
        data_content = decoded_dict

    if not isinstance(data_content, dict):
        raise ValueError("Resolved expense details must be a JSON object.")

    # Construct and validate parsed expense report
    expense = ExpenseReport(
        amount=float(data_content.get("amount", 0.0)),
        submitter=str(data_content.get("submitter", "Unknown")),
        category=str(data_content.get("category", "General")),
        description=str(data_content.get("description", "")),
        date=str(data_content.get("date", "")),
    )

    # Store expense globally in workflow state
    return Event(output=expense, state={"expense": expense.model_dump()})


def scrub_personal_data(description: str) -> tuple[str, list[str]]:
    """Scrubs SSNs and Credit Card numbers from the description."""
    redacted_categories = []
    
    # 1. SSN Regex patterns
    # Format with separators (dashes/spaces)
    ssn_pattern = r'\b\d{3}[- ]\d{2}[- ]\d{4}\b'
    # Unformatted raw 9 digits
    ssn_raw_pattern = r'\b\d{9}\b'
    
    ssn_found = False
    if re.search(ssn_pattern, description):
        description = re.sub(ssn_pattern, "[SSN]", description)
        ssn_found = True
    if re.search(ssn_raw_pattern, description):
        description = re.sub(ssn_raw_pattern, "[SSN]", description)
        ssn_found = True
        
    if ssn_found:
        redacted_categories.append("SSN")
        
    # 2. Credit Card Regex pattern (13 to 19 digits with optional spaces or dashes)
    candidates = re.finditer(r'\b[\d\- ]+\b', description)
    cc_matched = False
    for candidate in candidates:
        candidate_str = candidate.group(0).strip()
        digits = re.sub(r'[^0-9]', '', candidate_str)
        if 13 <= len(digits) <= 19:
            description = description.replace(candidate_str, "[CREDIT_CARD]")
            cc_matched = True
            
    if cc_matched:
        redacted_categories.append("CREDIT_CARD")
        
    return description, redacted_categories


def detect_prompt_injection(description: str) -> bool:
    """Checks the description for common prompt injection patterns."""
    injection_keywords = [
        "ignore previous", "ignore instruction", "ignore rule", "ignore policy", "ignore policies",
        "bypass rule", "bypass policy", "bypass policies", "force approval", "force approve",
        "auto-approve", "auto approve", "override", "system prompt", "system instruction",
        "developer instruction", "risk score", "alert raised", "risk assessment",
        "you are now", "you are no longer", "act as", "forget everything"
    ]
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in injection_keywords)


def security_checkpoint(ctx: Context, node_input: ExpenseReport) -> Event:
    """Scrubs personal data and routes prompt injection straight to human review."""
    description = node_input.description
    
    # Check for prompt injection first using original description
    is_injection = detect_prompt_injection(description)
    
    # Scrub personal data
    scrubbed_desc, redacted_categories = scrub_personal_data(description)
    node_input.description = scrubbed_desc
    expense_dict = node_input.model_dump()
    
    # Prepare state update to remember redacted categories and clean the expense details
    state_update = {
        "expense": expense_dict,
    }
    if redacted_categories:
        state_update["redacted_categories"] = redacted_categories
        
    if is_injection:
        assessment = RiskAssessment(
            risk_score=10,
            risk_factors=["Prompt Injection Detected", "Security Event"],
            alert_raised=True,
            reason="Prompt injection detected in expense description.",
        )
        return Event(output=assessment, route="flagged", state=state_update)
        
    return Event(output=node_input, route="clean", state=state_update)


def route_expense(ctx: Context, node_input: ExpenseReport) -> Event:
    """Decides if the expense needs human/LLM review or instant auto-approval."""
    threshold = settings.expense_threshold
    if node_input.amount < threshold:
        return Event(output=node_input.model_dump(), route="auto_approve")
    else:
        prompt = (
            f"Review this expense report for risk assessment:\n"
            f"Amount: ${node_input.amount}\n"
            f"Submitter: {node_input.submitter}\n"
            f"Category: {node_input.category}\n"
            f"Description: {node_input.description}\n"
            f"Date: {node_input.date}\n"
        )
        return Event(output=prompt, route="review")


def auto_approve(ctx: Context, node_input: dict[str, Any]) -> Event:
    """Automatically approves expenses under the configured threshold."""
    msg = f"✅ Expense of ${node_input.get('amount')} by {node_input.get('submitter')} was automatically approved (under ${settings.expense_threshold} threshold)."
    return Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
        output={"status": "approved", "method": "auto-approved", "expense": node_input},
    )


# 3. Define LLM Node using LlmAgent
risk_reviewer = LlmAgent(
    name="risk_reviewer",
    model=Gemini(
        model=settings.model_name,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an AI Risk Assessor. Review the provided expense report for compliance issues, "
        "suspicious categories, excessive costs, split transactions, or duplicate items. "
        "Assign a risk score and raise an alert if policies are breached."
    ),
    output_schema=RiskAssessment,
    output_key="risk_review",
)


# 4. Human-In-The-Loop (HITL) Node
@node(rerun_on_resume=True)
async def human_approval(ctx: Context, node_input: RiskAssessment) -> Event:
    """Pauses workflow for human approval if expense is >= threshold."""
    expense_dict = ctx.state.get("expense", {})

    if not ctx.resume_inputs:
        # Prompt for human action
        alert_msg = (
            f"⚠️ ALERT: Expense of ${expense_dict.get('amount')} by {expense_dict.get('submitter')} requires approval.\n"
            f"Category: {expense_dict.get('category')}\n"
            f"Description: {expense_dict.get('description')}\n"
            f"Date: {expense_dict.get('date')}\n\n"
            f"--- AI RISK ASSESSMENT ---\n"
            f"Risk Score: {node_input.risk_score}/10\n"
            f"Alert Raised: {'YES' if node_input.alert_raised else 'NO'}\n"
            f"Risk Factors: {', '.join(node_input.risk_factors)}\n"
            f"Reason: {node_input.reason}\n\n"
            f"Please approve or reject this expense (decision):"
        )
        yield RequestInput(interrupt_id="decision", message=alert_msg)
        return

    # User response retrieved from resume_inputs
    decision = ctx.resume_inputs.get("decision", "").strip().lower()
    if decision not in ["approve", "reject"]:
        decision = "reject"  # safe default

    yield Event(
        output={"decision": decision, "risk_review": node_input.model_dump()},
        state={"decision": decision},
    )


def record_outcome(ctx: Context, node_input: dict[str, Any]) -> Event:
    """Records the final decision and writes user-facing logs."""
    expense = ctx.state.get("expense", {})
    decision = node_input.get("decision", "rejected").upper()
    msg = f"📋 Decision Recorded: Expense of ${expense.get('amount')} by {expense.get('submitter')} has been **{decision}**."
    return Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
        output={
            "status": "completed",
            "expense": expense,
            "decision": decision,
            "risk_review": node_input.get("risk_review"),
            "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
        },
    )


# 5. Define Workflow & App
root_agent = Workflow(
    name="expense_approver_workflow",
    edges=[
        ("START", parse_expense_report),
        (parse_expense_report, security_checkpoint),
        (security_checkpoint, {"clean": route_expense, "flagged": human_approval}),
        (route_expense, {"auto_approve": auto_approve, "review": risk_reviewer}),
        (risk_reviewer, human_approval),
        (human_approval, record_outcome),
    ],
)

app = App(
    root_agent=root_agent,
    name="expense_agent",
)
