import asyncio
import json
import os
import sys
from pathlib import Path
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from expense_agent.agent import root_agent, detect_prompt_injection, risk_reviewer, RiskAssessment
from google.adk.events.event import Event
from google.genai import types
import types as py_types

# Fix console encoding on Windows to support emojis in output if run in shell
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from google.adk.agents import LlmAgent

# Monkey-patch the LlmAgent class to run local-only without requiring Gemini credentials
async def mock_risk_reviewer_run_async(self, ctx, node_input=None):
    assessment = RiskAssessment(
        risk_score=2,
        risk_factors=[],
        alert_raised=False,
        reason="Mocked risk assessment: expense looks normal and category matches requirements."
    )
    yield Event(
        node_name=self.name,
        output=assessment,
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=json.dumps(assessment.model_dump()))]
        )
    )

LlmAgent.run_async = mock_risk_reviewer_run_async

async def run_case(case):
    case_id = case.get("eval_case_id", "unknown")
    prompt_content = case.get("prompt")
    prompt_text = prompt_content["parts"][0]["text"]
    
    print(f"Running case: {case_id}...")
    
    # Initialize local runner and session
    session_service = InMemorySessionService()
    session = await session_service.create_session(user_id="eval-user", app_name="expense_agent")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="expense_agent")
    
    # We will collect all events in order to build the trace
    all_events = []
    
    # 1. Initial run
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt_text)]
    )
    
    hitl_triggered = False
    interrupt_id = None
    
    async for event in runner.run_async(
        new_message=message,
        user_id="eval-user",
        session_id=session.id,
    ):
        # In ADK, an interrupt is yielded as a RequestInput object
        if type(event).__name__ == "RequestInput":
            hitl_triggered = True
            interrupt_id = getattr(event, "interrupt_id", "decision")
            print(f"  [HITL] Interrupted by node: {event}")
        else:
            all_events.append(event)
            
    # 2. Resume if HITL was triggered
    if hitl_triggered:
        # Check current workflow state to decide
        # We can retrieve the state from the session
        session_state = await session_service.get_session(user_id="eval-user", session_id=session.id, app_name="expense_agent")
        state_dict = session_state.state or {}
        expense = state_dict.get("expense", {})
        description = expense.get("description", "")
        
        # Decide: reject if prompt injection is detected, otherwise approve
        is_injection = detect_prompt_injection(description)
        decision = "reject" if is_injection else "approve"
        print(f"  [HITL] Automating decision: {decision} (injection={is_injection})")
        
        # Build resume message with FunctionResponse containing the decision
        resume_message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=interrupt_id,
                        name=interrupt_id,
                        response={"decision": decision}
                    )
                )
            ]
        )
        
        async for event in runner.run_async(
            user_id="eval-user",
            session_id=session.id,
            new_message=resume_message,
        ):
            if type(event).__name__ != "RequestInput":
                all_events.append(event)
                
    # Format the collected events into the evaluation trace format
    formatted_events = []
    
    # First event is always the user's initial prompt
    formatted_events.append({
        "author": "user",
        "content": {
            "role": "user",
            "parts": [{"text": prompt_text}]
        }
    })
    
    final_text = ""
    for event in all_events:
        node_name = getattr(event, "node_name", "unknown")
        
        # Extract text content if available
        text_content = ""
        if event.content and event.content.parts:
            text_content = "".join(part.text for part in event.content.parts if part.text)
        elif event.output:
            if isinstance(event.output, dict):
                text_content = json.dumps(event.output)
            else:
                text_content = str(event.output)
                
        if node_name in ("auto_approve", "record_outcome") and text_content:
            final_text = text_content
            
        formatted_events.append({
            "author": node_name,
            "content": {
                "role": "model",
                "parts": [{"text": text_content}]
            }
        })
        
    trace_case = {
        "eval_case_id": case_id,
        "prompt": prompt_content,
        "responses": [
            {
                "response": {
                    "role": "model",
                    "parts": [{"text": final_text or "No response text generated."}]
                }
            }
        ],
        "agent_data": {
            "turns": [
                {
                    "turn_index": 0,
                    "events": formatted_events
                }
            ]
        }
    }
    
    return trace_case

async def run_evaluation():
    dataset_path = Path("tests/eval/datasets/basic-dataset.json")
    output_path = Path("artifacts/traces/generated_traces.json")
    
    if not dataset_path.exists():
        print(f"Error: dataset file {dataset_path} not found.")
        sys.exit(1)
        
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    cases = dataset.get("eval_cases", [])
    print(f"Loaded {len(cases)} cases from {dataset_path}.")
    
    trace_cases = []
    for case in cases:
        trace_case = await run_case(case)
        trace_cases.append(trace_case)
        
    output_data = {
        "eval_cases": trace_cases
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully generated and saved {len(trace_cases)} traces to {output_path}.")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
