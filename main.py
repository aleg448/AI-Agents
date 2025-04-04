# main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
import uuid # For generating unique task IDs
import json # For serializing/deserializing Redis data

# Import agent classes
from agent_core import CybersecurityAgent, CodeGeneratorAgent

# Import Redis client functions
import redis_client as rc

# --- FastAPI Application Setup ---
app = FastAPI(title="Cybersecurity Agent Simulation Backend - Phase 2")

# --- Simulation State (Agent Objects & Statuses in Memory) ---
# Task Queue and Results Store now live in Redis
simulation_state = {
    "current_time": datetime.now().replace(minute=0, second=0, microsecond=0),
    "time_step_minutes": 1, # Shorter steps for more responsive queue processing
    "agents": {
        # --- Analyzer Agents ---
        "PyScanner": CybersecurityAgent(
            name="PyScanner",
            role_description="Analyze Python code snippets for common vulnerabilities (SQLi, XSS, Path Traversal, etc.)."
        ),
        "JavaScanner": CybersecurityAgent(
            name="JavaScanner",
            role_description="Analyze Java code snippets for common vulnerabilities, focusing on SQLi and insecure object handling."
        ),
        # --- Generator Agent ---
        "CodeGen": CodeGeneratorAgent(
            name="CodeGen"
        ),
    },
    # --- Agent Statuses (Managed in memory alongside objects) ---
    "agent_statuses": {
        "PyScanner": {"status": "idle", "current_task_id": None, "cooldown_steps": 0},
        "JavaScanner": {"status": "idle", "current_task_id": None, "cooldown_steps": 0},
        "CodeGen": {"status": "idle", "current_task_id": None, "cooldown_steps": 0},
    },
    "generator_cooldown": 2, # Steps the generator waits after generating code
    "analyzer_cooldown": 1, # Steps the analyzer waits after finishing analysis
}

