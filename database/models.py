"""
Database Models - SQLAlchemy modelleri.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Student(Base):
    """Öğrenci tablosu."""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    student_id = Column(String(20), unique=True, nullable=False)  # Öğrenci no
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True)
    department = Column(String(100))
    faculty = Column(String(100))
    grade = Column(Integer)  # Sınıf
    enrollment_year = Column(Integer)
    registration_status = Column(String(50), default="Aktif")  # Aktif, Pasif, Dondurulmuş
    gpa = Column(Float, default=0.0)
    total_credits = Column(Integer, default=0)
    completed_credits = Column(Integer, default=0)
    current_semester = Column(Integer, default=1)

    # Relationships
    courses = relationship("StudentCourse", back_populates="student")
    tuition = relationship("Tuition", back_populates="student", uselist=False)
    scholarships = relationship("Scholarship", back_populates="student")
    account = relationship("UserAccount", back_populates="student", uselist=False)


class Course(Base):
    """Ders tablosu."""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    course_code = Column(String(20), unique=True, nullable=False)
    course_name = Column(String(200), nullable=False)
    credits = Column(Integer, default=3)
    department = Column(String(100))
    semester = Column(Integer)
    instructor = Column(String(100))
    prerequisite = Column(String(20))  # Ön koşul ders kodu

    # Relationships
    enrollments = relationship("StudentCourse", back_populates="course")


class StudentCourse(Base):
    """Öğrenci-Ders ilişki tablosu."""
    __tablename__ = "student_courses"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    semester = Column(String(20))  # 2024-Güz
    grade = Column(String(5))  # AA, BA, vb.
    status = Column(String(20), default="Devam")  # Devam, Tamamlandı, Bırakıldı

    # Relationships
    student = relationship("Student", back_populates="courses")
    course = relationship("Course", back_populates="enrollments")


class Tuition(Base):
    """Harç tablosu."""
    __tablename__ = "tuition"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    semester = Column(String(20))
    total_amount = Column(Float, default=0.0)
    paid_amount = Column(Float, default=0.0)
    has_debt = Column(Boolean, default=False)
    debt_amount = Column(Float, default=0.0)
    due_date = Column(DateTime)
    last_payment_date = Column(DateTime)

    # Relationships
    student = relationship("Student", back_populates="tuition")
    payments = relationship("Payment", back_populates="tuition")
    installments = relationship("Installment", back_populates="tuition")


class Payment(Base):
    """Ödeme geçmişi tablosu."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    tuition_id = Column(Integer, ForeignKey("tuition.id"))
    amount = Column(Float)
    payment_date = Column(DateTime, default=datetime.utcnow)
    payment_method = Column(String(50))  # Kredi Kartı, Havale, vb.
    receipt_no = Column(String(50))

    # Relationships
    tuition = relationship("Tuition", back_populates="payments")


class Installment(Base):
    """Taksit tablosu."""
    __tablename__ = "installments"

    id = Column(Integer, primary_key=True)
    tuition_id = Column(Integer, ForeignKey("tuition.id"))
    installment_number = Column(Integer)
    amount = Column(Float)
    due_date = Column(DateTime)
    status = Column(String(20), default="Bekliyor")  # Bekliyor, Ödendi, Gecikmiş

    # Relationships
    tuition = relationship("Tuition", back_populates="installments")


class Scholarship(Base):
    """Burs tablosu."""
    __tablename__ = "scholarships"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    scholarship_name = Column(String(100))
    scholarship_type = Column(String(50))  # Başarı, İhtiyaç, Tam, KYK
    monthly_amount = Column(Float, default=0.0)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    status = Column(String(20), default="Aktif")  # Aktif, Pasif, Beklemede

    # Relationships
    student = relationship("Student", back_populates="scholarships")


class ScholarshipApplication(Base):
    """Burs başvuru tablosu."""
    __tablename__ = "scholarship_applications"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    scholarship_name = Column(String(100))
    application_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="Beklemede")  # Beklemede, Onaylandı, Reddedildi
    notes = Column(Text)


class AvailableScholarship(Base):
    """Başvuruya açık burslar."""
    __tablename__ = "available_scholarships"

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    description = Column(Text)
    monthly_amount = Column(Float)
    min_gpa = Column(Float)
    deadline = Column(DateTime)
    is_active = Column(Boolean, default=True)


class UserAccount(Base):
    """Kullanıcı hesap tablosu (IT)."""
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    username = Column(String(50), unique=True)
    email = Column(String(100))
    status = Column(String(20), default="Aktif")  # Aktif, Kilitli, Pasif
    last_login = Column(DateTime)
    is_locked = Column(Boolean, default=False)
    failed_attempts = Column(Integer, default=0)
    password_last_changed = Column(DateTime)
    password_expired = Column(Boolean, default=False)

    # Relationships
    student = relationship("Student", back_populates="account")


class ITTicket(Base):
    """IT destek talepleri."""
    __tablename__ = "it_tickets"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    ticket_no = Column(String(20), unique=True)
    category = Column(String(50))  # tech_support, email_support
    subject = Column(String(200))
    description = Column(Text)
    status = Column(String(20), default="Açık")  # Açık, İşlemde, Çözüldü, Kapatıldı
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    priority = Column(String(20), default="Normal")  # Düşük, Normal, Yüksek, Acil


class KnownIssue(Base):
    """Bilinen sorunlar (IT)."""
    __tablename__ = "known_issues"

    id = Column(Integer, primary_key=True)
    category = Column(String(50))
    title = Column(String(200))
    description = Column(Text)
    solution = Column(Text)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Device(Base):
    """Cihaz envanteri."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    device_type = Column(String(50))  # Laptop, Desktop, vb.
    brand = Column(String(50))
    model = Column(String(100))
    serial_no = Column(String(100))
    assigned_date = Column(DateTime)


class CourseRegistrationPeriod(Base):
    """Ders kayıt dönemi."""
    __tablename__ = "course_registration_periods"

    id = Column(Integer, primary_key=True)
    semester = Column(String(20))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=False)
