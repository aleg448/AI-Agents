from typing import List, Dict
from datetime import datetime
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import BaseMessage
import os
import requests  # Import the requests library
import json
import random

class Agent:
    def __init__(
        self,
        name: str,
        goal: str,
        location: str,
        current_action: str,
        stats: Dict[str, int],
        achieved_goals: List[str],
    ):
        self.name = name
        self.goal = goal
        self.location = location
        self.current_action = current_action
        self.memories = []
        self.llm_model = os.getenv("LLM_MODEL")  # Use a generic LLM_MODEL env variable
        self.prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    "You are a helpful agent named {name}. Your goal is to {goal}.  Your current location is {location}."
                ),
                HumanMessagePromptTemplate.from_template(
                    "Current time: {current_time}.  Your current action is: {current_action}.  Observation: {observation}.  Relevant memories: {relevant_memories}.  What is your next action?  Respond with only your next action, do not include any other information."
                ),
            ]
        )
        self.stats = stats  # Add stats
        self.achieved_goals = achieved_goals
        self.steps_towards_goal = 0  # Track progress towards the current goal

    def get_memories(self, observation: str) -> List[str]:
        """
        Implement logic to retrieve relevant memories based on the observation
        For now, let's return all memories
        """
        return self.memories

    def add_memory(self, memory: str):
        self.memories.append(memory)

    def get_next_action(self, observation: str, current_time: datetime) -> str:
        """
        Gets the next action of the agent by sending a direct request to LM Studio.
        """
        relevant_memories = self.get_memories(observation)
        prompt_value = self.prompt.format_prompt(
            name=self.name,
            goal=self.goal,
            location=self.location,
            current_action=self.current_action,
            observation=observation,
            current_time=current_time.strftime("%H:%M"),  # Format datetime
            relevant_memories=relevant_memories,
        )
        messages: List[BaseMessage] = prompt_value.to_messages()
        # Convert Langchain messages to the format expected by LM Studio.
        lm_studio_messages = []
        for m in messages:
            role = m.type
            if role == "human":
                role = "user"  # Convert 'human' role to 'user'
            lm_studio_messages.append({"role": role, "content": m.content})
        try:
            # LM Studio endpoint
            url = "http://localhost:1234/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.llm_model,  # Use the model name
                "messages": lm_studio_messages,
                "temperature": 0.7,
            }
            print(f"Sending request to LM Studio: {url} with payload: {json.dumps(payload)}")
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()  # Raise an exception for bad status codes
            response_json = response.json()
            print(f"Received response from LM Studio: {response_json}")
            # Extract the text. This part might need adjustment based on the exact LM Studio response format.
            action = response_json["choices"][0]["message"]["content"]  # Adjust as needed
            return action
        except requests.exceptions.RequestException as e:
            print(f"Error sending request to LM Studio: {e}")
            return "Error getting action"
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from LM Studio: {e}")
            return "Error getting action"
        except KeyError as e:
            print(f"Error extracting content from LM Studio response: {e}")
            print(
                "Check the LM Studio response format. The 'choices[0].message.content' path may be incorrect."
            )
            return "Error getting action"
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return "Error getting action."

    def update_stats(self, action: str):
        """
        Updates the agent's stats based on the action performed.
        """
        # Example stat updates - adjust these based on your game's logic
        if "work" in action.lower():
            self.stats["energy"] -= 10
            self.stats["money"] += 20
            self.stats["happiness"] += 5
        elif "sleep" in action.lower():
            self.stats["energy"] += 50
            self.stats["hunger"] -= 10
        elif "eat" in action.lower():
            self.stats["hunger"] += 30
            self.stats["money"] -= 10
        elif "socialize" in action.lower():
            self.stats["happiness"] += 20
            self.stats["energy"] -= 10
        elif "body care" in action.lower():
            self.stats["body_care"] += 30
            self.stats["energy"] -= 15
        else:
            self.stats["energy"] -= 5  # Default energy decrease for other actions
        # Clamp the stats to reasonable ranges (e.g., 0-100)
        for key in self.stats:
            self.stats[key] = max(0, min(100, self.stats[key]))

    def select_new_goal(self) -> str:
        """
        Selects a new goal for the agent based on current stats and achieved goals.
        """
        if "write a novel" in self.achieved_goals:
            return "publish the novel"
        # Example goal selection logic
        if self.stats["money"] < 20:
            return "find a job"
        elif self.stats["energy"] < 30:
            return "get some sleep"
        elif self.stats["hunger"] < 20:
            return "get something to eat"
        elif self.stats["happiness"] < 30:
            return "socialize with friends"
        elif self.stats["body_care"] < 30:
            return "take care of personal hygiene"
        elif self.steps_towards_goal >= 10:  # Example: Goal achieved after 10 steps
            if self.goal == "write a novel":
                self.achieved_goals.append(self.goal)
                self.steps_towards_goal = 0
                return "publish the novel"  # Set a new goal
            elif self.goal == "publish the novel":
                self.achieved_goals.append(self.goal)
                self.steps_towards_goal = 0
                return "start a new project"
            else:
                self.achieved_goals.append(self.goal)
                self.steps_towards_goal = 0
                return "relax"
        else:
            return self.goal  # Continue with the current goal

    def advance_time(self, hours: int):
        """
        Advances the agent's internal time and updates stats accordingly.
        """
        #  Placeholder
        pass

def get_agent_action(agent: Agent, observation: str, current_time: datetime) -> str:
    """
    Gets the action of an agent given the current observation and time.  Now uses direct requests.
    """
    next_action = agent.get_next_action(observation, current_time)
    agent.update_stats(next_action)  # Update stats based on the action
    agent.steps_towards_goal += 1  # Increment steps towards goal
    agent.goal = agent.select_new_goal()  # Potentially select a new goal
    return next_action
