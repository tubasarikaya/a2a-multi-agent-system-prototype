"""
Scholarship Agent - Burs işlemleri agentı.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class ScholarshipAgent(BaseDepartmentAgent):
    """
    Burs İşlemleri Agentı.

    Sorumluluklar:
    - Burs başvuruları
    - Burs durumu sorgulama
    - Burs kriterleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="finance_scholarship_agent",
            name="Burs İşlemleri Uzmanı",
            description="Burs başvuru ve işlemlerini yönetir",
            department="finance",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Burs agentı yetenekleri."""
        return [
            AgentSkill(
                id="scholarship_query",
                name="Burs Sorgulama",
                description="Burs durumunu sorgular",
                examples=["Burs alıyor muyum?", "Burs başvuru durumum ne?"]
            ),
            AgentSkill(
                id="scholarship_apply",
                name="Burs Başvurusu",
                description="Burs başvurusu bilgilerini verir",
                examples=["Bursa nasıl başvurabilirim?", "Hangi burslar var?"]
            ),
            AgentSkill(
                id="scholarship_criteria",
                name="Burs Kriterleri",
                description="Burs kriterlerini açıklar",
                examples=["Burs almak için şartlar neler?"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return SystemPrompts.FINANCE_SCHOLARSHIP

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Burs veritabanından bilgi çeker."""
        if not self.db:
            return None

        student_id = data.get("user_id") if data else None

        results = {}

        if student_id:
            # Aktif burs durumu
            scholarship = await self.db.get_scholarship_status(student_id)
            if scholarship:
                results["burs_durumu"] = {
                    "aktif_burs": scholarship.get("active_scholarship"),
                    "burs_turu": scholarship.get("scholarship_type"),
                    "aylik_miktar": scholarship.get("monthly_amount"),
                    "baslangic_tarihi": scholarship.get("start_date"),
                    "bitis_tarihi": scholarship.get("end_date")
                }

            # Burs başvuru durumu
            applications = await self.db.get_scholarship_applications(student_id)
            if applications:
                results["basvurular"] = applications

            # Akademik durum (burs kriteri)
            academic = await self.db.get_academic_status(student_id)
            if academic:
                results["akademik_durum"] = {
                    "gano": academic.get("gpa"),
                    "sinif": academic.get("grade")
                }

        # Mevcut burs türleri
        available = await self.db.get_available_scholarships()
        if available:
            results["mevcut_burslar"] = available

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Burs yanıtı oluşturur."""
        query_lower = query.lower()

        # Burs durumu sorgulama
        if "burs" in query_lower and ("alıyor" in query_lower or "durum" in query_lower or "var mı" in query_lower):
            if db_results and "burs_durumu" in db_results:
                burs = db_results["burs_durumu"]

                if burs.get("aktif_burs"):
                    response = f"""Burs Durumunuz:

Burs Turu: {burs.get('burs_turu', 'Bilinmiyor')}
Aylik Miktar: {burs.get('aylik_miktar', 0)} TL
Baslangic: {burs.get('baslangic_tarihi', 'Bilinmiyor')}
Bitis: {burs.get('bitis_tarihi', 'Bilinmiyor')}

Aktif burs sahibisiniz."""
                else:
                    response = "Su anda aktif bir bursunuz bulunmamaktadir."

                # Başvurular
                if "basvurular" in db_results:
                    response += "\n\nBaşvuru Durumlarınız:"
                    for app in db_results["basvurular"]:
                        response += f"\n  - {app.get('scholarship_name')}: {app.get('status')}"

                return response

            return "Burs durumunuzu öğrenmek için öğrenci numaranızla giriş yapmanız gerekmektedir."

        # Burs başvurusu
        if "burs" in query_lower and ("başvur" in query_lower or "basvur" in query_lower or "nasıl" in query_lower or "nasil" in query_lower):
            response = """Burs Basvurusu:

1. Universite Burslari:
   - OBS - Burs Islemleri - Basvuru
   - Donem basinda duyurulur

2. KYK Bursu:
   - kyk.gsb.gov.tr uzerinden basvuru
   - Genel basvuru: Agustos-Eylul

3. Ozel Burslar:
   - Vakif ve kurum burslari
   - Kariyer Merkezi duyurularini takip edin

Genel Kriterler:
- GANO sarti (genellikle 2.5+ veya 3.0+)
- Gelir duzeyi
- Disiplin cezasi almamis olmak"""

            if db_results and "mevcut_burslar" in db_results:
                response += "\n\nŞu an başvuruya açık burslar:"
                for burs in db_results["mevcut_burslar"][:5]:
                    response += f"\n  - {burs.get('name')}: {burs.get('deadline')}'e kadar"

            if db_results and "akademik_durum" in db_results:
                akademik = db_results["akademik_durum"]
                response += f"\n\nSizin GANO'nuz: {akademik.get('gano', 'Hesaplanmamış')}"

            return response

        # Burs kriterleri
        if "kriter" in query_lower or "şart" in query_lower or "sart" in query_lower:
            return """Burs Kriterleri:

1. Basari Bursu:
   - GANO: 3.50 ve uzeri
   - Disiplin cezasi olmamak
   - Normal ogrenim suresi icinde olmak

2. Ihtiyac Bursu:
   - Gelir belgesi
   - Aile durum bildirimi
   - GANO: 2.00 ve uzeri

3. Tam Burs:
   - Sinavda ilk %5'e girmek
   - GANO: 3.00 ve uzeri tutmak

4. KYK Bursu:
   - e-Devlet uzerinden basvuru
   - Gelir kriteri
   - Baska burs almiyor olmak

Detayli bilgi icin Mali Isler veya Kariyer Merkezi'ne basvurunuz."""

        # Burs ile ilgili keyword kontrolu - sadece ilgili sorgularda veri dondur
        burs_keywords = ["burs", "basvuru", "başvuru", "destek", "kriter", "sart", "şart"]
        has_relevant_keyword = any(kw in query_lower for kw in burs_keywords)

        if not has_relevant_keyword:
            return "Bu konuda ilgili bilgi bulunamadi."

        # Ilgili sorgu - RAG varsa formatla
        if rag_results:
            answer = rag_results.get("answer", "")
            sources = rag_results.get("sources", [])
            if answer and answer.strip() and sources:
                return await super().generate_agent_response(query, db_results, rag_results, data)

        if db_results:
            return self._format_db_results(db_results)

        return "Bu konuda ilgili bilgi bulunamadi."
