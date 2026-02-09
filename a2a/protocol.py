"""
A2A Protocol Implementation - Google Agent-to-Agent Protocol

Bu modül, A2A protokolünün temel yapı taşlarını implement eder:
- Task: İş birimi, yaşam döngüsü durumları ile
- Message: Agent'lar arası iletişim birimi
- Artifact: Görev çıktıları
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """A2A Task yaşam döngüsü durumları."""
    SUBMITTED = "submitted"      # Görev gönderildi
    WORKING = "working"          # Agent üzerinde çalışıyor
    INPUT_REQUIRED = "input_required"  # Ek bilgi gerekli
    COMPLETED = "completed"      # Başarıyla tamamlandı
    FAILED = "failed"            # Hata oluştu
    CANCELED = "canceled"        # İptal edildi


class MessageRole(str, Enum):
    """Mesaj gönderen rolü."""
    USER = "user"
    AGENT = "agent"


class TextPart(BaseModel):
    """Metin içerik parçası."""
    type: str = "text"
    text: str


class DataPart(BaseModel):
    """Yapılandırılmış veri parçası (JSON)."""
    type: str = "data"
    data: Dict[str, Any]


class FilePart(BaseModel):
    """Dosya içerik parçası."""
    type: str = "file"
    file_uri: Optional[str] = None
    file_data: Optional[str] = None  # Base64 encoded
    mime_type: str = "application/octet-stream"


# Union type for message parts
MessagePart = Union[TextPart, DataPart, FilePart]


class A2AMessage(BaseModel):
    """
    A2A Protokolü Mesaj Yapısı.
    Agent'lar arası iletişimin temel birimi.
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: MessageRole
    parts: List[MessagePart]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    context_id: Optional[str] = None  # İlişkili bağlam
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_text(self) -> str:
        """Mesajdaki tüm metin parçalarını birleştirir."""
        texts = []
        for part in self.parts:
            if isinstance(part, TextPart):
                texts.append(part.text)
            elif isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        return " ".join(texts)

    def get_data(self) -> Dict[str, Any]:
        """Mesajdaki tüm veri parçalarını birleştirir."""
        result = {}
        for part in self.parts:
            if isinstance(part, DataPart):
                result.update(part.data)
            elif isinstance(part, dict) and part.get("type") == "data":
                result.update(part.get("data", {}))
        return result


class Artifact(BaseModel):
    """
    Görev çıktısı - agent tarafından üretilen somut sonuçlar.
    """
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    parts: List[MessagePart]
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class A2ATask(BaseModel):
    """
    A2A Protokolü Task Yapısı.
    Agent'lar arası işlem biriminin temel yapısı.
    """
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context_id: Optional[str] = None
    status: TaskStatus = TaskStatus.SUBMITTED

    # Task sahibi ve hedef
    from_agent: str
    to_agent: str

    # İlk mesaj
    initial_message: A2AMessage

    # Mesaj geçmişi (çoklu tur için)
    history: List[A2AMessage] = Field(default_factory=list)

    # Üretilen çıktılar
    artifacts: List[Artifact] = Field(default_factory=list)

    # Hata bilgisi
    error: Optional[str] = None

    # Zaman damgaları
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Ek metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Alt görevler (orchestrator için)
    subtasks: List[str] = Field(default_factory=list)  # Alt task ID'leri
    parent_task_id: Optional[str] = None

    def update_status(self, new_status: TaskStatus, error: Optional[str] = None):
        """Task durumunu günceller."""
        self.status = new_status
        self.updated_at = datetime.utcnow().isoformat()
        if error:
            self.error = error

    def add_message(self, message: A2AMessage):
        """Geçmişe mesaj ekler."""
        self.history.append(message)
        self.updated_at = datetime.utcnow().isoformat()

    def add_artifact(self, artifact: Artifact):
        """Çıktı ekler."""
        self.artifacts.append(artifact)
        self.updated_at = datetime.utcnow().isoformat()

    def get_latest_message(self) -> A2AMessage:
        """En son mesajı döndürür."""
        if self.history:
            return self.history[-1]
        return self.initial_message

    def get_all_text(self) -> str:
        """Tüm mesajlardaki metinleri birleştirir."""
        texts = [self.initial_message.get_text()]
        for msg in self.history:
            texts.append(msg.get_text())
        return " ".join(texts)


# Helper functions
def create_task(
    from_agent: str,
    to_agent: str,
    text: str,
    data: Optional[Dict[str, Any]] = None,
    context_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> A2ATask:
    """Yeni bir A2A Task oluşturur."""
    parts: List[MessagePart] = [TextPart(text=text)]
    if data:
        parts.append(DataPart(data=data))

    message = A2AMessage(
        role=MessageRole.USER,
        parts=parts,
        context_id=context_id
    )

    return A2ATask(
        from_agent=from_agent,
        to_agent=to_agent,
        initial_message=message,
        context_id=context_id,
        parent_task_id=parent_task_id,
        metadata=metadata or {}
    )


def create_message(
    role: MessageRole,
    text: str,
    data: Optional[Dict[str, Any]] = None,
    context_id: Optional[str] = None
) -> A2AMessage:
    """Yeni bir A2A Message oluşturur."""
    parts: List[MessagePart] = [TextPart(text=text)]
    if data:
        parts.append(DataPart(data=data))

    return A2AMessage(
        role=role,
        parts=parts,
        context_id=context_id
    )


def create_response(
    task: A2ATask,
    text: str,
    data: Optional[Dict[str, Any]] = None,
    artifacts: Optional[List[Artifact]] = None,
    status: TaskStatus = TaskStatus.COMPLETED
) -> A2ATask:
    """Task için başarılı yanıt oluşturur."""
    response_message = create_message(
        role=MessageRole.AGENT,
        text=text,
        data=data,
        context_id=task.context_id
    )

    task.add_message(response_message)
    task.update_status(status)

    if artifacts:
        for artifact in artifacts:
            task.add_artifact(artifact)

    return task


def create_error_response(
    task: A2ATask,
    error_message: str
) -> A2ATask:
    """Task için hata yanıtı oluşturur."""
    response_message = create_message(
        role=MessageRole.AGENT,
        text=f"Hata: {error_message}",
        context_id=task.context_id
    )

    task.add_message(response_message)
    task.update_status(TaskStatus.FAILED, error=error_message)

    return task


class TaskLabel(BaseModel):
    """Görev etiketi - orchestrator tarafından atanır."""
    label_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    department: str
    category: str
    priority: int = 1  # 1: düşük, 5: yüksek
    keywords: List[str] = Field(default_factory=list)
    requires_departments: List[str] = Field(default_factory=list)  # Çoklu departman gerektiren görevler için
