"""
Database Connection - Veritabanı bağlantısı ve sorgu metodları.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import structlog

from .models import (
    Base, Student, Course, StudentCourse, Tuition, Payment,
    Installment, Scholarship, ScholarshipApplication,
    AvailableScholarship, UserAccount, ITTicket, KnownIssue,
    Device, CourseRegistrationPeriod
)

logger = structlog.get_logger()


class DatabaseConnection:
    """
    Veritabanı bağlantı ve sorgu sınıfı.
    Agent'ların kullandığı tüm DB metodlarını içerir.
    """

    def __init__(self, database_url: str = "sqlite:///./university.db"):
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Tabloları oluşturur."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("database_tables_created")

    def get_session(self) -> Session:
        """Yeni session döndürür."""
        return self.SessionLocal()

    # ==================== STUDENT ENTITY ====================

    async def get_student(self, student_id: str) -> Optional[Any]:
        """
        Öğrenci ORM nesnesini döndürür.
        AcademicStatusAgent gibi yerlerde doğrudan attribute erişimi için kullanılır.
        """
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()
            return student

    # ==================== STUDENT QUERIES ====================

    async def get_student_info(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Öğrenci bilgilerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if student:
                return {
                    "id": student.id,
                    "student_id": student.student_id,
                    "full_name": student.full_name,
                    "email": student.email,
                    "department": student.department,
                    "faculty": student.faculty,
                    "grade": student.grade,
                    "enrollment_year": student.enrollment_year,
                    "registration_status": student.registration_status
                }
        return None

    async def get_academic_status(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Akademik durum bilgilerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if student:
                # Mevcut krediyi hesapla
                current_courses = session.query(StudentCourse).filter(
                    StudentCourse.student_id == student.id,
                    StudentCourse.status == "Devam"
                ).all()

                current_credits = sum(
                    session.query(Course).get(c.course_id).credits
                    for c in current_courses
                )

                # Max kredi (GANO'ya göre)
                max_credits = 30
                if student.gpa and student.gpa >= 3.0:
                    max_credits = 36
                elif student.gpa and student.gpa >= 2.5:
                    max_credits = 33

                return {
                    "gpa": student.gpa,
                    "total_credits": student.total_credits,
                    "completed_credits": student.completed_credits,
                    "current_semester": student.current_semester,
                    "current_credits": current_credits,
                    "max_credits": max_credits,
                    "grade": student.grade
                }
        return None

    # ==================== COURSE QUERIES ====================

    async def get_course_registration_status(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Ders kayıt durumunu döndürür."""
        with self.get_session() as session:
            # Aktif kayıt dönemi
            period = session.query(CourseRegistrationPeriod).filter(
                CourseRegistrationPeriod.is_active == True
            ).first()

            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if period:
                return {
                    "is_open": True,
                    "start_date": period.start_date.strftime("%Y-%m-%d") if period.start_date else None,
                    "end_date": period.end_date.strftime("%Y-%m-%d") if period.end_date else None,
                    "semester": period.semester,
                    "approval_status": "Onay Bekleniyor" if student else None
                }

            # Gelecek dönem bilgisi
            next_period = session.query(CourseRegistrationPeriod).filter(
                CourseRegistrationPeriod.start_date > datetime.utcnow()
            ).order_by(CourseRegistrationPeriod.start_date).first()

            return {
                "is_open": False,
                "start_date": next_period.start_date.strftime("%Y-%m-%d") if next_period else None,
                "end_date": None,
                "semester": next_period.semester if next_period else None,
                "approval_status": None
            }

    async def get_current_courses(self, student_id: str) -> List[Dict[str, Any]]:
        """Öğrencinin mevcut derslerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return []

            enrollments = session.query(StudentCourse).filter(
                StudentCourse.student_id == student.id,
                StudentCourse.status == "Devam"
            ).all()

            courses = []
            for enrollment in enrollments:
                course = session.query(Course).get(enrollment.course_id)
                if course:
                    courses.append({
                        "code": course.course_code,
                        "name": course.course_name,
                        "credits": course.credits,
                        "instructor": course.instructor,
                        "grade": enrollment.grade
                    })

            return courses

    # ==================== TUITION QUERIES ====================

    async def get_tuition_status(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Harç durumunu döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return None

            tuition = session.query(Tuition).filter(
                Tuition.student_id == student.id
            ).first()

            if tuition:
                return {
                    "has_debt": tuition.has_debt,
                    "debt_amount": tuition.debt_amount,
                    "total_amount": tuition.total_amount,
                    "paid_amount": tuition.paid_amount,
                    "due_date": tuition.due_date.strftime("%Y-%m-%d") if tuition.due_date else None,
                    "semester": tuition.semester
                }

            return {"has_debt": False, "debt_amount": 0}

    async def get_payment_history(self, student_id: str) -> List[Dict[str, Any]]:
        """Ödeme geçmişini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return []

            tuition = session.query(Tuition).filter(
                Tuition.student_id == student.id
            ).first()

            if not tuition:
                return []

            payments = session.query(Payment).filter(
                Payment.tuition_id == tuition.id
            ).order_by(Payment.payment_date.desc()).all()

            return [
                {
                    "date": p.payment_date.strftime("%Y-%m-%d"),
                    "amount": p.amount,
                    "method": p.payment_method,
                    "receipt": p.receipt_no
                }
                for p in payments
            ]

    async def get_installment_info(self, student_id: str) -> List[Dict[str, Any]]:
        """Taksit bilgilerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return []

            tuition = session.query(Tuition).filter(
                Tuition.student_id == student.id
            ).first()

            if not tuition:
                return []

            installments = session.query(Installment).filter(
                Installment.tuition_id == tuition.id
            ).order_by(Installment.installment_number).all()

            return [
                {
                    "number": i.installment_number,
                    "amount": i.amount,
                    "due_date": i.due_date.strftime("%Y-%m-%d") if i.due_date else None,
                    "status": i.status
                }
                for i in installments
            ]

    # ==================== SCHOLARSHIP QUERIES ====================

    async def get_scholarship_status(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Burs durumunu döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return None

            scholarship = session.query(Scholarship).filter(
                Scholarship.student_id == student.id,
                Scholarship.status == "Aktif"
            ).first()

            if scholarship:
                return {
                    "active_scholarship": True,
                    "scholarship_name": scholarship.scholarship_name,
                    "scholarship_type": scholarship.scholarship_type,
                    "monthly_amount": scholarship.monthly_amount,
                    "start_date": scholarship.start_date.strftime("%Y-%m-%d") if scholarship.start_date else None,
                    "end_date": scholarship.end_date.strftime("%Y-%m-%d") if scholarship.end_date else None
                }

            return {"active_scholarship": False}

    async def get_scholarship_applications(self, student_id: str) -> List[Dict[str, Any]]:
        """Burs başvurularını döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return []

            applications = session.query(ScholarshipApplication).filter(
                ScholarshipApplication.student_id == student.id
            ).order_by(ScholarshipApplication.application_date.desc()).all()

            return [
                {
                    "scholarship_name": a.scholarship_name,
                    "application_date": a.application_date.strftime("%Y-%m-%d"),
                    "status": a.status
                }
                for a in applications
            ]

    async def get_available_scholarships(self) -> List[Dict[str, Any]]:
        """Başvuruya açık bursları döndürür."""
        with self.get_session() as session:
            scholarships = session.query(AvailableScholarship).filter(
                AvailableScholarship.is_active == True,
                AvailableScholarship.deadline > datetime.utcnow()
            ).all()

            return [
                {
                    "name": s.name,
                    "description": s.description,
                    "amount": s.monthly_amount,
                    "min_gpa": s.min_gpa,
                    "deadline": s.deadline.strftime("%Y-%m-%d") if s.deadline else None
                }
                for s in scholarships
            ]

    # ==================== IT QUERIES ====================

    async def get_user_account(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Kullanıcı hesap bilgilerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student or not student.account:
                return None

            account = student.account
            return {
                "username": account.username,
                "email": account.email,
                "status": account.status,
                "last_login": account.last_login.strftime("%Y-%m-%d %H:%M") if account.last_login else None,
                "is_locked": account.is_locked
            }

    async def get_password_info(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Şifre bilgilerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student or not student.account:
                return None

            account = student.account
            return {
                "last_changed": account.password_last_changed.strftime("%Y-%m-%d") if account.password_last_changed else None,
                "expired": account.password_expired
            }

    async def get_open_tickets(self, student_id: str, department: str = None) -> List[Dict[str, Any]]:
        """Açık destek taleplerini döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return []

            query = session.query(ITTicket).filter(
                ITTicket.student_id == student.id,
                ITTicket.status.in_(["Açık", "İşlemde"])
            )

            if department:
                query = query.filter(ITTicket.category.like(f"%{department}%"))

            tickets = query.all()

            return [
                {
                    "ticket_no": t.ticket_no,
                    "subject": t.subject,
                    "status": t.status,
                    "created_at": t.created_at.strftime("%Y-%m-%d")
                }
                for t in tickets
            ]

    async def get_known_issues(self, category: str = None) -> List[Dict[str, Any]]:
        """Bilinen sorunları döndürür."""
        with self.get_session() as session:
            query = session.query(KnownIssue).filter(
                KnownIssue.is_resolved == False
            )

            if category:
                query = query.filter(KnownIssue.category == category)

            issues = query.all()

            return [
                {
                    "title": i.title,
                    "description": i.description,
                    "solution": i.solution
                }
                for i in issues
            ]

    async def get_user_devices(self, student_id: str) -> List[Dict[str, Any]]:
        """Kullanıcı cihazlarını döndürür."""
        with self.get_session() as session:
            student = session.query(Student).filter(
                Student.student_id == student_id
            ).first()

            if not student:
                return []

            devices = session.query(Device).filter(
                Device.student_id == student.id
            ).all()

            return [
                {
                    "type": d.device_type,
                    "brand": d.brand,
                    "model": d.model,
                    "serial": d.serial_no
                }
                for d in devices
            ]


# Singleton instance
_db_instance: Optional[DatabaseConnection] = None


def get_database(database_url: str = "sqlite:///./university.db") -> DatabaseConnection:
    """Database connection singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseConnection(database_url)
        _db_instance.create_tables()
    return _db_instance
