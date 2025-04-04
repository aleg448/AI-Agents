# agent_core.py
import os
import requests
import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Any

# LangChain imports for prompt templating
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import BaseMessage

from dotenv import load_dotenv
load_dotenv()

# --- CybersecurityAgent Class (Analyzer) ---
class CybersecurityAgent:
    def __init__(self, name: str, role_description: str):
        self.name = name
        self.role_description = role_description
        self.current_action = "Initialized"
        self.memories: List[str] = []
        self.findings: List[str] = []
        self.current_task_id: Optional[str] = None
        self.llm_model = os.getenv("LLM_MODEL", "instructlab/granite-7b-lab")
        self.prompt = ChatPromptTemplate.from_messages([
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
        ])

    def get_memories(self, k: int = 3) -> List[str]:
        return self.memories[-k:]

    def add_memory(self, memory: str):
        # Save the full memory (no truncation)
        self.memories.append(f"[{datetime.now().strftime('%H:%M:%S')}] {memory}")
        if len(self.memories) > 50:
            self.memories = self.memories[-50:]

    def perform_task(self, task_description_specific: str, target_context: str, current_time: datetime) -> str:
        self.current_action = f"Analyzing task: {task_description_specific}"
        self.findings = []
        if not target_context:
            self.add_memory("Skipped task: No target context provided.")
            return "Error: No target context provided for analysis."

        relevant_memories = self.get_memories()
        memory_str = "\n".join(f"- {mem}" for mem in relevant_memories) if relevant_memories else "None"

        prompt_value = self.prompt.format_prompt(
            name=self.name,
            role_description=self.role_description,
            task_description_specific=task_description_specific,
            current_time=current_time.strftime("%Y-%m-%d %H:%M"),
            relevant_memories=memory_str,
            target_context=target_context,
        )
        messages: List[BaseMessage] = prompt_value.to_messages()
        lm_studio_messages = []
        for m in messages:
            role = m.type
            if role == "human":
                role = "user"
            elif role == "system":
                role = "system"
            elif role == "ai":
                role = "assistant"
            else:
                role = "user"
            lm_studio_messages.append({"role": role, "content": m.content})
        try:
            url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
            headers = {"Content-Type": "application/json"}
            payload = {"model": self.llm_model, "messages": lm_studio_messages, "temperature": 0.7}
            print(f"DEBUG: Sending request to LM Studio ({url}) for agent {self.name}...")
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
            response.raise_for_status()
            response_json = response.json()
            if "choices" in response_json and len(response_json["choices"]) > 0:
                analysis_result = response_json["choices"][0]["message"]["content"].strip()
                # Save the full analysis result
                self.add_memory(f"Analysis complete. Result: {analysis_result}")
                self.findings.append(analysis_result)
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
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during analysis for agent {self.name}: {e}")
            self.add_memory(f"Error: Unexpected analysis error - {e}")
            return f"Error: An unexpected analysis error occurred - {e}"

# --- CodeGeneratorAgent Class ---
class CodeGeneratorAgent:
    def __init__(self, name: str):
        self.name = name
        self.task_description = "Generate code snippets for security analysis."
        self.current_action = "Initialized"
        self.memories: List[str] = []
        self.llm_model = os.getenv("LLM_MODEL", "instructlab/granite-7b-lab")
        self.prompt = ChatPromptTemplate.from_messages([
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
        ])

    def add_memory(self, memory: str):
        # Save the full memory message.
        self.memories.append(f"[{datetime.now().strftime('%H:%M:%S')}] {memory}")
        if len(self.memories) > 20:
            self.memories = self.memories[-20:]

    def _fix_triple_quotes(self, text: str) -> str:
        pattern = re.compile(r'"""\s*(.*?)\s*"""', re.DOTALL)
        def replacer(match):
            code_str = match.group(1)
            dumped = json.dumps(code_str)
            return dumped[1:-1]
        return pattern.sub(replacer, text)

    def _extract_json_response(self, text: str) -> Optional[Dict[str, str]]:
        pattern = re.compile(
            r'"language":\s*"(?P<language>.*?)".*?"description":\s*"(?P<description>.*?)".*?"code":\s*(?P<code>.+)\s*}\s*$',
            re.DOTALL
        )
        match = pattern.search(text)
        if match:
            language = match.group('language').strip()
            description = match.group('description').strip()
            code_raw = match.group('code').strip()
            if not (code_raw.startswith('"') and code_raw.endswith('"')):
                code_fixed = json.dumps(code_raw)
            else:
                code_fixed = code_raw
            return {"language": language, "description": description, "code": json.loads(code_fixed)}
        return None

    def perform_task(self, current_time: datetime) -> Optional[Dict[str, str]]:
        self.current_action = "Generating new code snippet..."
        print(f"DEBUG: Agent {self.name} starting code generation.")
        prompt_value = self.prompt.format_prompt(name=self.name)
        messages: List[BaseMessage] = prompt_value.to_messages()
        lm_studio_messages = []
        for m in messages:
            role = m.type
            if role == "human":
                role = "user"
            elif role == "system":
                role = "system"
            else:
                role = "user"
            lm_studio_messages.append({"role": role, "content": m.content})
        try:
            url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
            headers = {"Content-Type": "application/json"}
            payload = {"model": self.llm_model, "messages": lm_studio_messages, "temperature": 0.5}
            print(f"DEBUG: Sending request to LM Studio ({url}) for agent {self.name}...")
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=90)
            response.raise_for_status()
            outer_response = response.json()
            if "choices" in outer_response and len(outer_response["choices"]) > 0:
                inner_content = outer_response["choices"][0]["message"]["content"].strip()
                fixed_content = self._fix_triple_quotes(inner_content)
                extracted = self._extract_json_response(fixed_content)
                if extracted and all(k in extracted for k in ('language', 'description', 'code')):
                    # Save full generated code and description in memory.
                    self.add_memory(f"Generated {extracted['language']} code:\nDescription: {extracted['description']}\nCode:\n{extracted['code']}")
                    self.current_action = "Code generation successful"
                    print(f"DEBUG: Agent {self.name} successfully generated code.")
                    return extracted
                else:
                    print(f"ERROR: Failed to extract valid JSON from fixed content: {fixed_content}")
                    self.add_memory("Error: Failed to extract valid JSON from generated output.")
                    return None
            else:
                print(f"ERROR: Unexpected outer response format from LM Studio: {outer_response}")
                self.add_memory("Error: Unexpected outer response format from LM Studio.")
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
            if self.current_action == "Generating new code snippet...":
                self.current_action = "Code generation failed"