# --- Simulation Step Logic ---
def run_simulation_step() -> Dict:
    """
    Runs one step of the simulation:
    - Generators create tasks and add to Redis queue.
    - Analyzers pick tasks from Redis queue, analyze, and store results in Redis.
    """
    current_time = simulation_state["current_time"]
    print(f"\n--- Simulation Step: {current_time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    step_events = [] # Log events during this step

    # --- 1. Update Cooldowns ---
    for name in simulation_state["agent_statuses"]:
        status_info = simulation_state["agent_statuses"][name]
        if status_info["cooldown_steps"] > 0:
            status_info["cooldown_steps"] -= 1
            if status_info["cooldown_steps"] == 0 and status_info["status"] == 'cooldown':
                 status_info["status"] = 'idle'
                 step_events.append(f"Agent {name} finished cooldown, now idle.")

    # --- 2. Process Generators ---
    for agent_name, agent in simulation_state["agents"].items():
        if isinstance(agent, CodeGeneratorAgent):
            status_info = simulation_state["agent_statuses"][agent_name]
            if status_info["status"] == 'idle':
                print(f"Triggering {agent_name} to generate code...")
                status_info["status"] = 'generating'
                generated_data = agent.perform_task(current_time=current_time)
                status_info["status"] = 'cooldown' # Go into cooldown regardless of success
                status_info["cooldown_steps"] = simulation_state["generator_cooldown"]

                if generated_data:
                    # Create a new task for the queue
                    new_task_id = str(uuid.uuid4())
                    new_task = {
                        'task_id': new_task_id,
                        'description': f"Analyze generated {generated_data.get('language','unknown')} code: {generated_data.get('description', 'N/A')}",
                        'context': generated_data.get('code', ''),
                        'language': generated_data.get('language', None),
                        'submitted_by': agent_name,
                        'status': 'pending',
                        'submitted_time': current_time.isoformat()
                    }
                    if rc.add_task_to_queue(new_task):
                        step_events.append(f"{agent_name} generated task {new_task_id} ({new_task['language']}) and added to queue.")
                    else:
                         step_events.append(f"{agent_name} failed to add generated task {new_task_id} to queue.")
                else:
                    step_events.append(f"{agent_name} failed to generate code.")
                # Set cooldown even on failure to prevent rapid retries
                status_info["status"] = 'cooldown'
                status_info["cooldown_steps"] = simulation_state["generator_cooldown"]

    # --- 3. Process Analyzers ---
    task_queue_length = rc.get_queue_length()
    print(f"DEBUG: Task queue length: {task_queue_length}")

    if task_queue_length > 0:
        for agent_name, agent in simulation_state["agents"].items():
            if isinstance(agent, CybersecurityAgent): # Only process analyzers here
                status_info = simulation_state["agent_statuses"][agent_name]
                # Check if agent is idle AND if there are tasks remaining in the queue
                if status_info["status"] == 'idle' and rc.get_queue_length() > 0:
                    print(f"Attempting to assign task to idle agent {agent_name}...")
                    task_data = rc.get_task_from_queue()

                    if task_data:
                        task_id = task_data['task_id']
                        print(f"Assigning task {task_id} to {agent_name}.")
                        status_info["status"] = 'analyzing'
                        status_info["current_task_id"] = task_id

                        # Perform the analysis
                        analysis_result = agent.perform_task(
                            task_description_specific=task_data['description'],
                            target_context=task_data['context'],
                            current_time=current_time
                        )

                        # Store the result in Redis
                        completion_time = datetime.now()
                        result_entry = {
                            'task_id': task_id,
                            'original_task': task_data, # Store original task details
                            'analysis_result': analysis_result,
                            'analyzed_by': agent_name,
                            'status': 'completed' if not analysis_result.startswith("Error:") else 'analysis_failed',
                            'completion_time': completion_time.isoformat()
                        }
                        rc.store_result(task_id, result_entry)

                        # Handle analysis errors (optional: add to failed queue)
                        if result_entry['status'] == 'analysis_failed':
                            step_events.append(f"Agent {agent_name} failed analysis for task {task_id}.")
                            rc.add_failed_task(task_data, analysis_result) # Log to failed queue
                        else:
                             step_events.append(f"Agent {agent_name} completed analysis for task {task_id}.")

                        # Reset agent state after processing
                        status_info["status"] = 'cooldown'
                        status_info["current_task_id"] = None
                        status_info["cooldown_steps"] = simulation_state["analyzer_cooldown"]

                    else:
                        # This case might happen if multiple agents tried to grab the last task concurrently
                        print(f"Agent {agent_name} found queue empty after check.")
                        break # No more tasks left

    # Advance Simulation Time
    simulation_state["current_time"] += timedelta(minutes=simulation_state["time_step_minutes"])

    # Return summary of the step
    return {
        "step_time": current_time.isoformat(),
        "next_time": simulation_state["current_time"].isoformat(),
        "queue_length": rc.get_queue_length(),
        "results_count": rc.get_results_count(),
        "step_events": step_events
    }

# --- API Endpoints ---
@app.on_event("startup")
async def startup_event():
    """Initialize Redis client on startup."""
    print("FastAPI startup: Initializing Redis client...")
    rc.get_redis_client() # Establish connection, will raise error if connection fails

@app.get("/")
def read_root():
    """ Basic endpoint to check if the server is running. """
    return {"message": "Cybersecurity Agent Simulation Backend (Phase 2) is running."}

@app.post("/step", summary="Run One Simulation Step")
def trigger_simulation_step():
    """ Triggers one simulation step and returns a summary of events. """
    try:
        step_summary = run_simulation_step()
        return step_summary
    except Exception as e:
         # Catch unexpected errors during step execution
         print(f"CRITICAL ERROR during simulation step: {e}")
         raise HTTPException(status_code=500, detail=f"Simulation step failed: {e}")


@app.get("/state", summary="Get Current Simulation State")
def get_current_state():
    """ Returns the current state including agent statuses and queue/result counts. """
    # Agent statuses are from in-memory state
    agent_statuses = simulation_state["agent_statuses"]
    return {
        "current_simulation_time": simulation_state["current_time"].isoformat(),
        "agent_statuses": agent_statuses,
        "task_queue_length": rc.get_queue_length(),
        "results_stored_count": rc.get_results_count(),
    }

@app.post("/submit_task", summary="Manually Submit a Task to the Queue")
def submit_task_to_queue(
    task_description: str = Body(...),
    context: str = Body(...),
    language: Optional[str] = Body(None)
):
    """ Adds a task manually to the Redis task queue. """
    new_task_id = str(uuid.uuid4())
    new_task = {
        'task_id': new_task_id,
        'description': task_description,
        'context': context,
        'language': language,
        'submitted_by': 'User',
        'status': 'pending',
        'submitted_time': datetime.now().isoformat()
    }
    if rc.add_task_to_queue(new_task):
        return {"message": "Task successfully submitted to queue.", "task_id": new_task_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to add task to Redis queue.")

@app.get("/tasks", summary="View Pending Tasks")
def get_pending_tasks(limit: int = 10):
    """ Retrieves the first 'limit' tasks from the pending queue. """
    tasks = rc.peek_tasks(limit)
    return {"pending_tasks": tasks, "count": len(tasks), "total_in_queue": rc.get_queue_length()}

@app.get("/results", summary="View Completed Results")
def get_completed_results(limit: int = 10):
    """ Retrieves the most recent 'limit' results from the results store. """
    results = rc.get_recent_results(limit)
    return {"recent_results": results, "count": len(results), "total_results": rc.get_results_count()}

@app.get("/results/{task_id}", summary="Get Specific Result by Task ID")
def get_single_result(task_id: str):
    """ Retrieves the result for a specific task ID. """
    result = rc.get_result(task_id)
    if result:
        return result
    else:
        raise HTTPException(status_code=404, detail=f"Result for task_id '{task_id}' not found.")


# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Cybersecurity Agent Backend (Phase 2)...")
    print(f"Attempting to connect to Redis at {rc.REDIS_HOST}:{rc.REDIS_PORT} DB {rc.REDIS_DB}")
    # The startup event handles the initial connection attempt
    print(f"Ensure LM Studio is running and serving model: {os.getenv('LLM_MODEL', 'instructlab/granite-7b-lab')}")
    print(f"LM Studio URL configured as: {os.getenv('LM_STUDIO_URL', 'http://localhost:1234/v1/chat/completions')}")
    uvicorn.run(app, host="0.0.0.0", port=8000)