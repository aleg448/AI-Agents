# mongodb_client.py
from pymongo import MongoClient
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ai_agents")

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]

# Collections
task_queue = db["task_queue"]
results_store = db["results_store"]
failed_tasks = db["failed_tasks"]

# --- Task Queue Operations ---
def add_task_to_queue(task_data: Dict[str, Any]) -> bool:
    """Adds a task to MongoDB queue."""
    try:
        task_data["created_at"] = datetime.utcnow()
        task_queue.insert_one(task_data)
        print(f"DEBUG: Added task {task_data.get('task_id')} to queue.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to add task to queue: {e}")
        return False

def get_task_from_queue() -> Optional[Dict[str, Any]]:
    """Retrieves and removes the oldest task from MongoDB queue."""
    try:
        task = task_queue.find_one_and_delete({}, sort=[("created_at", 1)])
        if task:
            task.pop("_id", None)  # Remove MongoDB object ID
            print(f"DEBUG: Popped task {task.get('task_id')} from queue.")
        return task
    except Exception as e:
        print(f"ERROR: Failed to get task from queue: {e}")
        return None

def get_queue_length() -> int:
    """Returns the number of tasks in the queue."""
    return task_queue.count_documents({})

def peek_tasks(limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieves the first 'limit' tasks without removing them."""
    tasks = list(task_queue.find().sort("created_at", 1).limit(limit))
    for task in tasks:
        task.pop("_id", None)
    return tasks

# --- Results Store Operations ---
def store_result(task_id: str, result_data: Dict[str, Any]) -> bool:
    """Stores a result in MongoDB."""
    try:
        result_data["task_id"] = task_id
        result_data["completion_time"] = datetime.utcnow()
        results_store.update_one({"task_id": task_id}, {"$set": result_data}, upsert=True)
        print(f"DEBUG: Stored result for task {task_id}.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to store result: {e}")
        return False

def get_result(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a specific result from MongoDB."""
    result = results_store.find_one({"task_id": task_id})
    if result:
        result.pop("_id", None)
    return result

def get_recent_results(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves the most recent results."""
    results = list(results_store.find().sort("completion_time", -1).limit(limit))
    for result in results:
        result.pop("_id", None)
    return results

def get_results_count() -> int:
    """Returns the total number of results stored."""
    return results_store.count_documents({})

# --- Failed Task Handling ---
def add_failed_task(failed_task_data: Dict[str, Any], error_message: str) -> bool:
    """Adds a failed task to MongoDB."""
    try:
        failed_info = {
            "failed_task": failed_task_data,
            "error": error_message,
            "failed_time": datetime.utcnow(),
        }
        failed_tasks.insert_one(failed_info)
        print(f"WARN: Added failed task {failed_task_data.get('task_id')} to failed queue.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to add failed task: {e}")
        return False
