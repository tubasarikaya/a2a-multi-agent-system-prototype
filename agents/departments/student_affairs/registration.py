"""
Registration Agent - Kayıt ve belge işlemleri agentı.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class RegistrationAgent(BaseDepartmentAgent):
    """
    Kayıt ve Belge İşlemleri Agentı.

    Sorumluluklar:
    - Öğrenci belgesi
    - Transkript
    - Kayıt işlemleri
    - Mezuniyet işlemleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="student_registration_agent",
            name="Kayıt ve Belge Uzmanı",
            description="Öğrenci kayıt ve belge işlemlerini yönetir",
            department="student_affairs",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Kayıt agentı yetenekleri."""
        return [
            AgentSkill(
                id="student_document",
                name="Öğrenci Belgesi",
                description="Öğrenci belgesi düzenler",
                examples=["Öğrenci belgesi almak istiyorum"]
            ),
            AgentSkill(
                id="transcript",
                name="Transkript",
                description="Not dökümü belgesi düzenler",
                examples=["Transkript almak istiyorum"]
            ),
            AgentSkill(
                id="registration_status",
                name="Kayıt Durumu",
                description="Kayıt durumunu sorgular",
                examples=["Kaydım aktif mi?", "Kayıt durumumu öğrenmek istiyorum"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return SystemPrompts.STUDENT_REGISTRATION

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Öğrenci veritabanından bilgi çeker."""
        if not self.db:
            return None

        student_id = data.get("user_id") if data else None
        query_lower = query.lower()

        results = {}

        if student_id:
            # Öğrenci temel bilgileri
            student_info = await self.db.get_student_info(student_id)
            if student_info:
                results["ogrenci_bilgisi"] = {
                    "ad_soyad": student_info.get("full_name"),
                    "bolum": student_info.get("department"),
                    "fakulte": student_info.get("faculty"),
                    "sinif": student_info.get("grade"),
                    "kayit_durumu": student_info.get("registration_status"),
                    "giris_yili": student_info.get("enrollment_year")
                }

            # Akademik durum
            academic_status = await self.db.get_academic_status(student_id)
            if academic_status:
                results["akademik_durum"] = {
                    "gano": academic_status.get("gpa"),
                    "toplam_kredi": academic_status.get("total_credits"),
                    "tamamlanan_kredi": academic_status.get("completed_credits"),
                    "donem": academic_status.get("current_semester")
                }

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Kayıt/belge yanıtı oluşturur."""
        query_lower = query.lower()

        # Önce RAG sonuçlarını kontrol et (kurallar, prosedürler, nasıl yapılır soruları için)
        # Base class'taki _format_rag_results metodu zaten RAG sonuçlarını formatlıyor
        # Burada özel bir şey yapmaya gerek yok, base class'a bırak

        # Öğrenci belgesi
        if "öğrenci belgesi" in query_lower:
            response = """Öğrenci belgesi almak için:

1. E-Devlet üzerinden: turkiye.gov.tr → Öğrenci Belgesi Sorgulama
2. OBS üzerinden: obs.universite.edu.tr → Belgelerim → Öğrenci Belgesi
3. Öğrenci İşleri'nden: Kimlik ibrazı ile (1-2 iş günü)

E-Devlet ve OBS'den alınan belgeler karekodlu ve resmi geçerliliğe sahiptir."""

            if db_results and "ogrenci_bilgisi" in db_results:
                ogrenci = db_results["ogrenci_bilgisi"]
                response += f"\n\nKayıt Durumunuz: {ogrenci.get('kayit_durumu', 'Bilinmiyor')}"

            return response

        # Transkript
        if "transkript" in query_lower:
            response = """Transkript (not dökümü) almak için:

1. OBS üzerinden: obs.universite.edu.tr → Belgelerim → Transkript
2. Öğrenci İşleri'nden: Resmi mühürlü transkript (3-5 iş günü)

Not: Resmi kurumlara verilecek transkriptler için mühürlü belge gerekebilir."""

            if db_results and "akademik_durum" in db_results:
                akademik = db_results["akademik_durum"]
                response += f"\n\nMevcut GANO: {akademik.get('gano', 'Hesaplanmamış')}"
                response += f"\nTamamlanan Kredi: {akademik.get('tamamlanan_kredi', 0)}"

            return response

        # Kayıt silme, kayıt dondurma gibi işlemler
        if "kayıt" in query_lower and ("sil" in query_lower or "dondur" in query_lower or "iptal" in query_lower):
            # Base class'taki _format_rag_results zaten RAG sonuçlarını formatlıyor
            # Eğer RAG sonucu varsa base class handle edecek, yoksa fallback bilgi ver
            if not rag_results or not rag_results.get("answer"):
                # Fallback: Genel bilgi
                response = """Kayıt silme/dondurma işlemleri için:
            
1. Öğrenci İşleri Daire Başkanlığı'na başvurun
2. Gerekli belgeler:
   - Dilekçe
   - Kimlik fotokopisi
   - Öğrenci belgesi
   
3. İşlem süresi: 5-7 iş günü

ÖNEMLİ: Kayıt silme işlemi geri alınamaz. Lütfen dikkatli karar verin.

Detaylı bilgi için: ogrenciisleri@universite.edu.tr veya 1234 (dahili)"""
                
                if db_results and "ogrenci_bilgisi" in db_results:
                    ogrenci = db_results["ogrenci_bilgisi"]
                    response += f"\n\nMevcut Kayıt Durumunuz: {ogrenci.get('kayit_durumu', 'Bilinmiyor')}"
                
                return response

        # Kayıt durumu
        if "kayıt" in query_lower and ("durum" in query_lower or "aktif" in query_lower):
            if db_results and "ogrenci_bilgisi" in db_results:
                ogrenci = db_results["ogrenci_bilgisi"]
                return f"""Kayıt durumunuz aşağıdaki gibidir:

Ad Soyad: {ogrenci.get('ad_soyad', 'Bilinmiyor')}
Bölüm: {ogrenci.get('bolum', 'Bilinmiyor')}
Fakülte: {ogrenci.get('fakulte', 'Bilinmiyor')}
Sınıf: {ogrenci.get('sinif', 'Bilinmiyor')}
Kayıt Durumu: {ogrenci.get('kayit_durumu', 'Bilinmiyor')}
Giriş Yılı: {ogrenci.get('giris_yili', 'Bilinmiyor')}"""

            return "Kayıt durumunuzu sorgulamak için öğrenci numaranızla giriş yapmanız gerekmektedir."

        # Kayit/belge ile ilgili keyword kontrolu - sadece ilgili sorgularda veri dondur
        kayit_keywords = ["kayit", "kayıt", "belge", "transkript", "mezuniyet", "durum", "aktif"]
        has_relevant_keyword = any(kw in query_lower for kw in kayit_keywords)

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
    
    def _format_db_results(self, results: Dict[str, Any]) -> str:
        """Veritabanı sonuçlarını formatlar."""
        if not results:
            return "Veri bulunamadı."

        lines = []
        for key, value in results.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  - {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)
