# agent_core.py
import random
import os
from datetime import datetime
from dotenv import load_dotenv

# --- LangChain & LLM Imports ---
from langchain_community.chat_models import ChatLiteLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

# --- Load Environment Variables ---
# Load variables from .env file (especially API keys or model configs for LiteLLM)
load_dotenv()

# --- Initialize LLM ---
# Uses LiteLLM to connect to various LLM providers or local models.
# Ensure your environment is configured correctly for the desired model.
# Example: Using a local Llama 3 model served via Ollama.
# Make sure Ollama is running and has the llama3 model pulled.
try:
    # Ensure LiteLLM can find your Ollama instance (usually localhost:11434)
    # You might need to set OLLAMA_API_BASE_URL in your .env if it's different
    llm = ChatLiteLLM(model="ollama/llama3", temperature=0.7)
    # For OpenAI, it would be: llm = ChatLiteLLM(model="gpt-3.5-turbo")
except Exception as e:
    print(f"Error initializing LLM: {e}")
    print("Please ensure your LLM provider (e.g., Ollama) is running and configured correctly.")
    print("Or set appropriate API keys in the .env file.")
    # Fallback to basic logic if LLM fails
    llm = None

# --- Memory Placeholders ---
# Replace these with actual ChromaDB interactions later
def retrieve_memories(agent_name: str, observation: str, k: int = 5) -> list[str]:
    """
    Placeholder for retrieving relevant memories for the agent.
    Should query ChromaDB based on the observation embedding.
    """
    print(f"DEBUG: Retrieving memories for {agent_name} based on '{observation}' (placeholder).")
    # Simulating retrieval - replace with actual vector search
    # relevant_memories = vector_db.similarity_search(observation, k=k)
    # return [mem.page_content for mem in relevant_memories]
    return ["Memory: Started the day feeling motivated.", "Memory: Had coffee earlier."] # Example fixed memories

def store_memory(agent_name: str, memory_entry: str):
    """
    Placeholder for storing a new memory for the agent in ChromaDB.
    """
    print(f"DEBUG: Storing memory for {agent_name}: '{memory_entry}' (placeholder).")
    # vector_db.add_texts([memory_entry], metadatas=[{"agent": agent_name, "timestamp": datetime.now()}])
    pass

# --- Agent Core Logic ---
def get_agent_action(agent_name: str, agent_goal: str, current_time: datetime, observation: str) -> str:
    """
    Determines the next action for an agent using an LLM via LangChain.

    Args:
        agent_name: The name of the agent.
        agent_goal: The high-level goal of the agent.
        current_time: The current simulation time.
        observation: A string describing the agent's current observation.

    Returns:
        A string describing the agent's chosen action.
    """
    time_str = current_time.strftime("%Y-%m-%d %H:%M")
    action = f"idle due to error or LLM not available ({observation})" # Default action

    if not llm: # Check if LLM initialization failed
        print(f"[{time_str}] {agent_name} falling back to basic logic.")
        # Basic fallback (can refine this)
        hour = current_time.hour
        if 8 <= hour < 17:
            action = random.choice(["doing something productive", "thinking", "observing"])
        else:
            action = random.choice(["resting", "sleeping", "wandering"])
        print(f"[{time_str}] {agent_name} decided to: {action} (fallback)")
        return action

    # 1. Retrieve relevant memories (using placeholder)
    relevant_memories = retrieve_memories(agent_name, observation)
    memory_str = "\n".join(f"- {mem}" for mem in relevant_memories) if relevant_memories else "No relevant memories found."

    # 2. Define the prompt template
    # This prompt guides the LLM's decision-making process.
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """You are an AI agent simulating a person named {agent_name}.
Your core goal is: {agent_goal}.
You exist in a simulated world. You need to decide your next action based on your current situation and memories.
Current time: {time_str}.
Your recent relevant memories:
{memory_str}

Based on this information and your goal, decide on a **single, specific, short action** you will take right now. Be concise and describe the action directly (e.g., "drink coffee", "write chapter 3", "go for a run in the park", "check email"). Do not narrate or explain your reasoning, just state the action."""),
        ("human", "Current observation: {observation}\nWhat is your next action?")
    ])

    # 3. Create the chain: Prompt -> LLM -> Output Parser
    chain = prompt_template | llm | StrOutputParser()

    # 4. Invoke the chain with agent-specific data
    try:
        print(f"DEBUG: Invoking LLM for {agent_name}...")
        action = chain.invoke({
            "agent_name": agent_name,
            "agent_goal": agent_goal,
            "time_str": time_str,
            "memory_str": memory_str,
            "observation": observation,
        })
        action = action.strip() # Clean up whitespace
        print(f"[{time_str}] {agent_name} decided to: {action} (via LLM)")

        # 5. Store memory of observation and action (using placeholder)
        memory_entry = f"At {time_str}, I observed '{observation}' and decided to '{action}'."
        store_memory(agent_name, memory_entry)

    except Exception as e:
        print(f"Error during LLM invocation for {agent_name}: {e}")
        # Fallback action if LLM fails
        action = f"pondering the situation ({observation}) after an error"
        print(f"[{time_str}] {agent_name} decided to: {action} (fallback due to error)")


    return action