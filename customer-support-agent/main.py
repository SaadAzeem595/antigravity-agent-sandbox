import asyncio
import os
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import root_agent

# Ensure API key is loaded
if not os.environ.get("GOOGLE_API_KEY"):
    print("Warning: GOOGLE_API_KEY environment variable is not set. Please set it in your shell or .env file.")

async def run_chat(query: str):
    # Initialize the Runner with InMemorySessionService for local testing
    runner = Runner(
        node=root_agent,
        session_service=InMemorySessionService(),
        app_name="customer-support-agent",
        auto_create_session=True,
    )
    
    # Create the new user message content
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=query)]
    )
    
    print(f"\nUser Query: {query}")
    print("Agent Response: ", end="", flush=True)
    
    # Run the workflow agent
    async for event in runner.run_async(
        user_id="test_user",
        session_id="test_session",
        new_message=new_message,
    ):
        # Print the text content of model events
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
        # Or if it's a function output / direct value output
        elif event.output:
            print(event.output, end="", flush=True)
    print("\n" + "-" * 40)

async def main():
    # Test a shipping-related query
    await run_chat("How can I track my package with order number 12345?")
    
    # Test an unrelated query
    await run_chat("What is the capital of France?")

if __name__ == "__main__":
    asyncio.run(main())
