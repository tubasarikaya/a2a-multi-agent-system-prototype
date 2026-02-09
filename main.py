"""
Üniversite Kurumsal Destek Sistemi - Ana Giriş Noktası

Bu prototip, RAG destekli LLM'ler ve A2A protokolü kullanarak
çoklu-agent tabanlı kurumsal destek sistemi gösterir.
"""
import asyncio
import os
import sys
from pathlib import Path

# Proje kök dizinini Python path'e ekle
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import structlog
from dotenv import load_dotenv

# Konfigürasyon
load_dotenv()

from config.settings import settings
from database.connection import get_database
from database.seed_data import seed_database
from llm.provider import get_llm_provider
from rag.vector_store import DepartmentVectorStore
from rag.rag_engine import RAGEngine
from task_queue_module.task_queue import get_queue

# Agents
from agents.main_orchestrator import MainOrchestrator
from agents.departments.it import ITOrchestrator, TechSupportAgent, EmailSupportAgent
from agents.departments.student_affairs import StudentAffairsOrchestrator, RegistrationAgent, CourseAgent
from agents.departments.finance import FinanceOrchestrator, TuitionAgent, ScholarshipAgent
from agents.departments.academic_affairs import AcademicAffairsOrchestrator, AcademicStatusAgent
from agents.departments.library import LibraryOrchestrator, BookAgent

# Logging yapılandırması
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
)

logger = structlog.get_logger()


class UniversitySupportSystem:
    """Ana sistem sınıfı - tüm bileşenleri koordine eder."""

    def __init__(self):
        self.db = None
        self.llm = None
        self.rag_stores = None
        self.main_orchestrator = None
        self._initialized = False

    async def initialize(self):
        """Sistemi başlatır."""
        if self._initialized:
            return

        logger.info("system_initializing")

        # 1. Veritabanı
        logger.info("initializing_database")
        self.db = get_database(settings.database_url)
        seed_database(self.db)

        # 2. LLM Provider
        logger.info("initializing_llm")
        self.llm = get_llm_provider(
            google_api_key=settings.google_api_key,
            anthropic_api_key=settings.anthropic_api_key,
            primary=settings.primary_llm_provider,
            gemini_model=settings.gemini_model,
            claude_model=settings.claude_model,
            ollama_qwen_model=settings.ollama_qwen_model,
            ollama_base_url=settings.ollama_base_url,
        )

        # 3. RAG Vector Stores
        logger.info("initializing_rag")
        chroma_dir = str(settings.chroma_dir)
        self.rag_stores = DepartmentVectorStore(chroma_dir)

        # Dokümanları yükle
        data_dir = str(settings.data_dir)
        if Path(data_dir).exists():
            self.rag_stores.load_from_directory(data_dir)

        # 4. Departman RAG Engine'leri
        rag_engines = {
            "it": RAGEngine(self.llm, department_store=self.rag_stores),
            "student_affairs": RAGEngine(self.llm, department_store=self.rag_stores),
            "finance": RAGEngine(self.llm, department_store=self.rag_stores),
            "academic_affairs": RAGEngine(self.llm, department_store=self.rag_stores),
            "library": RAGEngine(self.llm, department_store=self.rag_stores)
        }

        # 5. IT Departmanı
        logger.info("initializing_it_department")
        it_orchestrator = ITOrchestrator(llm_provider=self.llm, rag_engine=rag_engines["it"])
        tech_support = TechSupportAgent(llm_provider=self.llm, rag_engine=rag_engines["it"], db_connection=self.db)
        email_support = EmailSupportAgent(llm_provider=self.llm, rag_engine=rag_engines["it"], db_connection=self.db)
        it_orchestrator.register_sub_agent(tech_support)
        it_orchestrator.register_sub_agent(email_support)

        # 6. Öğrenci İşleri Departmanı
        logger.info("initializing_student_affairs_department")
        student_orchestrator = StudentAffairsOrchestrator(llm_provider=self.llm, rag_engine=rag_engines["student_affairs"])
        registration_agent = RegistrationAgent(llm_provider=self.llm, rag_engine=rag_engines["student_affairs"], db_connection=self.db)
        course_agent = CourseAgent(llm_provider=self.llm, rag_engine=rag_engines["student_affairs"], db_connection=self.db)
        student_orchestrator.register_sub_agent(registration_agent)
        student_orchestrator.register_sub_agent(course_agent)

        # 7. Mali İşler Departmanı
        logger.info("initializing_finance_department")
        finance_orchestrator = FinanceOrchestrator(llm_provider=self.llm, rag_engine=rag_engines["finance"])
        tuition_agent = TuitionAgent(llm_provider=self.llm, rag_engine=rag_engines["finance"], db_connection=self.db)
        scholarship_agent = ScholarshipAgent(llm_provider=self.llm, rag_engine=rag_engines["finance"], db_connection=self.db)
        finance_orchestrator.register_sub_agent(tuition_agent)
        finance_orchestrator.register_sub_agent(scholarship_agent)

        # 8. Akademik İşler Departmanı
        logger.info("initializing_academic_affairs_department")
        academic_orchestrator = AcademicAffairsOrchestrator(llm_provider=self.llm, rag_engine=rag_engines["academic_affairs"])
        academic_status_agent = AcademicStatusAgent(llm_provider=self.llm, rag_engine=rag_engines["academic_affairs"], db_connection=self.db)
        academic_orchestrator.register_sub_agent(academic_status_agent)

        # 9. Kütüphane Departmanı
        logger.info("initializing_library_department")
        library_orchestrator = LibraryOrchestrator(llm_provider=self.llm, rag_engine=rag_engines["library"])
        book_agent = BookAgent(llm_provider=self.llm, rag_engine=rag_engines["library"], db_connection=self.db)
        library_orchestrator.register_sub_agent(book_agent)

        # 10. Ana Orchestrator
        logger.info("initializing_main_orchestrator")
        self.main_orchestrator = MainOrchestrator(llm_provider=self.llm)
        self.main_orchestrator.register_department(it_orchestrator)
        self.main_orchestrator.register_department(student_orchestrator)
        self.main_orchestrator.register_department(finance_orchestrator)
        self.main_orchestrator.register_department(academic_orchestrator)
        self.main_orchestrator.register_department(library_orchestrator)

        self._initialized = True
        logger.info("system_initialized", departments=["it", "student_affairs", "finance", "academic_affairs", "library"])

    async def process_message(self, message: str, user_id: str = None, context_id: str = None) -> str:
        """Kullanıcı mesajını işler."""
        if not self._initialized:
            await self.initialize()

        return await self.main_orchestrator.handle_user_message(
            message=message,
            user_id=user_id,
            context_id=context_id
        )


