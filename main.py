import uvicorn
from fastapi import FastAPI
from datetime import datetime, timedelta
import random

# Import the agent logic
from agent_core import get_agent_action

# --- FastAPI Application Setup ---
app = FastAPI(title="AI Agent Simulation Backend")

# --- Simulation State (In-Memory - Replace with Redis later) ---
# For simplicity, we store the state in memory.
# In a real application, use Redis for scalability and persistence.
simulation_state = {
    "current_time": datetime.now().replace(hour=7, minute=0, second=0, microsecond=0),
    "time_step_minutes": 15,  # How much time passes each step
    "agents": {
        "Alice": {
            "name": "Alice",
            "goal": "write a novel and live a balanced life",
            "location": "Home Office",  # Simplified state
            "current_action": "Waking up",
        },
        "Bob": {
            "name": "Bob",
            "goal": "prepare for a marathon and excel at work",
            "location": "Kitchen",  # Simplified state
            "current_action": "Making coffee",
        },
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
    In a real simulation, this would be much more complex, based on
    location, other agents present, objects, etc.
    """
    agent_info = simulation_state["agents"].get(agent_name)
    if not agent_info:
        return "Observing the void."

    location = agent_info["location"]
    occupants = simulation_state["locations"].get(location, {}).get("occupants", [])
    other_occupants = [name for name in occupants if name != agent_name]

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
def run_simulation_step():
    """
    Runs one step of the simulation.
    """
    current_time = simulation_state["current_time"]
    print(f"\n--- Simulation Step: {current_time.strftime('%Y-%m-%d %H:%M')} ---")

    # Process each agent
    for agent_name, agent_data in simulation_state["agents"].items():
        # 1. Get Observation (Simplified)
        observation = get_observation(agent_name)

        # 2. Get Action from Agent Core (using placeholder logic for now)
        action = get_agent_action(
            agent=simulation_state["agents"][agent_name],  # Pass the agent *object*
            observation=observation,
            current_time=current_time,
        )

        # 3. Update Agent State (Simplified)
        # In a real simulation, the action would be parsed, and state changes
        # (like location) would be applied based on the action.
        # For now, just store the action description.
        simulation_state["agents"][agent_name]["current_action"] = action

        # Placeholder for updating location based on action (e.g., if action is "go to park")
        # update_agent_location(agent_name, action)

    # Advance Simulation Time
    simulation_state["current_time"] += timedelta(minutes=simulation_state["time_step_minutes"])

    # Return current state (optional, useful for API response)
    return {
        "current_time": simulation_state["current_time"].isoformat(),
        "agents": simulation_state["agents"],
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
    return state_copy


# --- Main Execution ---
if __name__ == "__main__":
    # We can run a few steps automatically on startup for testing
    # print("Running initial simulation steps...")
    # for _ in range(3): # Run 3 steps
    #  run_simulation_step()
    # print("\nStarting FastAPI server...")

    # Run the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)