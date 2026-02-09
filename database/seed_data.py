"""
Seed Data - Sentetik test verileri.
"""
from datetime import datetime, timedelta
import structlog

from .connection import DatabaseConnection
from .models import (
    Student, Course, StudentCourse, Tuition, Payment, Installment,
    Scholarship, ScholarshipApplication, AvailableScholarship,
    UserAccount, ITTicket, KnownIssue, Device, CourseRegistrationPeriod
)

logger = structlog.get_logger()


def seed_database(db: DatabaseConnection):
    """Veritabanına sentetik veriler ekler."""
    session = db.get_session()

    try:
        # Mevcut verileri kontrol et
        existing = session.query(Student).first()
        if existing:
            logger.info("database_already_seeded")
            return

        # ==================== STUDENTS ====================
        students = [
            Student(
                student_id="20210001",
                full_name="Ahmet Yılmaz",
                email="ahmet.yilmaz@universite.edu.tr",
                department="Bilgisayar Mühendisliği",
                faculty="Mühendislik Fakültesi",
                grade=3,
                enrollment_year=2021,
                registration_status="Aktif",
                gpa=3.45,
                total_credits=120,
                completed_credits=90,
                current_semester=5
            ),
            Student(
                student_id="20220015",
                full_name="Ayşe Demir",
                email="ayse.demir@universite.edu.tr",
                department="Elektrik-Elektronik Mühendisliği",
                faculty="Mühendislik Fakültesi",
                grade=2,
                enrollment_year=2022,
                registration_status="Aktif",
                gpa=2.85,
                total_credits=120,
                completed_credits=60,
                current_semester=3
            ),
            Student(
                student_id="20230042",
                full_name="Mehmet Kaya",
                email="mehmet.kaya@universite.edu.tr",
                department="İşletme",
                faculty="İktisadi ve İdari Bilimler Fakültesi",
                grade=1,
                enrollment_year=2023,
                registration_status="Aktif",
                gpa=2.10,
                total_credits=120,
                completed_credits=30,
                current_semester=2
            ),
            Student(
                student_id="20190088",
                full_name="Fatma Şahin",
                email="fatma.sahin@universite.edu.tr",
                department="Tıp",
                faculty="Tıp Fakültesi",
                grade=5,
                enrollment_year=2019,
                registration_status="Aktif",
                gpa=3.78,
                total_credits=240,
                completed_credits=200,
                current_semester=9
            ),
            # Test için ek öğrenciler
            Student(
                student_id="2021001",
                full_name="Ali Özkan",
                email="ali.ozkan@universite.edu.tr",
                department="Makine Mühendisliği",
                faculty="Mühendislik Fakültesi",
                grade=2,
                enrollment_year=2021,
                registration_status="Aktif",
                gpa=2.65,
                total_credits=120,
                completed_credits=75,
                current_semester=4
            ),
            Student(
                student_id="12345",
                full_name="Zeynep Arslan",
                email="zeynep.arslan@universite.edu.tr",
                department="Psikoloji",
                faculty="Edebiyat Fakültesi",
                grade=3,
                enrollment_year=2020,
                registration_status="Aktif",
                gpa=3.20,
                total_credits=120,
                completed_credits=105,
                current_semester=6
            ),
        ]
        session.add_all(students)
        session.flush()

        # ==================== COURSES ====================
        courses = [
            Course(course_code="BLM101", course_name="Programlamaya Giriş", credits=4, department="Bilgisayar Mühendisliği", semester=1, instructor="Prof. Dr. Ali Veli"),
            Course(course_code="BLM201", course_name="Veri Yapıları", credits=4, department="Bilgisayar Mühendisliği", semester=3, instructor="Doç. Dr. Zeynep Ak", prerequisite="BLM101"),
            Course(course_code="BLM301", course_name="Veritabanı Sistemleri", credits=3, department="Bilgisayar Mühendisliği", semester=5, instructor="Dr. Öğr. Üyesi Can Demir", prerequisite="BLM201"),
            Course(course_code="BLM302", course_name="Yapay Zeka", credits=3, department="Bilgisayar Mühendisliği", semester=5, instructor="Prof. Dr. Ayşe Yıldız"),
            Course(course_code="EEE101", course_name="Elektrik Devreleri", credits=4, department="Elektrik-Elektronik Mühendisliği", semester=1, instructor="Prof. Dr. Mehmet Can"),
            Course(course_code="ISL101", course_name="İşletmeye Giriş", credits=3, department="İşletme", semester=1, instructor="Doç. Dr. Selin Ay"),
            Course(course_code="MAT101", course_name="Matematik I", credits=4, department="Ortak", semester=1, instructor="Prof. Dr. Kemal Öz"),
        ]
        session.add_all(courses)
        session.flush()

        # ==================== STUDENT COURSES ====================
        # Ahmet'in dersleri
        student_courses = [
            StudentCourse(student_id=students[0].id, course_id=courses[2].id, semester="2024-Güz", status="Devam"),
            StudentCourse(student_id=students[0].id, course_id=courses[3].id, semester="2024-Güz", status="Devam"),
            StudentCourse(student_id=students[0].id, course_id=courses[1].id, semester="2023-Güz", grade="AA", status="Tamamlandı"),
            # Ayşe'nin dersleri
            StudentCourse(student_id=students[1].id, course_id=courses[4].id, semester="2024-Güz", status="Devam"),
            StudentCourse(student_id=students[1].id, course_id=courses[6].id, semester="2024-Güz", status="Devam"),
        ]
        session.add_all(student_courses)

        # ==================== TUITION ====================
        tuitions = [
            # Ahmet - borcu yok
            Tuition(
                student_id=students[0].id,
                semester="2024-Güz",
                total_amount=5000,
                paid_amount=5000,
                has_debt=False,
                debt_amount=0,
                due_date=datetime(2024, 10, 15)
            ),
            # Ayşe - borcu var
            Tuition(
                student_id=students[1].id,
                semester="2024-Güz",
                total_amount=5000,
                paid_amount=2500,
                has_debt=True,
                debt_amount=2500,
                due_date=datetime(2024, 12, 31)
            ),
            # Mehmet - borcu yok
            Tuition(
                student_id=students[2].id,
                semester="2024-Güz",
                total_amount=4500,
                paid_amount=4500,
                has_debt=False,
                debt_amount=0,
                due_date=datetime(2024, 10, 15)
            ),
            # Ali (2021001) - borcu var
            Tuition(
                student_id=students[4].id,
                semester="2024-Güz",
                total_amount=5000,
                paid_amount=3000,
                has_debt=True,
                debt_amount=2000,
                due_date=datetime(2024, 12, 20)
            ),
            # Zeynep (12345) - borcu yok
            Tuition(
                student_id=students[5].id,
                semester="2024-Güz",
                total_amount=4800,
                paid_amount=4800,
                has_debt=False,
                debt_amount=0,
                due_date=datetime(2024, 10, 15)
            ),
        ]
        session.add_all(tuitions)
        session.flush()

        # ==================== PAYMENTS ====================
        payments = [
            Payment(tuition_id=tuitions[0].id, amount=5000, payment_date=datetime(2024, 9, 10), payment_method="Kredi Kartı", receipt_no="RCP2024001"),
            Payment(tuition_id=tuitions[1].id, amount=2500, payment_date=datetime(2024, 9, 15), payment_method="Havale", receipt_no="RCP2024002"),
            Payment(tuition_id=tuitions[2].id, amount=4500, payment_date=datetime(2024, 9, 12), payment_method="Kredi Kartı", receipt_no="RCP2024003"),
            Payment(tuition_id=tuitions[3].id, amount=3000, payment_date=datetime(2024, 9, 20), payment_method="Havale", receipt_no="RCP2024004"),
            Payment(tuition_id=tuitions[4].id, amount=4800, payment_date=datetime(2024, 9, 8), payment_method="Kredi Kartı", receipt_no="RCP2024005"),
        ]
        session.add_all(payments)

        # ==================== INSTALLMENTS ====================
        installments = [
            Installment(tuition_id=tuitions[1].id, installment_number=1, amount=2500, due_date=datetime(2024, 9, 15), status="Ödendi"),
            Installment(tuition_id=tuitions[1].id, installment_number=2, amount=2500, due_date=datetime(2024, 12, 15), status="Bekliyor"),
        ]
        session.add_all(installments)

        # ==================== SCHOLARSHIPS ====================
        scholarships = [
            # Fatma - başarı bursu
            Scholarship(
                student_id=students[3].id,
                scholarship_name="Başarı Bursu",
                scholarship_type="Başarı",
                monthly_amount=2000,
                start_date=datetime(2023, 9, 1),
                end_date=datetime(2024, 6, 30),
                status="Aktif"
            ),
        ]
        session.add_all(scholarships)

        # ==================== SCHOLARSHIP APPLICATIONS ====================
        applications = [
            ScholarshipApplication(
                student_id=students[0].id,
                scholarship_name="Araştırma Bursu",
                application_date=datetime(2024, 9, 1),
                status="Beklemede"
            ),
        ]
        session.add_all(applications)

        # ==================== AVAILABLE SCHOLARSHIPS ====================
        available = [
            AvailableScholarship(
                name="Başarı Bursu",
                description="3.50 ve üzeri GANO'ya sahip öğrenciler için",
                monthly_amount=2000,
                min_gpa=3.50,
                deadline=datetime(2024, 12, 31),
                is_active=True
            ),
            AvailableScholarship(
                name="İhtiyaç Bursu",
                description="Gelir düzeyi kriterini karşılayan öğrenciler için",
                monthly_amount=1500,
                min_gpa=2.00,
                deadline=datetime(2024, 12, 15),
                is_active=True
            ),
            AvailableScholarship(
                name="Araştırma Asistanlığı",
                description="Lisansüstü öğrenciler için araştırma desteği",
                monthly_amount=3000,
                min_gpa=3.00,
                deadline=datetime(2024, 11, 30),
                is_active=True
            ),
        ]
        session.add_all(available)

        # ==================== USER ACCOUNTS ====================
        accounts = [
            UserAccount(
                student_id=students[0].id,
                username="ahmet.yilmaz",
                email="ahmet.yilmaz@universite.edu.tr",
                status="Aktif",
                last_login=datetime(2024, 11, 20, 14, 30),
                is_locked=False,
                password_last_changed=datetime(2024, 8, 15)
            ),
            UserAccount(
                student_id=students[1].id,
                username="ayse.demir",
                email="ayse.demir@universite.edu.tr",
                status="Kilitli",
                last_login=datetime(2024, 11, 18, 9, 0),
                is_locked=True,
                failed_attempts=5,
                password_last_changed=datetime(2024, 6, 1),
                password_expired=True
            ),
            UserAccount(
                student_id=students[2].id,
                username="mehmet.kaya",
                email="mehmet.kaya@universite.edu.tr",
                status="Aktif",
                last_login=datetime(2024, 11, 19, 16, 45),
                is_locked=False,
                password_last_changed=datetime(2024, 10, 1)
            ),
            UserAccount(
                student_id=students[4].id,
                username="ali.ozkan",
                email="ali.ozkan@universite.edu.tr",
                status="Aktif",
                last_login=datetime(2024, 11, 21, 10, 15),
                is_locked=False,
                password_last_changed=datetime(2024, 9, 1)
            ),
            UserAccount(
                student_id=students[5].id,
                username="zeynep.arslan",
                email="zeynep.arslan@universite.edu.tr",
                status="Aktif",
                last_login=datetime(2024, 11, 22, 14, 20),
                is_locked=False,
                password_last_changed=datetime(2024, 8, 20)
            ),
        ]
        session.add_all(accounts)

        # ==================== IT TICKETS ====================
        tickets = [
            ITTicket(
                student_id=students[1].id,
                ticket_no="IT2024001",
                category="email_support",
                subject="Hesabım kilitlendi",
                description="5 kez yanlış şifre girdim, hesabım kilitlendi",
                status="Açık",
                priority="Yüksek"
            ),
            ITTicket(
                student_id=students[0].id,
                ticket_no="IT2024002",
                category="tech_support",
                subject="VPN bağlantı sorunu",
                description="Uzaktan VPN'e bağlanamıyorum",
                status="İşlemde",
                priority="Normal"
            ),
        ]
        session.add_all(tickets)

        # ==================== KNOWN ISSUES ====================
        known_issues = [
            KnownIssue(
                category="tech_support",
                title="VPN Yavaşlık Sorunu",
                description="Yoğun saatlerde VPN bağlantısında yavaşlık yaşanmaktadır",
                solution="Yoğun saatler dışında (09:00-18:00) bağlanmayı deneyin veya farklı sunucu seçin"
            ),
            KnownIssue(
                category="email_support",
                title="Outlook Senkronizasyon Hatası",
                description="Outlook'ta e-postalar senkronize olmayabiliyor",
                solution="Hesabı kaldırıp yeniden ekleyin veya web mail kullanın"
            ),
        ]
        session.add_all(known_issues)

        # ==================== DEVICES ====================
        devices = [
            Device(
                student_id=students[0].id,
                device_type="Laptop",
                brand="Dell",
                model="Latitude 5520",
                serial_no="ABC123456",
                assigned_date=datetime(2021, 9, 15)
            ),
        ]
        session.add_all(devices)

        # ==================== COURSE REGISTRATION PERIODS ====================
        periods = [
            CourseRegistrationPeriod(
                semester="2024-Güz",
                start_date=datetime(2024, 9, 1),
                end_date=datetime(2024, 9, 20),
                is_active=False
            ),
            CourseRegistrationPeriod(
                semester="2025-Bahar",
                start_date=datetime(2025, 1, 15),
                end_date=datetime(2025, 2, 5),
                is_active=True  # Şu an aktif
            ),
        ]
        session.add_all(periods)

        session.commit()
        logger.info("database_seeded_successfully")

    except Exception as e:
        session.rollback()
        logger.error("database_seed_error", error=str(e))
        raise
    finally:
        session.close()
