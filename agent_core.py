# agent_core.py
import os
import requests # For direct LM Studio calls
import json
from datetime import datetime
from typing import List, Dict, Optional

# LangChain imports for prompt templating
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import BaseMessage

# Load environment variables (especially LLM_MODEL)
from dotenv import load_dotenv
load_dotenv()

class CybersecurityAgent:
    """
    Represents an AI agent focused on cybersecurity tasks.
    """
    def __init__(
        self,
        name: str,
        task_description: str,
        target_context: Optional[str] = None, # Code or context to analyze
    ):
        self.name = name
        self.task_description = task_description
        self.target_context = target_context if target_context else ""
        self.current_action = "Initialized" # Describes the current security step/status
        self.memories: List[str] = [] # Stores history of actions/findings
        self.findings: List[str] = [] # Stores reported vulnerabilities or analysis results
        self.llm_model = os.getenv("LLM_MODEL", "instructlab/granite-7b-lab") # Fallback model if not set

        # --- New Prompt Template for Cybersecurity ---
        self.prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    "You are {name}, a cybersecurity analyst AI. Your current task is: {task_description}. "
                    "Analyze the provided context for security vulnerabilities according to best practices like the OWASP Top 10. "
                    "Be specific and clear in your analysis."
                ),
                HumanMessagePromptTemplate.from_template(
                    "Current time: {current_time}.\n"
                    "Relevant recent memories/findings:\n{relevant_memories}\n\n"
                    "Context for analysis:\n---\n{target_context}\n---\n\n"
                    "Based on your task, provide your analysis or next required action. "
                    "If reporting vulnerabilities, describe the issue, potential impact, and suggest a mitigation. "
                    "If the code looks secure for the given task, state that clearly. Respond concisely."
                ),
            ]
        )

    def get_memories(self, k: int = 3) -> List[str]:
        """
        Retrieves the last k memories (simple implementation).
        Replace with vector search later.
        """
        return self.memories[-k:]

    def add_memory(self, memory: str):
        """Adds a memory entry (e.g., action taken, finding)."""
        self.memories.append(f"[{datetime.now().strftime('%H:%M:%S')}] {memory}")

    def perform_task(self, current_time: datetime) -> str:
        """
        Performs the cybersecurity task by querying the LLM via LM Studio API.

        Args:
            current_time: The current simulation time.

        Returns:
            A string containing the LLM's analysis or response.
        """
        if not self.target_context:
            return "No target context provided for analysis."

        relevant_memories = self.get_memories()
        memory_str = "\n".join(f"- {mem}" for mem in relevant_memories) if relevant_memories else "None"

        # Format the prompt using the new structure
        prompt_value = self.prompt.format_prompt(
            name=self.name,
            task_description=self.task_description,
            current_time=current_time.strftime("%Y-%m-%d %H:%M"),
            relevant_memories=memory_str,
            target_context=self.target_context,
        )
        messages: List[BaseMessage] = prompt_value.to_messages()

        # Convert Langchain messages to the format expected by LM Studio.
        lm_studio_messages = []
        for m in messages:
            role = m.type
            if role == "human":
                role = "user" # Convert 'human' role to 'user' for LM Studio
            elif role == "system":
                role = "system"
            elif role == "ai":
                 role = "assistant" # Assuming LM Studio uses 'assistant'
            else:
                 role = "user" # Default fallback
            lm_studio_messages.append({"role": role, "content": m.content})

        try:
            # LM Studio endpoint (ensure LM Studio is running and serving the model)
            url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.llm_model,
                "messages": lm_studio_messages,
                "temperature": 0.7,
                # Add other parameters like max_tokens if needed
                # "max_tokens": 500,
            }

            print(f"DEBUG: Sending request to LM Studio ({url}) for agent {self.name}...")
            # print(f"DEBUG: Payload: {json.dumps(payload, indent=2)}") # Uncomment for detailed debugging

            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120) # Added timeout
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            response_json = response.json()

            # print(f"DEBUG: Received response from LM Studio: {response_json}") # Uncomment for detailed debugging

            # Extract the response content - adjust path if needed based on your LM Studio version/model
            if "choices" in response_json and len(response_json["choices"]) > 0:
                analysis_result = response_json["choices"][0]["message"]["content"].strip()
                self.add_memory(f"Performed task: {self.task_description}. Result snippet: {analysis_result[:100]}...") # Log action
                return analysis_result
            else:
                print(f"ERROR: Unexpected response format from LM Studio: {response_json}")
                self.add_memory("Error: Unexpected response format from LLM.")
                return "Error: Could not parse LLM response."

        except requests.exceptions.Timeout:
            print(f"ERROR: Request to LM Studio timed out for agent {self.name}.")
            self.add_memory("Error: LLM request timed out.")
            return "Error: LLM request timed out."
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Error sending request to LM Studio for agent {self.name}: {e}")
            self.add_memory(f"Error: LLM connection failed - {e}")
            return f"Error: Failed to connect to LLM - {e}"
        except json.JSONDecodeError as e:
            print(f"ERROR: Error decoding JSON response from LM Studio for agent {self.name}: {e}")
            print(f"Response text: {response.text}")
            self.add_memory("Error: Could not decode LLM JSON response.")
            return "Error: Could not decode LLM response."
        except KeyError as e:
            print(f"ERROR: Error extracting content from LM Studio response for agent {self.name}: {e}")
            print(f"Response JSON: {response_json}") # Log the actual JSON to see the structure
            self.add_memory("Error: Could not extract content from LLM response.")
            return "Error: Could not extract content from LLM response."
        except Exception as e:
            print(f"ERROR: An unexpected error occurred for agent {self.name}: {e}")
            self.add_memory(f"Error: Unexpected error - {e}")
            return f"Error: An unexpected error occurred - {e}"

