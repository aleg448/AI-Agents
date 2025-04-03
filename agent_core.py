import litellm
import random
import os
from datetime import datetime
from dotenv import load_dotenv

# --- LangChain & LLM Imports ---
from langchain_community.chat_models import ChatLiteLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

litellm._turn_on_debug()
# --- Load Environment Variables ---
# Load variables from .env file (especially API keys or model configs for LiteLLM)
load_dotenv()
litellm.api_base = os.getenv("LM_STUDIO_API_BASE") + "/chat/completions"
llm = None  # Initialize llm *outside* the try block

# --- Initialize LLM and Direct Test---
try:
    response = litellm.completion(
        model=os.getenv("LITELLM_MODEL"),
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},  # Use dict format
            {"role": "user", "content": "What is the capital of France?"},  # Use dict format
        ],
        custom_llm_provider="lm_studio",
        temperature=0.7,
    )
    print(f"DEBUG: LiteLLM Response: {response}")
    action = response.choices[0].message.content
    llm = ChatLiteLLM(
        model=os.getenv("LITELLM_MODEL"),
        api_base=os.getenv("LM_STUDIO_API_BASE"),
        temperature=0.7,
        custom_llm_provider="lm_studio",
    )
except Exception as e:
    print(f"ERROR: LiteLLM Direct Test Failed: {e}")
    action = "Error"
    llm = None


# --- Agent Class ---
class Agent:
    def __init__(self, name, goal, memories=None):
        self.name = name
        self.goal = goal
        self.memories = memories if memories is not None else []

    def get_memories(self, observation):
        # Placeholder for memory retrieval logic
        return self.memories

    def add_memory(self, memory):
        self.memories.append(memory)

# --- Action Selection Function ---
def get_agent_action(agent, observation, current_time):
    """
    Determines the next action for an agent based on the current observation,
    recent memories, and the agent's goal.  Uses an LLM to generate the action.

    Args:
        agent (Agent): The agent for whom to determine the action.
        observation (str): The agent's current observation of the environment.
        current_time (str): The current time in the simulation.

    Returns:
        str: The action the agent will take.
    """
    # 1. Get relevant memories
    relevant_memories = agent.get_memories(observation)

    # 2. Construct the prompt
    system_prompt = f"""You are an AI agent simulating a person named {agent.name}.
Your core goal is: {agent.goal}.
You exist in a simulated world. You need to decide your next action based on your current situation and memories.
Current time: {current_time}.
Your recent relevant memories:
{relevant_memories}

Based on this information and your goal, decide on a **single, specific, short action** you will take right now. Be concise and describe the action directly (e.g., "drink coffee", "write chapter 3", "go for a run in the park", "check email"). Do not narrate or explain your reasoning, just state the action."""

    prompt_template = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Current observation: {observation}\nWhat is your next action?"),
        ]
    )
    if llm is not None: # check if llm is initialized
        chain = prompt_template | llm | StrOutputParser()
        action = chain.invoke({})
    else:
        action = f"{random.choice(['resting', 'wandering', 'thinking'])} (fallback)"
    print(f"[{current_time}] {agent.name} decided to: {action}")
    agent.add_memory(f"Memory: {action}")
    return action
