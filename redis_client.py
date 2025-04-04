# redis_client.py
import redis
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any

# --- Redis Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# --- Redis Keys ---
TASK_QUEUE_KEY = "cyber:task_queue"
RESULTS_STORE_KEY = "cyber:results_store"
FAILED_TASK_KEY = "cyber:failed_tasks" # Optional: For tasks that fail processing

# --- Redis Connection ---
redis_client: Optional[redis.Redis] = None

def get_redis_client() -> redis.Redis:
    """Initializes and returns the Redis client connection."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True # Decode responses from bytes to strings
            )
            redis_client.ping() # Check connection
            print(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except redis.exceptions.ConnectionError as e:
            print(f"ERROR: Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}. Please ensure Redis is running.")
            print(f"Error details: {e}")
            raise # Re-raise the exception to halt startup if Redis is essential
    return redis_client

# --- Task Queue Operations ---
def add_task_to_queue(task_data: Dict[str, Any]) -> bool:
    """Adds a task dictionary (serialized as JSON) to the right end of the queue."""
    try:
        r = get_redis_client()
        task_json = json.dumps(task_data)
        r.rpush(TASK_QUEUE_KEY, task_json)
        print(f"DEBUG: Added task {task_data.get('task_id')} to queue.")
        return True
    except (redis.exceptions.RedisError, json.JSONDecodeError, TypeError) as e:
        print(f"ERROR: Failed to add task to Redis queue: {e}")
        return False

def get_task_from_queue() -> Optional[Dict[str, Any]]:
    """Retrieves and removes a task dictionary from the left end of the queue."""
    try:
        r = get_redis_client()
        task_json = r.lpop(TASK_QUEUE_KEY)
        if task_json:
            task_data = json.loads(task_json)
            print(f"DEBUG: Popped task {task_data.get('task_id')} from queue.")
            return task_data
        return None # Queue is empty
    except (redis.exceptions.RedisError, json.JSONDecodeError) as e:
        print(f"ERROR: Failed to get task from Redis queue: {e}")
        return None

def get_queue_length() -> int:
    """Returns the current number of tasks in the queue."""
    try:
        r = get_redis_client()
        return r.llen(TASK_QUEUE_KEY)
    except redis.exceptions.RedisError as e:
        print(f"ERROR: Failed to get Redis queue length: {e}")
        return 0

def peek_tasks(limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieves the first 'limit' tasks from the queue without removing them."""
    tasks = []
    try:
        r = get_redis_client()
        # Get elements from index 0 to limit-1
        task_json_list = r.lrange(TASK_QUEUE_KEY, 0, limit - 1)
        for task_json in task_json_list:
            try:
                tasks.append(json.loads(task_json))
            except json.JSONDecodeError:
                print(f"WARN: Could not decode task JSON from queue: {task_json[:100]}...")
        return tasks
    except redis.exceptions.RedisError as e:
        print(f"ERROR: Failed to peek tasks from Redis queue: {e}")
        return []


# --- Results Store Operations ---
def store_result(task_id: str, result_data: Dict[str, Any]) -> bool:
    """Stores a result dictionary (serialized as JSON) in a Redis hash."""
    try:
        r = get_redis_client()
        result_json = json.dumps(result_data, default=str) # Use default=str for datetime
        r.hset(RESULTS_STORE_KEY, task_id, result_json)
        print(f"DEBUG: Stored result for task {task_id}.")
        return True
    except (redis.exceptions.RedisError, json.JSONDecodeError, TypeError) as e:
        print(f"ERROR: Failed to store result in Redis hash: {e}")
        return False

def get_result(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a specific result dictionary from the Redis hash."""
    try:
        r = get_redis_client()
        result_json = r.hget(RESULTS_STORE_KEY, task_id)
        if result_json:
            return json.loads(result_json)
        return None
    except (redis.exceptions.RedisError, json.JSONDecodeError) as e:
        print(f"ERROR: Failed to get result {task_id} from Redis hash: {e}")
        return None

def get_recent_results(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves the most recent 'limit' results (inefficient for large stores)."""
    # Note: HGETALL can be slow for very large hashes. Consider SCAN or sorted sets for production.
    results = []
    try:
        r = get_redis_client()
        all_results_json = r.hvals(RESULTS_STORE_KEY) # Gets all values
        # Sort by completion_time (assuming it exists and is ISO format)
        all_results = []
        for res_json in all_results_json:
             try:
                 all_results.append(json.loads(res_json))
             except json.JSONDecodeError:
                 print(f"WARN: Could not decode result JSON from store: {res_json[:100]}...")

        # Sort by completion time, newest first
        all_results.sort(key=lambda x: x.get('completion_time', ''), reverse=True)

        return all_results[:limit]
    except redis.exceptions.RedisError as e:
        print(f"ERROR: Failed to get recent results from Redis hash: {e}")
        return []

def get_results_count() -> int:
     """Returns the total number of results stored."""
     try:
         r = get_redis_client()
         return r.hlen(RESULTS_STORE_KEY)
     except redis.exceptions.RedisError as e:
        print(f"ERROR: Failed to get Redis results count: {e}")
        return 0

# --- Failed Task Handling (Optional) ---
def add_failed_task(failed_task_data: Dict[str, Any], error_message: str) -> bool:
    """Adds a failed task (serialized) to a separate list for inspection."""
    try:
        r = get_redis_client()
        failed_info = {
            "failed_task": failed_task_data,
            "error": error_message,
            "failed_time": datetime.now().isoformat()
        }
        failed_json = json.dumps(failed_info, default=str)
        r.rpush(FAILED_TASK_KEY, failed_json)
        print(f"WARN: Added failed task {failed_task_data.get('task_id')} to failed queue.")
        return True
    except (redis.exceptions.RedisError, json.JSONDecodeError, TypeError) as e:
        print(f"ERROR: Failed to add failed task to Redis: {e}")
        return False