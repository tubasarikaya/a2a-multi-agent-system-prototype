"""
Tuition Agent - Harç ve ödeme işlemleri agentı.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class TuitionAgent(BaseDepartmentAgent):
    """
    Harç ve Ödeme İşlemleri Agentı.

    Sorumluluklar:
    - Harç borcu sorgulama
    - Ödeme bilgileri
    - Taksit işlemleri
    - Makbuz/dekont
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="finance_tuition_agent",
            name="Harç İşlemleri Uzmanı",
            description="Harç ve ödeme işlemlerini yönetir",
            department="finance",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Harç agentı yetenekleri."""
        return [
            AgentSkill(
                id="tuition_query",
                name="Harç Sorgulama",
                description="Harç borcu durumunu sorgular",
                examples=["Harç borcum var mı?", "Ne kadar harç ödemem gerekiyor?"]
            ),
            AgentSkill(
                id="payment_info",
                name="Ödeme Bilgisi",
                description="Ödeme yapma bilgilerini verir",
                examples=["Harç nasıl ödenir?", "Hangi bankaya yatıracağım?"]
            ),
            AgentSkill(
                id="installment",
                name="Taksit İşlemleri",
                description="Taksit bilgilerini sorgular",
                examples=["Taksitle ödeyebilir miyim?"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return SystemPrompts.FINANCE_TUITION

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Mali veritabanından bilgi çeker."""
        if not self.db:
            return None

        student_id = data.get("user_id") if data else None

        results = {}

        if student_id:
            # Harç durumu
            tuition = await self.db.get_tuition_status(student_id)
            if tuition:
                results["harc_durumu"] = {
                    "borc_var_mi": tuition.get("has_debt", False),
                    "toplam_borc": tuition.get("debt_amount", 0),
                    "son_odeme_tarihi": tuition.get("due_date"),
                    "donem": tuition.get("semester")
                }

            # Ödeme geçmişi
            payments = await self.db.get_payment_history(student_id)
            if payments:
                results["odeme_gecmisi"] = payments[-3:]  # Son 3 ödeme

            # Taksit bilgisi
            installments = await self.db.get_installment_info(student_id)
            if installments:
                results["taksit_bilgisi"] = installments

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Harç yanıtı oluşturur."""
        query_lower = query.lower()

        # Harç borcu sorgulama (ASCII ve Türkçe karakter desteği)
        harc_keywords = ["harc", "harç"]
        borc_keywords = ["borc", "borç", "var mi", "var mı", "ne kadar", "durumum", "durum"]

        has_harc = any(kw in query_lower for kw in harc_keywords)
        has_borc = any(kw in query_lower for kw in borc_keywords)

        # "Borç durumum" gibi sorularda sadece "borç" yeterli olmalı
        # "Harc borcu" gibi sorularda her ikisi de olmalı
        if has_borc and (has_harc or "durum" in query_lower or "durumum" in query_lower):
            # DB sonuçları varsa göster
            if db_results and "harc_durumu" in db_results:
                harc = db_results["harc_durumu"]

                if harc.get("borc_var_mi"):
                    response = f"""Harc Borc Durumu:

Toplam Borc: {harc.get('toplam_borc', 0)} TL
Donem: {harc.get('donem', 'Mevcut donem')}
Son Odeme Tarihi: {harc.get('son_odeme_tarihi', 'Belirtilmemis')}

Odeme Yontemleri:
1. Online: obs.universite.edu.tr - Mali Islemler - Harc Odeme
2. Banka: Ziraat Bankasi, Vakifbank, Halkbank
3. ATM: Anlasmalı banka ATM'leri

Not: Son odeme tarihinden sonra gecikme faizi uygulanir."""
                else:
                    response = """Harc Durumu:

Harc borcunuz bulunmamaktadir.

Not: Yeni donem harc tahakkuklari akademik takvime gore belirlenir."""

                # Ödeme geçmişi ekle
                if "odeme_gecmisi" in db_results:
                    response += "\n\nSon Odemeleriniz:"
                    for odeme in db_results["odeme_gecmisi"]:
                        response += f"\n  - {odeme.get('date')}: {odeme.get('amount')} TL"

                return response

            # Veritabanı yoksa - öğrenci bulunamadı veya veri yok
            user_id = data.get("user_id") if data else None
            if user_id:
                # Öğrenci ID var ama veri bulunamadı
                return f"Öğrenci numarası '{user_id}' ile ilgili harç/borç kaydı bulunamadı. Lütfen öğrenci numaranızı kontrol edin veya Mali İşler Birimi'ne başvurun."
            else:
                # Öğrenci ID yok
                return """Harc borc durumunuzu ogrenmek icin:

1. OBS: obs.universite.edu.tr - Mali Islemler
2. Mali Isler Birimi: Telefon veya yuz yuze

Ogrenci numaranizla giris yaparak guncel borc durumunuzu gorebilirsiniz."""

        # Ödeme bilgisi
        odeme_keywords = ["nasil", "nasıl", "ode", "öde", "yatir", "yatır"]
        has_nasil = any(kw in query_lower for kw in ["nasil", "nasıl"])
        has_ode = any(kw in query_lower for kw in ["ode", "öde", "yatir", "yatır"])

        if has_nasil and has_ode:
            return """Harc Odeme Yontemleri:

1. Online Odeme:
   - OBS - Mali Islemler - Harc Odeme
   - Kredi karti ile aninda odeme

2. Banka Subesi:
   - Ziraat Bankasi
   - Vakifbank
   - Halkbank
   - Ogrenci numaranizi belirtin

3. ATM:
   - Anlasmalı banka ATM'leri
   - Odemeler - Egitim Odemeleri - Universite Harc

4. Mobil Bankacilik:
   - Banka uygulamasi - Odemeler - Egitim

Dekont/makbuzunuzu saklayiniz."""

        # Taksit
        if "taksit" in query_lower:
            response = """Harc Taksitlendirme:

Taksit imkani donem basinda belirlenir. Genel bilgiler:

- Taksit sayisi: Genellikle 2-4 taksit
- Ilk taksit: Kayit doneminde
- Kalan taksitler: Belirlenen tarihlerde

Basvuru: Mali Isler Birimi'ne dilekce ile

Not: Taksitlendirme imkani ve kosullari her donem degisebilir."""

            if db_results and "taksit_bilgisi" in db_results:
                taksit = db_results["taksit_bilgisi"]
                response += f"\n\nMevcut Taksit Durumunuz:"
                for t in taksit:
                    response += f"\n  - Taksit {t.get('number')}: {t.get('amount')} TL - {t.get('status')}"

            return response

        # Harc/odeme ile ilgili keyword kontrolu - ONCE kontrol et
        harc_odeme_keywords = ["harc", "harç", "odeme", "ödeme", "borc", "borç", "taksit", "banka", "dekont", "makbuz"]
        has_relevant_keyword = any(kw in query_lower for kw in harc_odeme_keywords)

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

        return "Bu konuda ilgili bilgi bulunamadi."
