import litellm
import uvicorn
from fastapi import FastAPI
from datetime import datetime, timedelta
from typing import Dict, List
import os
litellm._turn_on_debug()
# Import the agent logic
from agent_core import Agent, get_agent_action  # Import the Agent class
# --- FastAPI Application Setup ---
app = FastAPI(title="AI Agent Simulation Backend")
# --- Simulation State (In-Memory - Replace with Redis later) ---
# For simplicity, we store the state in memory.
# In a real application, use Redis for scalability and persistence.
simulation_state = {
    "current_time": datetime.now().replace(hour=7, minute=0, second=0, microsecond=0),
    "time_step_minutes": 15,  # How much time passes each step
    "agents": {
        "Alice": Agent(  # Create Agent object
            name="Alice",
            goal="write a novel and live a balanced life",
            location="Home Office",
            current_action="Waking up",
            stats={
                "money": 100,
                "hunger": 100,
                "energy": 100,
                "body_care": 100,
                "happiness": 100,
            },
            achieved_goals=[],
        ),
        "Bob": Agent(  # Create Agent object
            name="Bob",
            goal="prepare for a marathon and excel at work",
            location="Kitchen",
            current_action="Making coffee",
            stats={
                "money": 150,
                "hunger": 100,
                "energy": 100,
                "body_care": 100,
                "happiness": 100,
            },
            achieved_goals=[],
        ),
    },
    "locations": {
        "Home Office": {"occupants": ["Alice"]},
        "Kitchen": {"occupants": ["Bob"]},
        "Park": {"occupants": []},
        "Gym": {"occupants": []},
        "Library": {"occupants": []},
        "Workplace": {"occupants": []},
    },
}
# --- Helper Functions ---
def get_observation(agent_name: str) -> str:
    """
    Generates a simple observation string for the agent.
    """
    agent = simulation_state["agents"].get(agent_name)  # Get Agent object
    if not agent:
        return "Observing the void."
    location = agent.location
    occupants = simulation_state["locations"].get(location, {}).get("occupants", [])
    other_occupants = [name for name in occupants if name != agent.name]
    observation = f"Currently at {location}."
    if other_occupants:
        observation += f" Sees: {', '.join(other_occupants)}."
    else:
        observation += " It's quiet here."
    # Add time context
    time_str = simulation_state["current_time"].strftime("%H:%M")
    observation += f" The time is {time_str}."
    return observation
# --- Simulation Step Logic ---
def run_simulation_step() -> Dict:  # Specify return type for clarity
    """
    Runs one step of the simulation.
    """
    current_time = simulation_state["current_time"]
    print(f"\n--- Simulation Step: {current_time.strftime('%Y-%m-%d %H:%M')} ---")
    # Process each agent
    for agent_name, agent in simulation_state["agents"].items():  # Iterate through Agent objects
        # 1. Get Observation (Simplified)
        observation = get_observation(agent_name)
        # 2. Get Action from Agent Core (using LLM)
        action = get_agent_action(
            agent=agent,  # Pass the Agent object
            observation=observation,
            current_time=current_time,
        )
        # 3. Update Agent State
        agent.current_action = action  # Update with *only* the LLM's action
    # Advance Simulation Time
    simulation_state["current_time"] += timedelta(minutes=simulation_state["time_step_minutes"])
    # Return current state
    return {
        "current_time": simulation_state["current_time"].isoformat(),
        "agents": {
            agent_name: {
                "name": agent.name,
                "goal": agent.goal,
                "location": agent.location,
                "current_action": agent.current_action,
                "stats": agent.stats,
                "achieved_goals": agent.achieved_goals,
            }
            for agent_name, agent in simulation_state["agents"].items()
        },
    }
# --- API Endpoints ---
@app.get("/")
def read_root():
    """ Basic endpoint to check if the server is running. """
    return {"message": "AI Agent Simulation Backend is running."}
@app.post("/step")
def trigger_simulation_step():
    """ Triggers one step of the simulation and returns the updated state. """
    updated_state = run_simulation_step()
    return updated_state
@app.get("/state")
def get_current_state():
    """ Returns the current state of the simulation. """
    # Make sure time is serializable
    state_copy = simulation_state.copy()
    state_copy["current_time"] = state_copy["current_time"].isoformat()
    state_copy["agents"] = {
        agent_name: {
            "name": agent.name,
            "goal": agent.goal,
            "location": agent.location,
            "current_action": agent.current_action,
            "stats": agent.stats,
            "achieved_goals": agent.achieved_goals,
        }
        for agent_name, agent in state_copy["agents"].items()
    }
    return state_copy
# --- Main Execution ---
if __name__ == "__main__":
    # Run the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)