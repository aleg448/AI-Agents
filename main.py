# main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
import uuid
import json

# Import agent classes
from agent_core import CybersecurityAgent, CodeGeneratorAgent
import mongodb_client as rc

app = FastAPI(title="Cybersecurity Agent Simulation Backend - Phase 2 (MongoDB)")

simulation_state = {
    "current_time": datetime.now().replace(minute=0, second=0, microsecond=0),
    "time_step_minutes": 1,
    "agents": {
        "PyScanner": CybersecurityAgent(
            name="PyScanner",
            role_description="Analyze Python code snippets for common vulnerabilities (SQLi, XSS, Path Traversal, etc.)."
        ),
        "JavaScanner": CybersecurityAgent(
            name="JavaScanner",
            role_description="Analyze Java code snippets for common vulnerabilities, focusing on SQLi and insecure object handling."
        ),
        "CodeGen": CodeGeneratorAgent(name="CodeGen"),
    },
    "agent_statuses": {
        "PyScanner": {"status": "idle", "current_task_id": None, "cooldown_steps": 0},
        "JavaScanner": {"status": "idle", "current_task_id": None, "cooldown_steps": 0},
        "CodeGen": {"status": "idle", "current_task_id": None, "cooldown_steps": 0},
    },
    "generator_cooldown": 2,
    "analyzer_cooldown": 1,
}

def run_simulation_step() -> Dict:
    current_time = simulation_state["current_time"]
    print(f"\n--- Simulation Step: {current_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    step_events = []

    # Update cooldowns
    for name in simulation_state["agent_statuses"]:
        status_info = simulation_state["agent_statuses"][name]
        if status_info["cooldown_steps"] > 0:
            status_info["cooldown_steps"] -= 1
            if status_info["cooldown_steps"] == 0 and status_info["status"] == 'cooldown':
                status_info["status"] = 'idle'
                step_events.append(f"Agent {name} finished cooldown, now idle.")

    # Process Code Generator (CodeGen)
    for agent_name, agent in simulation_state["agents"].items():
        if isinstance(agent, CodeGeneratorAgent):
            status_info = simulation_state["agent_statuses"][agent_name]
            if status_info["status"] == 'idle':
                print(f"Triggering {agent_name} to generate code...")
                status_info["status"] = 'generating'
                generated_data = agent.perform_task(current_time=current_time)
                status_info["status"] = 'cooldown'
                status_info["cooldown_steps"] = simulation_state["generator_cooldown"]

                if generated_data:
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

                status_info["status"] = 'cooldown'
                status_info["cooldown_steps"] = simulation_state["generator_cooldown"]

    # Process Analyzer Agents (e.g., PyScanner)
    task_queue_length = rc.get_queue_length()
    print(f"DEBUG: Task queue length: {task_queue_length}")
    if task_queue_length > 0:
        for agent_name, agent in simulation_state["agents"].items():
            if isinstance(agent, CybersecurityAgent):
                status_info = simulation_state["agent_statuses"][agent_name]
                if status_info["status"] == 'idle' and rc.get_queue_length() > 0:
                    print(f"Attempting to assign task to idle agent {agent_name}...")
                    task_data = rc.get_task_from_queue()
                    if task_data:
                        task_id = task_data['task_id']
                        print(f"Assigning task {task_id} to {agent_name}.")
                        status_info["status"] = 'analyzing'
                        status_info["current_task_id"] = task_id

                        analysis_result = agent.perform_task(
                            task_description_specific=task_data['description'],
                            target_context=task_data['context'],
                            current_time=current_time
                        )
                        completion_time = datetime.now()
                        result_entry = {
                            'task_id': task_id,
                            'original_task': task_data,
                            'analysis_result': analysis_result,
                            'analyzed_by': agent_name,
                            'status': 'completed' if not analysis_result.startswith("Error:") else 'analysis_failed',
                            'completion_time': completion_time.isoformat()
                        }
                        rc.store_result(task_id, result_entry)

                        if result_entry['status'] == 'analysis_failed':
                            step_events.append(f"Agent {agent_name} failed analysis for task {task_id}.")
                            rc.add_failed_task(task_data, analysis_result)
                        else:
                            step_events.append(f"Agent {agent_name} completed analysis for task {task_id}.")

                        status_info["status"] = 'cooldown'
                        status_info["current_task_id"] = None
                        status_info["cooldown_steps"] = simulation_state["analyzer_cooldown"]
                    else:
                        print(f"Agent {agent_name} found queue empty after check.")
                        break

    simulation_state["current_time"] += timedelta(minutes=simulation_state["time_step_minutes"])
    return {
        "step_time": current_time.isoformat(),
        "next_time": simulation_state["current_time"].isoformat(),
        "queue_length": rc.get_queue_length(),
        "results_count": rc.get_results_count(),
        "step_events": step_events
    }

@app.on_event("startup")
async def startup_event():
    print("FastAPI startup: Checking MongoDB connection...")
    try:
        rc.client.admin.command('ping')
        print("Successfully connected to MongoDB.")
    except Exception as e:
        print(f"ERROR: Could not connect to MongoDB: {e}")
        raise e

@app.get("/")
def read_root():
    return {"message": "Cybersecurity Agent Simulation Backend (Phase 2) with MongoDB is running."}

@app.post("/step", summary="Run One Simulation Step")
def trigger_simulation_step():
    try:
        step_summary = run_simulation_step()
        return step_summary
    except Exception as e:
        print(f"CRITICAL ERROR during simulation step: {e}")
        raise HTTPException(status_code=500, detail=f"Simulation step failed: {e}")

@app.get("/state", summary="Get Current Simulation State")
def get_current_state():
    agent_statuses = simulation_state["agent_statuses"]
    chat_history = {
        "CodeGen": simulation_state["agents"]["CodeGen"].memories,
        "PyScanner": simulation_state["agents"]["PyScanner"].memories,
    }
    return {
        "current_simulation_time": simulation_state["current_time"].isoformat(),
        "agent_statuses": agent_statuses,
        "task_queue_length": rc.get_queue_length(),
        "results_stored_count": rc.get_results_count(),
        "chat_history": chat_history
    }

@app.post("/submit_task", summary="Manually Submit a Task to the Queue")
def submit_task_to_queue(
    task_description: str = Body(...),
    context: str = Body(...),
    language: Optional[str] = Body(None)
):
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
        raise HTTPException(status_code=500, detail="Failed to add task to MongoDB queue.")

@app.get("/tasks", summary="View Pending Tasks")
def get_pending_tasks(limit: int = 10):
    tasks = rc.peek_tasks(limit)
    return {"pending_tasks": tasks, "count": len(tasks), "total_in_queue": rc.get_queue_length()}

@app.get("/results", summary="View Completed Results")
def get_completed_results(limit: int = 10):
    results = rc.get_recent_results(limit)
    return {"recent_results": results, "count": len(results), "total_results": rc.get_results_count()}

@app.get("/results/{task_id}", summary="Get Specific Result by Task ID")
def get_single_result(task_id: str):
    result = rc.get_result(task_id)
    if result:
        return result
    else:
        raise HTTPException(status_code=404, detail=f"Result for task_id '{task_id}' not found.")

if __name__ == "__main__":
    print("Starting Cybersecurity Agent Backend (Phase 2) with MongoDB...")
    print(f"Ensure LM Studio is running and serving model: {os.getenv('LLM_MODEL', 'instructlab/granite-7b-lab')}")
    print(f"LM Studio URL configured as: {os.getenv('LM_STUDIO_URL', 'http://localhost:1234/v1/chat/completions')}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
