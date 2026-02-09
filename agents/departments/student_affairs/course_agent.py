"""
Course Agent - Ders işlemleri agentı.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class CourseAgent(BaseDepartmentAgent):
    """
    Ders İşlemleri Agentı.

    Sorumluluklar:
    - Ders kaydı
    - Ders programı
    - Not sorgulama
    - Akademik takvim
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="student_course_agent",
            name="Ders İşlemleri Uzmanı",
            description="Ders kaydı ve akademik işlemleri yönetir",
            department="student_affairs",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Ders agentı yetenekleri."""
        return [
            AgentSkill(
                id="course_registration",
                name="Ders Kaydı",
                description="Ders kaydı işlemlerini yönetir",
                examples=["Ders kaydı yapabilir miyim?", "Ders eklemek istiyorum"]
            ),
            AgentSkill(
                id="course_info",
                name="Ders Bilgisi",
                description="Ders bilgilerini sorgular",
                examples=["Bu dersin ön koşulu ne?", "Ders saatleri"]
            ),
            AgentSkill(
                id="grades",
                name="Not Sorgulama",
                description="Ders notlarını sorgular",
                examples=["Notlarımı görmek istiyorum"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return SystemPrompts.STUDENT_COURSE

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Ders veritabanından bilgi çeker."""
        if not self.db:
            return None

        student_id = data.get("user_id") if data else None
        query_lower = query.lower()

        results = {}

        if student_id:
            # Ders kaydı durumu
            registration_status = await self.db.get_course_registration_status(student_id)
            if registration_status:
                results["kayit_durumu"] = {
                    "kayit_acik_mi": registration_status.get("is_open"),
                    "kayit_baslangic": registration_status.get("start_date"),
                    "kayit_bitis": registration_status.get("end_date"),
                    "onay_durumu": registration_status.get("approval_status")
                }

            # Mevcut dersler
            current_courses = await self.db.get_current_courses(student_id)
            if current_courses:
                results["mevcut_dersler"] = current_courses

            # Akademik durum (ders kaydı için)
            academic_status = await self.db.get_academic_status(student_id)
            if academic_status:
                results["akademik_durum"] = {
                    "gano": academic_status.get("gpa"),
                    "donem": academic_status.get("current_semester"),
                    "max_kredi": academic_status.get("max_credits", 30),
                    "alinan_kredi": academic_status.get("current_credits", 0)
                }

            # Harç durumu (ders kaydı için önemli)
            tuition_status = await self.db.get_tuition_status(student_id)
            if tuition_status:
                results["harc_durumu"] = {
                    "borc_var_mi": tuition_status.get("has_debt", False),
                    "borc_miktari": tuition_status.get("debt_amount", 0)
                }

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        dependency_results: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Ders işlemleri yanıtı oluşturur.

        dependency_results: Bağımlılık sonuçları (check_fee_status, check_academic_status)
        """
        query_lower = query.lower()

        # Ders kaydı yapabilir miyim?
        if "ders kaydı" in query_lower or "ders kayıt" in query_lower or "ders kaydi" in query_lower:
            response_parts = []
            can_register = True

            # 1. Harc kontrolu - Once bagimlilik sonuclarindan, yoksa db'den
            harc_ok = True
            fee_result = dependency_results.get("check_fee_status") if dependency_results else None

            if fee_result and fee_result.get("status") == "completed":
                # Bagimlilik sonucu var
                fee_data = fee_result.get("data", {})
                has_debt = fee_data.get("has_debt", False)
                debt_amount = fee_data.get("debt_amount", 0)

                if has_debt:
                    harc_ok = False
                    can_register = False
                    response_parts.append(f"[X] HARC BORCU: {debt_amount} TL borcunuz bulunmaktadir.")
                    response_parts.append("    -> Ders kaydi icin once harc borcunuzun odenmesi gerekir.")
                else:
                    response_parts.append("[+] Harc durumu: Borcunuz bulunmamaktadir.")
            elif db_results and "harc_durumu" in db_results:
                # Fallback: db sonucu
                harc = db_results["harc_durumu"]
                if harc.get("borc_var_mi"):
                    harc_ok = False
                    can_register = False
                    response_parts.append(f"[X] HARC BORCU: {harc.get('borc_miktari', 0)} TL borcunuz bulunmaktadir.")
                    response_parts.append("    -> Ders kaydi icin once harc borcunuzun odenmesi gerekir.")
                else:
                    response_parts.append("[+] Harc durumu: Borcunuz bulunmamaktadir.")

            # 2. Akademik durum kontrolu - Once bagimlilik sonuclarindan
            academic_ok = True
            academic_result = dependency_results.get("check_academic_status") if dependency_results else None

            if academic_result and academic_result.get("status") == "completed":
                # Bagimlilik sonucu var
                academic_data = academic_result.get("data", {})
                gpa = academic_data.get("gpa", 0)
                can_register_academic = academic_data.get("ders_kaydi_yapabilir", True)

                if not can_register_academic or gpa < 2.0:
                    academic_ok = False
                    can_register = False
                    response_parts.append(f"[X] AKADEMIK DURUM: GPA {gpa} (minimum 2.0 gerekli)")
                    response_parts.append("    -> Akademik durumunuz ders kaydi icin uygun degil.")
                else:
                    response_parts.append(f"[+] Akademik durum: GPA {gpa} - Uygun")
            elif db_results and "akademik_durum" in db_results:
                # Fallback: db sonucu
                akademik = db_results["akademik_durum"]
                gpa = akademik.get("gano", 0)
                if gpa < 2.0:
                    academic_ok = False
                    can_register = False
                    response_parts.append(f"[X] AKADEMIK DURUM: GPA {gpa} (minimum 2.0 gerekli)")
                else:
                    response_parts.append(f"[+] Akademik durum: GPA {gpa} - Uygun")

            # 3. Kayit donemi kontrolu
            if db_results and "kayit_durumu" in db_results:
                kayit = db_results["kayit_durumu"]
                if kayit.get("kayit_acik_mi"):
                    response_parts.append(f"[+] Ders kayit donemi aciktir.")
                    response_parts.append(f"    Bitis: {kayit.get('kayit_bitis', 'Bilinmiyor')}")
                else:
                    can_register = False
                    response_parts.append("[X] Ders kayit donemi su an kapalidir.")
                    if kayit.get("kayit_baslangic"):
                        response_parts.append(f"    Sonraki donem: {kayit.get('kayit_baslangic')}")

            # 4. Sonuc ozeti
            response_parts.append("\n" + "=" * 40)
            if can_register:
                response_parts.append("SONUC: Ders kaydi yapabilirsiniz.")
                response_parts.append("OBS: obs.universite.edu.tr - Ders Kaydi")
            else:
                response_parts.append("SONUC: Ders kaydi su an yapilamaz.")
                if not harc_ok:
                    response_parts.append("    -> Once harc borcunuzu odeyin.")
                if not academic_ok:
                    response_parts.append("    -> Akademik danismaninizla gorusun.")

            return "\n".join(response_parts) if response_parts else await super().generate_agent_response(query, db_results, rag_results, data)

        # Not sorgulama
        if "not" in query_lower and ("sorgula" in query_lower or "görmek" in query_lower):
            response = """Notlarınızı görmek için:

