# agent_core.py
import os
import requests # For direct LM Studio calls
import json
from datetime import datetime
from typing import List, Dict, Optional, Any

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

# --- Base Agent (Optional Refactor - keeping separate for now) ---

class CybersecurityAgent:
    """
    Represents an AI agent focused on analyzing code for security vulnerabilities.
    Picks tasks from a queue.
    """
    def __init__(
        self,
        name: str,
        role_description: str, # Describes the agent's specialty (e.g., Python analysis)
    ):
        self.name = name
        # Role description forms the core of the system prompt
        self.role_description = role_description
        self.current_action = "Initialized" # Describes the current security step/status
        self.memories: List[str] = [] # Stores history of actions/findings
        self.findings: List[str] = [] # Stores reported vulnerabilities or analysis results for the *current* task
        self.current_task_id: Optional[str] = None # Track assigned task
        self.llm_model = os.getenv("LLM_MODEL", "instructlab/granite-7b-lab") # Fallback model if not set

        # --- Prompt Template for Analysis ---
        self.prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    "You are {name}, a cybersecurity analyst AI. Your specific role is: {role_description}. "
                    "Analyze the provided context for security vulnerabilities according to best practices like the OWASP Top 10. "
                    "Be specific and clear in your analysis."
                ),
                HumanMessagePromptTemplate.from_template(
                    "Current time: {current_time}.\n"
                    "Your instructions for this specific task: {task_description_specific}\n"
                    "Relevant recent memories/findings (if any):\n{relevant_memories}\n\n"
                    "Context for analysis (e.g., code snippet):\n---\n{target_context}\n---\n\n"
                    "Based on your role and the specific task instructions, provide your analysis or next required action. "
                    "If reporting vulnerabilities, describe the issue, potential impact, and suggest a mitigation. "
                    "If the code looks secure for the given task, state that clearly. Respond concisely."
                ),
            ]
        )

    def get_memories(self, k: int = 3) -> List[str]:
        """ Retrieves the last k memories (simple implementation). """
        return self.memories[-k:]

    def add_memory(self, memory: str):
        """ Adds a memory entry (e.g., action taken, finding). """
        self.memories.append(f"[{datetime.now().strftime('%H:%M:%S')}] {memory}")
        # Optional: Limit memory size
        if len(self.memories) > 50:
            self.memories = self.memories[-50:]

    def perform_task(
        self,
        task_description_specific: str, # Specific instructions for this task
        target_context: str, # Code/context for this task
        current_time: datetime
    ) -> str:
        """
        Performs the cybersecurity analysis task by querying the LLM via LM Studio API.

        Args:
            task_description_specific: Specific instructions from the task queue item.
            target_context: The code or context to analyze for this task.
            current_time: The current simulation time.

        Returns:
            A string containing the LLM's analysis or response.
        """
        self.current_action = f"Analyzing task: {task_description_specific[:50]}..."
        self.findings = [] # Clear findings for the new task

        if not target_context:
            self.add_memory("Skipped task: No target context provided.")
            return "Error: No target context provided for analysis."

        relevant_memories = self.get_memories()
        memory_str = "\n".join(f"- {mem}" for mem in relevant_memories) if relevant_memories else "None"

        # Format the prompt using the agent's role and the specific task details
        prompt_value = self.prompt.format_prompt(
            name=self.name,
            role_description=self.role_description, # Agent's overall role
            task_description_specific=task_description_specific, # Specific task goal
            current_time=current_time.strftime("%Y-%m-%d %H:%M"),
            relevant_memories=memory_str,
            target_context=target_context,
        )
        messages: List[BaseMessage] = prompt_value.to_messages()

        # Convert Langchain messages to the format expected by LM Studio.
        lm_studio_messages = []
        for m in messages:
            role = m.type
            if role == "human": role = "user"
            elif role == "system": role = "system"
            elif role == "ai": role = "assistant"
            else: role = "user"
            lm_studio_messages.append({"role": role, "content": m.content})

        try:
            url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
            headers = {"Content-Type": "application/json"}
            payload = { "model": self.llm_model, "messages": lm_studio_messages, "temperature": 0.7 }

            print(f"DEBUG: Sending request to LM Studio ({url}) for agent {self.name}...")
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
            response.raise_for_status()
            response_json = response.json()

            if "choices" in response_json and len(response_json["choices"]) > 0:
                analysis_result = response_json["choices"][0]["message"]["content"].strip()
                self.add_memory(f"Analysis complete. Result snippet: {analysis_result[:100]}...")
                self.findings.append(analysis_result) # Store finding for this task
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
        # ... (keep other specific exceptions from previous version) ...
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during analysis for agent {self.name}: {e}")
            self.add_memory(f"Error: Unexpected analysis error - {e}")
            return f"Error: An unexpected analysis error occurred - {e}"


