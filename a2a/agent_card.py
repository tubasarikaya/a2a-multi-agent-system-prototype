"""
Agent Card - A2A protokolündeki agent kimlik kartı.

Her agent kendini tanıtan bir Agent Card yayınlar.
Bu kart, agent'ın yeteneklerini, endpoint'ini ve
diğer metadata'sını içerir.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentSkill(BaseModel):
    """Agent'ın sahip olduğu bir yetenek."""
    id: str
    name: str
    description: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: List[str] = Field(default_factory=list)


class AgentCapability(BaseModel):
    """Agent'ın desteklediği protokol özellikleri."""
    streaming: bool = False
    push_notifications: bool = False
    multi_turn: bool = True
    async_execution: bool = True


class AgentCard(BaseModel):
    """
    Agent Card - Agent'ın kendini tanıttığı yapı.

    A2A protokolünde her agent bir Agent Card yayınlar.
    Bu kart genellikle /.well-known/agent.json endpoint'inde sunulur.
    """
    # Temel bilgiler
    agent_id: str
    name: str
    description: str
    version: str = "1.0.0"

    # Endpoint bilgileri
    endpoint: str
    protocol_version: str = "1.0"

    # Yetenekler
    skills: List[AgentSkill] = Field(default_factory=list)
    capabilities: AgentCapability = Field(default_factory=AgentCapability)

    # Organizasyon bilgisi
    organization: Optional[str] = None
    department: Optional[str] = None

    # Ek metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Bağımlılıklar (bu agent'ın iletişim kurduğu diğer agent'lar)
    dependencies: List[str] = Field(default_factory=list)

    def to_well_known(self) -> Dict[str, Any]:
        """/.well-known/agent.json formatında döndürür."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "endpoint": self.endpoint,
            "protocol_version": self.protocol_version,
            "skills": [skill.model_dump() for skill in self.skills],
            "capabilities": self.capabilities.model_dump(),
            "organization": self.organization,
            "department": self.department,
            "metadata": self.metadata
        }

    def has_skill(self, skill_id: str) -> bool:
        """Agent'ın belirli bir yeteneğe sahip olup olmadığını kontrol eder."""
        return any(skill.id == skill_id for skill in self.skills)

    def get_skill(self, skill_id: str) -> Optional[AgentSkill]:
        """Belirli bir yeteneği döndürür."""
        for skill in self.skills:
            if skill.id == skill_id:
                return skill
        return None


class AgentRegistry:
    """
    Agent kayıt defteri - Sistemdeki tüm agent'ları tutar.
    """

    def __init__(self):
        self._agents: Dict[str, AgentCard] = {}
        self._department_agents: Dict[str, List[str]] = {}

    def register(self, agent_card: AgentCard):
        """Agent'ı kayıt defterine ekler."""
        self._agents[agent_card.agent_id] = agent_card

        # Departman bazlı indexleme
        if agent_card.department:
            if agent_card.department not in self._department_agents:
                self._department_agents[agent_card.department] = []
            if agent_card.agent_id not in self._department_agents[agent_card.department]:
                self._department_agents[agent_card.department].append(agent_card.agent_id)

    def unregister(self, agent_id: str):
        """Agent'ı kayıt defterinden çıkarır."""
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            if agent.department and agent.department in self._department_agents:
                self._department_agents[agent.department].remove(agent_id)
            del self._agents[agent_id]

    def get(self, agent_id: str) -> Optional[AgentCard]:
        """Agent kartını döndürür."""
        return self._agents.get(agent_id)

    def get_by_department(self, department: str) -> List[AgentCard]:
        """Bir departmandaki tüm agent'ları döndürür."""
        agent_ids = self._department_agents.get(department, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_all(self) -> List[AgentCard]:
        """Tüm agent'ları döndürür."""
        return list(self._agents.values())

    def find_by_skill(self, skill_id: str) -> List[AgentCard]:
        """Belirli bir yeteneğe sahip agent'ları bulur."""
        return [agent for agent in self._agents.values() if agent.has_skill(skill_id)]

    def get_department_orchestrator(self, department: str) -> Optional[AgentCard]:
        """Bir departmanın orchestrator'ını döndürür."""
        agents = self.get_by_department(department)
        for agent in agents:
            if "orchestrator" in agent.agent_id.lower() or agent.metadata.get("is_orchestrator"):
                return agent
        return None


# Global registry instance
agent_registry = AgentRegistry()
