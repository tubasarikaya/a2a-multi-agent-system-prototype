"""
Academic Status Agent - Akademik durum sorgulama agentı.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class AcademicStatusAgent(BaseDepartmentAgent):
    """
    Akademik Durum Sorgulama Agentı.

    Sorumluluklar:
    - GPA/not ortalaması sorgulama
    - Kredi durumu
    - Akademik durum kontrolü
    - Mezuniyet şartları kontrolü
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="academic_status_agent",
            name="Akademik Durum Uzmanı",
            description="Akademik durum ve not ortalaması sorgular",
            department="academic_affairs",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Akademik durum agentı yetenekleri."""
        return [
            AgentSkill(
                id="gpa_query",
                name="GPA Sorgulama",
                description="Not ortalamasını sorgular",
                examples=["GPA'm kaç?", "Not ortalamam nedir?"]
            ),
            AgentSkill(
                id="credit_status",
                name="Kredi Durumu",
                description="Tamamlanan ve kalan kredileri sorgular",
                examples=["Kaç kredi tamamladım?", "Mezuniyet için kaç kredi kaldı?"]
            ),
            AgentSkill(
                id="academic_standing",
                name="Akademik Durum",
                description="Akademik durumu (aktif, şartlı, vb.) sorgular",
                examples=["Akademik durumum nedir?", "Şartlı mıyım?"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return """Sen üniversite akademik işler departmanı asistanısın.
Öğrencilerin akademik durumu, GPA, kredi durumu hakkında yardımcı oluyorsun.
Sadece verilen bilgilere dayanarak cevap ver. Emin olmadığın konularda akademik danışmana yönlendir."""

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Akademik veritabanından bilgi çeker."""
        if not self.db:
            return None

        student_id = data.get("user_id") if data else None

        results = {}

        if student_id:
            # Öğrenci bilgisi
            student = await self.db.get_student(student_id)
            if student:
                results["akademik_durum"] = {
                    "gpa": student.gpa,
                    "toplam_kredi": student.total_credits,
                    "tamamlanan_kredi": student.completed_credits,
                    "kalan_kredi": student.total_credits - student.completed_credits,
                    "donem": student.current_semester,
                    "kayit_durumu": student.registration_status,
                    "bolum": student.department,
                    "fakulte": student.faculty
                }

                # Akademik durum kontrolü
                if student.gpa < 2.0:
                    results["akademik_durum"]["durum"] = "Şartlı"
                    results["akademik_durum"]["uyari"] = "GPA 2.0'ın altında, şartlı durumdasınız."
                else:
                    results["akademik_durum"]["durum"] = "Normal"

                # Ders kaydı yapabilir mi?
                results["akademik_durum"]["ders_kaydi_yapabilir"] = student.gpa >= 2.0

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Akademik durum yanıtı oluşturur."""
        query_lower = query.lower()

        # Akademik durum sorgulama
        if db_results and "akademik_durum" in db_results:
            durum = db_results["akademik_durum"]

            # GPA sorgulama
            if "gpa" in query_lower or "not ortalaması" in query_lower or "not ortalamasi" in query_lower or "ortalama" in query_lower:
                gpa = durum.get("gpa", "Bilinmiyor")
                status = durum.get("durum", "Normal")

                response = f"""Akademik Durum Raporu:

Not Ortalamasi (GPA): {gpa}
Akademik Durum: {status}
Bolum: {durum.get('bolum', 'Bilinmiyor')}
Donem: {durum.get('donem', 'Bilinmiyor')}

Kredi Durumu:
- Toplam Gereken: {durum.get('toplam_kredi', 0)} kredi
- Tamamlanan: {durum.get('tamamlanan_kredi', 0)} kredi
- Kalan: {durum.get('kalan_kredi', 0)} kredi"""

                if durum.get("uyari"):
                    response += f"\n\nUyari: {durum['uyari']}"

                return response

            # Genel akademik durum
            if "akademik durum" in query_lower or "akademik" in query_lower:
                gpa = durum.get("gpa", 0)
                can_register = durum.get("ders_kaydi_yapabilir", False)

                response = f"""Akademik Durum Ozeti:

GPA: {gpa}
Durum: {durum.get('durum', 'Normal')}
Kayit Durumu: {durum.get('kayit_durumu', 'Bilinmiyor')}

Ders Kaydi: {'Yapabilirsiniz' if can_register else 'Yapamazsiniz (GPA < 2.0)'}

Kredi Bilgisi:
- Tamamlanan: {durum.get('tamamlanan_kredi', 0)} / {durum.get('toplam_kredi', 0)}
- Kalan: {durum.get('kalan_kredi', 0)} kredi"""

                if durum.get("uyari"):
                    response += f"\n\nUyari: {durum['uyari']}"

                return response

        # Akademik ile ilgili keyword kontrolu - ONCE kontrol et
        akademik_keywords = ["akademik", "gpa", "ortalama", "not", "kredi", "donem", "dönem", "mezuniyet", "durum"]
        has_relevant_keyword = any(kw in query_lower for kw in akademik_keywords)

        # Keyword eslesmiyor - ilgisiz sorgu
        if not has_relevant_keyword:
            return "Bu konuda ilgili bilgi bulunamadi."

        # RAG sonucu var mi kontrol et
        if rag_results:
            answer = rag_results.get("answer", "")
            sources = rag_results.get("sources", [])
            if answer and answer.strip() and sources:
                return await super().generate_agent_response(query, db_results, rag_results, data)

        # DB verisi varsa formatla
        if db_results:
            return self._format_db_results(db_results)

        # Genel bilgi
        return """Akademik durumunuzu ogrenmek icin:

1. OBS: obs.universite.edu.tr - Ogrenci Bilgileri - Akademik Durum
2. Transkript: OBS - Belgelerim - Transkript

Not Ortalamasi (GPA) hesaplamasi:
- Tum derslerinizin agirlikli ortalamasi
- 4.0 uzerinden degerlendirilir
- 2.0 alti: Sartli durum
- 3.0 ve uzeri: Iyi
- 3.5 ve uzeri: Cok iyi

Detayli bilgi icin akademik danismaniniza basvurabilirsiniz."""
