"""Multi-Agent Orchestration Engine for Smart AI Gateway.

Provides specialized agent personas and blackboard collaboration:
- Roles: Orchestrator, Coding, Debugging, Testing, Code Review, Research,
  Documentation, Database, Deployment, Security, Planning.
- Central SharedBlackboard for agent communication and file concurrency locks.
- Concurrency locks prevent conflicting file edits between agents.
- Orchestrator supervises task assignment, tool routing, and validation.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class AgentRole(str, enum.Enum):
    ORCHESTRATOR = "orchestrator"
    CODING = "coding"
    DEBUGGING = "debugging"
    TESTING = "testing"
    CODE_REVIEW = "code_review"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    DATABASE = "database"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    PLANNING = "planning"


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class SharedBlackboard:
    """Shared state, message bus, and file lock coordinator across agents."""

    def __init__(self):
        self.messages: List[AgentMessage] = []
        self.file_locks: Dict[str, str] = {}  # file_path -> agent_name
        self.shared_facts: Dict[str, Any] = {}

    def post_message(
        self, sender: str, recipient: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        msg = AgentMessage(sender=sender, recipient=recipient, content=content, metadata=metadata or {})
        self.messages.append(msg)
        return msg

    def get_messages_for(self, recipient: str) -> List[AgentMessage]:
        return [m for m in self.messages if m.recipient in (recipient, "all", "*")]

    def acquire_file_lock(self, file_path: str, agent_name: str) -> bool:
        """Acquires exclusive write lock on a file for an agent."""
        clean_path = str(file_path).replace("\\", "/")
        if clean_path in self.file_locks:
            return self.file_locks[clean_path] == agent_name
        self.file_locks[clean_path] = agent_name
        return True

    def release_file_lock(self, file_path: str, agent_name: str) -> bool:
        """Releases write lock on a file."""
        clean_path = str(file_path).replace("\\", "/")
        if clean_path in self.file_locks and self.file_locks[clean_path] == agent_name:
            del self.file_locks[clean_path]
            return True
        return False

    def is_file_locked(self, file_path: str, by_other_than: Optional[str] = None) -> bool:
        clean_path = str(file_path).replace("\\", "/")
        if clean_path not in self.file_locks:
            return False
        if by_other_than:
            return self.file_locks[clean_path] != by_other_than
        return True


class SpecializedAgent:
    """An autonomous agent persona specialized in a specific domain."""

    def __init__(
        self,
        name: str,
        role: AgentRole,
        system_prompt: str,
        blackboard: Optional[SharedBlackboard] = None,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.blackboard = blackboard or SharedBlackboard()

    def send(self, recipient: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> AgentMessage:
        return self.blackboard.post_message(self.name, recipient, content, metadata)

    def read_inbox(self) -> List[AgentMessage]:
        return self.blackboard.get_messages_for(self.name)


class MultiAgentOrchestrator:
    """Orchestrates specialized personas to solve multi-faceted engineering tasks."""

    def __init__(self, blackboard: Optional[SharedBlackboard] = None):
        self.blackboard = blackboard or SharedBlackboard()
        self.agents: Dict[str, SpecializedAgent] = {}
        self._init_specialized_agents()

    def _init_specialized_agents(self) -> None:
        personas = [
            (
                "orchestrator",
                AgentRole.ORCHESTRATOR,
                "Master coordinator responsible for plan decomposition, task delegation, and final synthesis.",
            ),
            (
                "coder",
                AgentRole.CODING,
                "Specialized software engineer writing clean, robust, type-annotated production code.",
            ),
            (
                "debugger",
                AgentRole.DEBUGGING,
                "Diagnostic specialist identifying root causes of exceptions, syntax errors, and race conditions.",
            ),
            (
                "tester",
                AgentRole.TESTING,
                "QA specialist creating comprehensive unit, integration, and regression test suites.",
            ),
            (
                "reviewer",
                AgentRole.CODE_REVIEW,
                "Senior code reviewer auditing security, edge cases, algorithmic efficiency, and conventions.",
            ),
            (
                "database_expert",
                AgentRole.DATABASE,
                "Database architect managing schemas, migrations, query optimization, and data integrity.",
            ),
            (
                "devops_engineer",
                AgentRole.DEPLOYMENT,
                "DevOps engineer managing containerization, CI/CD pipelines, and cloud health monitoring.",
            ),
            (
                "security_auditor",
                AgentRole.SECURITY,
                "Security auditor scanning for vulnerabilities, secret leakage, and unsafe shell inputs.",
            ),
        ]

        for name, role, prompt in personas:
            self.agents[name] = SpecializedAgent(name, role, prompt, self.blackboard)

    def get_agent(self, name_or_role: str | AgentRole) -> Optional[SpecializedAgent]:
        if isinstance(name_or_role, AgentRole):
            for ag in self.agents.values():
                if ag.role == name_or_role:
                    return ag
            return None
        return self.agents.get(name_or_role)

    def route_task(self, task_description: str) -> SpecializedAgent:
        """Determines best specialized agent persona based on task semantics."""
        lower = task_description.lower()
        if any(w in lower for w in ("test", "pytest", "assert", "coverage")):
            return self.agents["tester"]
        if any(w in lower for w in ("debug", "fix", "error", "traceback", "exception")):
            return self.agents["debugger"]
        if any(w in lower for w in ("review", "audit", "critique")):
            return self.agents["reviewer"]
        if any(w in lower for w in ("database", "sql", "table", "schema", "sqlite")):
            return self.agents["database_expert"]
        if any(w in lower for w in ("docker", "deploy", "render", "ci", "compose")):
            return self.agents["devops_engineer"]
        if any(w in lower for w in ("security", "leak", "vulnerability", "token")):
            return self.agents["security_auditor"]
        if any(w in lower for w in ("write", "create", "implement", "code", "build")):
            return self.agents["coder"]
        return self.agents["orchestrator"]


default_orchestrator = MultiAgentOrchestrator()
