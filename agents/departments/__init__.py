from .base_department import BaseDepartmentAgent
from .it import ITOrchestrator, TechSupportAgent, EmailSupportAgent
from .student_affairs import StudentAffairsOrchestrator, RegistrationAgent, CourseAgent
from .finance import FinanceOrchestrator, TuitionAgent, ScholarshipAgent

__all__ = [
    "BaseDepartmentAgent",
    "ITOrchestrator", "TechSupportAgent", "EmailSupportAgent",
    "StudentAffairsOrchestrator", "RegistrationAgent", "CourseAgent",
    "FinanceOrchestrator", "TuitionAgent", "ScholarshipAgent"
]