async def interactive_demo():
    """İnteraktif demo modu."""
    system = UniversitySupportSystem()
    await system.initialize()

    print("\n" + "="*60)
    print("Üniversite Kurumsal Destek Sistemi")
    print("A2A Protokolü ile Çoklu-Agent Mimarisi")
    print("="*60)
    print("\nÖrnek sorular:")
    print("  - Harç borcum var mı?")
    print("  - Ders kaydı yapabilir miyim?")
    print("  - Şifremi unuttum, ne yapmalıyım?")
    print("  - Burs başvurusu nasıl yapılır?")
    print("  - Harç borcum var mı? Ders kaydı yapabilir miyim?")
    print("  - GPA'm kaç?")
    print("  - Kitap ödünç almak istiyorum")
    print("\nÇıkış için 'q' veya 'quit' yazın.")
    print("Öğrenci numarası belirtmek için: /user 20220015")
    print("Öğrenci numarasını kaldırmak için: /user clear")
    print("-"*60)

    # Demo kullanıcı ID'si - başlangıçta None (sistem öğrenci numarası isteyecek)
    demo_user = None

    while True:
        try:
            print("\n")
            user_prompt = f"[Öğrenci {demo_user}]" if demo_user else "[Öğrenci numarası belirtilmedi]"
            user_input = input(f"{user_prompt} Soru: ").strip()

            if user_input.lower() in ['q', 'quit', 'exit', 'çıkış']:
                print("Güle güle!")
                break

            if not user_input:
                continue

            # Farklı kullanıcı simülasyonu
            if user_input.startswith("/user "):
                parts = user_input.split()
                if len(parts) > 1 and parts[1].lower() in ["clear", "none", "null"]:
                    demo_user = None
                    print("Öğrenci numarası kaldırıldı. Sistem artık öğrenci numarası isteyecek.")
                else:
                    demo_user = parts[1] if len(parts) > 1 else None
                    print(f"Öğrenci numarası ayarlandı: {demo_user}")
                continue

            print("\nİşleniyor...")

            # user_id'yi sadece demo_user varsa gönder
            response = await system.process_message(user_input, user_id=demo_user if demo_user else None)

            print("\n" + "-"*40)
            print("YANIT:")
            print("-"*40)
            print(response)

        except KeyboardInterrupt:
            print("\n\nKapatılıyor...")
            break
        except Exception as e:
            logger.error("demo_error", error=str(e))
            print(f"\nHata: {e}")


async def run_example_queries():
    """Örnek sorguları çalıştırır."""
    system = UniversitySupportSystem()
    await system.initialize()

    print("\n" + "="*60)
    print("Örnek Sorgular - Otomatik Demo")
    print("="*60)

    # Örnek sorgular
    queries = [
        ("20210001", "Harç borcum var mı?"),  # Ahmet - borcu yok
        ("20220015", "Harç borcum var mı? Ders kaydı yapabilir miyim?"),  # Ayşe - borcu var
        ("20220015", "Şifremi unuttum"),  # Ayşe - hesabı kilitli
        ("20210001", "Burs başvurusu nasıl yapabilirim?"),  # Ahmet
    ]

    for user_id, query in queries:
        print(f"\n{'='*60}")
        print(f"Kullanıcı: {user_id}")
        print(f"Soru: {query}")
        print("-"*60)

        try:
            response = await system.process_message(query, user_id=user_id)
            print("\nYanıt:")
            print(response)
        except Exception as e:
            print(f"Hata: {e}")

        print()


def main():
    """Ana fonksiyon."""
    import argparse

    parser = argparse.ArgumentParser(description="Üniversite Kurumsal Destek Sistemi")
    parser.add_argument(
        "--mode",
        choices=["interactive", "demo", "server"],
        default="interactive",
        help="Çalışma modu"
    )
    args = parser.parse_args()

    if args.mode == "interactive":
        asyncio.run(interactive_demo())
    elif args.mode == "demo":
        asyncio.run(run_example_queries())
    elif args.mode == "server":
        print("Server modu henüz implement edilmedi.")
        print("FastAPI server için 'uvicorn main:app' kullanın.")


if __name__ == "__main__":
    main()
