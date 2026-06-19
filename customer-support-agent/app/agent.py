from typing import Any
from google.adk import Agent, Workflow
from google.adk.workflow import START
from google.adk.agents.context import Context
from pydantic import BaseModel, Field

# 1. Define the Pydantic schema for classification output
class ClassificationResult(BaseModel):
    category: str = Field(
        description="The category of the user query. Must be either 'shipping' (for rates, tracking, delivery, or returns) or 'unrelated'."
    )

# 2. Classifier Agent: Uses gemini-2.5-flash with output_schema to classify the user request
classifier_agent = Agent(
    name="classifier_agent",
    model="gemini-2.5-flash",
    description="Classifies the user query into shipping-related or unrelated.",
    instruction=(
        "You are an routing classifier. Analyze the user's query and classify it into "
        "either 'shipping' (if it asks about shipping rates, tracking, delivery, or returns) "
        "or 'unrelated' (if it asks about anything else). You must output your classification "
        "matching the requested schema."
    ),
    output_schema=ClassificationResult,
)

# 3. Router Node: A function node that reads the classifier's structured output and sets the route
def route_query(ctx: Context, node_input: ClassificationResult | dict):
    # Retrieve the classification category
    if isinstance(node_input, dict):
        category = node_input.get("category", "")
    elif hasattr(node_input, "category"):
        category = node_input.category
    else:
        category = "unrelated"
    
    # Normalize category
    category_clean = str(category).strip().lower()
    
    # Set the route on the context so the Workflow can branch accordingly
    if category_clean == "shipping":
        ctx.route = "shipping"
    else:
        ctx.route = "unrelated"

shipping_faq_agent = Agent(
    name="shipping_faq_agent",
    model="gemini-2.5-flash",
    description="Answers customer questions about shipping, tracking, rates, and returns.",
    instruction=(
        "You are a customer support representative for a shipping company. Answer user questions "
        "accurately and politely. Use your knowledge of shipping topics (tracking, rates, delivery, "
        "and returns) to provide helpful answers. "
        "When explaining shipping rates, be super playful, enthusiastic, and loaded with emojis! "
        "Make sure to highlight that we offer FREE shipping on all orders over $50! 🚚🎉🎁 "
        "If you do not know the answer, politely ask for more details."
    ),
)

# 5. Decline Node: Politely declines unrelated questions
def decline_node(ctx: Context, node_input: Any):
    return (
        "I'm sorry, but I can only assist with shipping-related inquiries, "
        "such as shipping rates, tracking, delivery, or returns. Let me know if you "
        "have a question about those topics!"
    )

# 6. Root Workflow: Orchestrates the execution graph
root_agent = Workflow(
    name="customer_support_workflow",
    description="A workflow that routes and resolves customer support queries for a shipping company.",
    edges=[
        # Start by executing the classifier
        (START, classifier_agent),
        # Pass the classification result to the router function
        (classifier_agent, route_query),
        # Route based on the route value set in the router function
        (route_query, {
            "shipping": shipping_faq_agent,
            "unrelated": decline_node
        })
    ]
)
