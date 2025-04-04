# main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os

# Import the refactored agent class
from agent_core import CybersecurityAgent

# --- FastAPI Application Setup ---
app = FastAPI(title="Cybersecurity Agent Simulation Backend")

# --- Example Code Snippets for Testing ---
EXAMPLE_PYTHON_CODE = """
import os

def get_user_data(user_id):
    # Simulate fetching data - Potential for insecurity if user_id is injectable
    query = "SELECT * FROM users WHERE id = '" + user_id + "'"
    print(f"Executing query: {query}")
    # In a real app, database connection and execution would happen here
    # db.execute(query)
    return {"id": user_id, "name": "Sample User"}

def process_file(filename):
    # Potential path traversal if filename is user-controlled
    full_path = "/data/files/" + filename
    if os.path.exists(full_path):
        with open(full_path, 'r') as f:
            return f.read()
    return None
"""

EXAMPLE_JAVA_CODE = """
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class UserDAO {
    public String getUserInfo(String userId) {
        String userInfo = "";
        try {
            Connection conn = DriverManager.getConnection("jdbc:mysql://localhost:3306/mydb", "user", "password");
            Statement stmt = conn.createStatement();
            // Vulnerable to SQL Injection
            String query = "SELECT name, email FROM user_accounts WHERE user_id = '" + userId + "'";
            System.out.println("Executing: " + query);
            ResultSet rs = stmt.executeQuery(query);
            if (rs.next()) {
                userInfo = "Name: " + rs.getString("name") + ", Email: " + rs.getString("email");
            }
            conn.close();
        } catch (Exception e) {
            e.printStackTrace();
        }
        return userInfo;
    }
}
"""

# --- Simulation State (In-Memory) ---
simulation_state = {
    "current_time": datetime.now().replace(minute=0, second=0, microsecond=0),
    "time_step_minutes": 60, # Longer steps might make sense for analysis tasks
    "agents": {
        "CodeScannerAgent": CybersecurityAgent(
            name="CodeScannerAgent",
            task_description="Analyze Python code snippets for common vulnerabilities like SQL injection, path traversal, and insecure deserialization.",
            target_context=EXAMPLE_PYTHON_CODE
        ),
        "JavaRefactorAgent": CybersecurityAgent(
            name="JavaRefactorAgent",
            task_description="Analyze Java code for SQL injection vulnerabilities and suggest refactored code to mitigate them using PreparedStatement.",
            target_context=EXAMPLE_JAVA_CODE
        )
    }
    # 'locations' dictionary removed
}

# --- Helper Functions ---
def get_agent_context(agent_name: str) -> Optional[str]:
    """ Gets the target context for the specified agent. """
    agent = simulation_state["agents"].get(agent_name)
    if agent:
        return agent.target_context
    return None

# --- Simulation Step Logic ---
def run_simulation_step() -> Dict:
    """
    Runs one step of the simulation, triggering each agent's task.
    """
    current_time = simulation_state["current_time"]
    print(f"\n--- Simulation Step: {current_time.strftime('%Y-%m-%d %H:%M')} ---")

    results = {} # Store results for this step

    # Process each agent
    for agent_name, agent in simulation_state["agents"].items():
        print(f"\nProcessing Agent: {agent_name} (Task: {agent.task_description})")
        context = agent.target_context # Use the agent's current context

        if not context:
            print(f"Agent {agent_name} has no target context. Skipping.")
            agent.current_action = "Idle - No context"
            results[agent_name] = {"status": "skipped", "reason": "No context"}
            continue

        # 2. Perform Task using Agent Core (LLM call)
        analysis_result = agent.perform_task(current_time=current_time)

        # 3. Update Agent State
        agent.current_action = f"Completed analysis at {current_time.strftime('%H:%M')}"
        agent.findings.append(f"[{current_time.strftime('%H:%M')}] Analysis Result:\n{analysis_result}\n" + "-"*20) # Store the full finding
        print(f"Agent {agent_name} Result:\n{analysis_result}")
        results[agent_name] = {"status": "completed", "result_preview": analysis_result[:200] + "..."}


    # Advance Simulation Time
    simulation_state["current_time"] += timedelta(minutes=simulation_state["time_step_minutes"])

    # Return summary of the step results
    return {
        "step_time": current_time.isoformat(),
        "next_time": simulation_state["current_time"].isoformat(),
        "step_results": results
    }

# --- API Endpoints ---
@app.get("/")
def read_root():
    """ Basic endpoint to check if the server is running. """
    return {"message": "Cybersecurity Agent Simulation Backend is running."}

@app.post("/step", summary="Run One Simulation Step")
def trigger_simulation_step():
    """ Triggers one analysis step for all agents and returns step results. """
    step_summary = run_simulation_step()
    return step_summary

@app.get("/state", summary="Get Current Simulation State")
def get_current_state():
    """ Returns the current state of all agents in the simulation. """
    # Create a serializable representation of the agents' state
    serializable_agents = {}
    for agent_name, agent in simulation_state["agents"].items():
        serializable_agents[agent_name] = {
            "name": agent.name,
            "task_description": agent.task_description,
            "current_action": agent.current_action,
            "target_context_preview": (agent.target_context[:200] + "..." if agent.target_context else "None"),
            "findings_count": len(agent.findings),
            "recent_findings": agent.findings[-2:], # Show last 2 findings
            "memories_count": len(agent.memories),
            "recent_memories": agent.memories[-3:], # Show last 3 memories
        }

    return {
        "current_simulation_time": simulation_state["current_time"].isoformat(),
        "agents": serializable_agents
        }

# --- Optional Endpoint from Plan ---
@app.post("/submit_task", summary="Submit a New Task to an Agent")
def submit_task_to_agent(
    agent_name: str = Body(...),
    task_description: str = Body(...),
    context: str = Body(...)
):
    """
    Assigns a new task description and context (e.g., code) to a specific agent.
    """
    if agent_name not in simulation_state["agents"]:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")

    agent = simulation_state["agents"][agent_name]
    agent.task_description = task_description
    agent.target_context = context
    agent.current_action = "Received new task"
    agent.findings = [] # Clear old findings when a new task is submitted
    agent.add_memory(f"Received new task: {task_description}")

    print(f"Updated Agent {agent_name} with new task: {task_description}")

    return {
        "message": f"Task successfully submitted to agent '{agent_name}'.",
        "agent_name": agent_name,
        "new_task_description": task_description,
        "context_preview": context[:200] + "..."
    }

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Cybersecurity Agent Backend...")
    print(f"Ensure LM Studio is running and serving model: {os.getenv('LLM_MODEL', 'instructlab/granite-7b-lab')}")
    print(f"LM Studio URL configured as: {os.getenv('LM_STUDIO_URL', 'http://localhost:1234/v1/chat/completions')}")
    # Run the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000)