1. OBS: obs.universite.edu.tr → Not Bilgileri
2. E-Devlet: turkiye.gov.tr → Yükseköğretim Not Bilgisi

Not girişleri final döneminden sonra yapılır."""

            if db_results and "mevcut_dersler" in db_results:
                dersler = db_results["mevcut_dersler"]
                response += f"\n\nBu dönem aldığınız ders sayısı: {len(dersler)}"

            return response

        # Ders ile ilgili keyword kontrolu - sadece ilgili sorgularda veri dondur
        ders_keywords = ["ders", "kayit", "kayıt", "not", "program", "kredi", "sinav", "sınav", "final", "vize"]
        has_relevant_keyword = any(kw in query_lower for kw in ders_keywords)

        if not has_relevant_keyword:
            # Ilgisiz sorgu - "bulunamadi" don
            return "Bu konuda ilgili bilgi bulunamadi."

        # Ilgili sorgu - RAG varsa formatla, yoksa DB'den
        if rag_results:
            answer = rag_results.get("answer", "")
            sources = rag_results.get("sources", [])
            if answer and answer.strip() and sources:
                return await super().generate_agent_response(query, db_results, rag_results, data)

        # DB sonuclarini formatla
        if db_results:
            return self._format_db_results(db_results)

        return "Bu konuda ilgili bilgi bulunamadi."