class CodeGeneratorAgent:
    """
    An AI agent focused on generating code snippets for security analysis.
    Adds generated tasks to a queue.
    """
    def __init__(self, name: str):
        self.name = name
        self.task_description = "Generate code snippets for security analysis." # Implicit role
        self.current_action = "Initialized"
        self.memories: List[str] = []
        self.llm_model = os.getenv("LLM_MODEL", "instructlab/granite-7b-lab")

        # --- Prompt Template for Code Generation ---
        self.prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    "You are {name}, an AI assistant that generates simple code snippets (Python, Java, Javascript) "
                    "for cybersecurity training purposes. The code should ideally contain a potential, common security flaw "
                    "or represent a pattern worth analyzing (e.g., related to input handling, database interaction, file access)."
                ),
                HumanMessagePromptTemplate.from_template(
                    "Generate a new code snippet (around 10-30 lines) and a brief description of its intended function and the language used. "
                    "Format the output ONLY as a JSON object with keys 'language', 'description', 'code'. "
                    "Example language values: 'python', 'java', 'javascript'. "
                    "Example description: 'Simple Python function to fetch user data, potentially vulnerable to SQLi'.\n"
                    "Do not include any other text before or after the JSON object."
                ),
            ]
        )

    def add_memory(self, memory: str):
        """ Adds a memory entry. """
        self.memories.append(f"[{datetime.now().strftime('%H:%M:%S')}] {memory}")
        if len(self.memories) > 20: # Shorter memory for generator
            self.memories = self.memories[-20:]

    def perform_task(self, current_time: datetime) -> Optional[Dict[str, str]]:
        """
        Generates a code snippet task by querying the LLM via LM Studio API.

        Args:
            current_time: The current simulation time.

        Returns:
            A dictionary {'language': str, 'description': str, 'code': str} or None on failure.
        """
        self.current_action = "Generating new code snippet..."
        print(f"DEBUG: Agent {self.name} starting code generation.")

        # Format the prompt
        prompt_value = self.prompt.format_prompt(name=self.name)
        messages: List[BaseMessage] = prompt_value.to_messages()

        # Convert Langchain messages to LM Studio format
        lm_studio_messages = []
        for m in messages:
            role = m.type
            if role == "human": role = "user"
            elif role == "system": role = "system"
            else: role = "user"
            lm_studio_messages.append({"role": role, "content": m.content})

        try:
            url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
            headers = {"Content-Type": "application/json"}
            # Lower temperature might be better for structured output like JSON
            payload = { "model": self.llm_model, "messages": lm_studio_messages, "temperature": 0.5 }

            print(f"DEBUG: Sending request to LM Studio ({url}) for agent {self.name}...")
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=90)
            response.raise_for_status()
            response_text = response.text.strip() # Get raw text first

            # Attempt to parse the JSON response directly
            # The prompt asks for ONLY JSON, so find the JSON block
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                 json_string = response_text[json_start:json_end]
                 try:
                     generated_data = json.loads(json_string)
                     # Validate required keys
                     if all(k in generated_data for k in ('language', 'description', 'code')):
                         self.add_memory(f"Generated {generated_data['language']} code: {generated_data['description'][:50]}...")
                         self.current_action = "Code generation successful"
                         print(f"DEBUG: Agent {self.name} successfully generated code.")
                         return generated_data
                     else:
                         print(f"ERROR: LLM response JSON missing required keys for agent {self.name}. JSON: {json_string}")
                         self.add_memory("Error: Generated JSON missing keys.")
                         return None
                 except json.JSONDecodeError as json_e:
                    print(f"ERROR: Failed to decode JSON from LLM response for agent {self.name}: {json_e}")
                    print(f"LLM Raw Response: {response_text}")
                    self.add_memory("Error: Failed to decode generated JSON.")
                    return None
            else:
                print(f"ERROR: Could not find JSON object in LLM response for agent {self.name}.")
                print(f"LLM Raw Response: {response_text}")
                self.add_memory("Error: Could not find JSON in LLM response.")
                return None

        except requests.exceptions.Timeout:
            print(f"ERROR: Request to LM Studio timed out for agent {self.name}.")
            self.add_memory("Error: LLM request timed out.")
            return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Error sending request to LM Studio for agent {self.name}: {e}")
            self.add_memory(f"Error: LLM connection failed - {e}")
            return None
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during generation for agent {self.name}: {e}")
            self.add_memory(f"Error: Unexpected generation error - {e}")
            return None
        finally:
             # Ensure action reflects outcome if not successful
             if self.current_action == "Generating new code snippet...":
                 self.current_action = "Code generation failed"