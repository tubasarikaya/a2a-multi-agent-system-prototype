"""
Email Support Agent - E-posta ve hesap destek agentı.

Şifre sıfırlama, hesap sorunları ve e-posta işlemleriyle ilgilenir.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class EmailSupportAgent(BaseDepartmentAgent):
    """
    E-posta ve Hesap Destek Agentı.

    Sorumluluklar:
    - Şifre sıfırlama
    - Hesap erişim sorunları
    - E-posta yapılandırması
    - Güvenlik sorunları
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="it_email_support",
            name="E-posta Destek Uzmanı",
            description="E-posta hesapları ve şifre işlemlerini yönetir",
            department="it",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """E-posta destek yetenekleri."""
        return [
            AgentSkill(
                id="password_reset",
                name="Şifre Sıfırlama",
                description="Kullanıcı şifrelerini sıfırlar",
                examples=["Şifremi unuttum", "Parolamı değiştirmek istiyorum"]
            ),
            AgentSkill(
                id="account_access",
                name="Hesap Erişimi",
                description="Hesap erişim sorunlarını çözer",
                examples=["Hesabıma giremiyorum", "Hesabım kilitlendi"]
            ),
            AgentSkill(
                id="email_config",
                name="E-posta Yapılandırma",
                description="E-posta ayarlarını yapılandırır",
                examples=["Outlook'a mail ekleyemiyorum", "Telefona mail kurmak istiyorum"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return SystemPrompts.IT_EMAIL_SUPPORT

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Hesap veritabanından bilgi çeker."""
        if not self.db:
            return None

        user_id = data.get("user_id") if data else None
        query_lower = query.lower()

        results = {}

        if user_id:
            # Kullanıcı hesap bilgisi
            account_info = await self.db.get_user_account(user_id)
            if account_info:
                results["hesap_durumu"] = {
                    "email": account_info.get("email"),
                    "durum": account_info.get("status"),
                    "son_giris": account_info.get("last_login"),
                    "kilitli_mi": account_info.get("is_locked", False)
                }

            # Son şifre değişikliği
            password_info = await self.db.get_password_info(user_id)
            if password_info:
                results["sifre_bilgisi"] = {
                    "son_degisiklik": password_info.get("last_changed"),
                    "suresi_doldu_mu": password_info.get("expired", False)
                }

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """E-posta/hesap destek yanıtı oluşturur."""
        query_lower = query.lower()

        # Şifre sıfırlama
        if "şifre" in query_lower and ("unuttum" in query_lower or "sıfırla" in query_lower):
            response = """Şifre sıfırlama için şu adımları izleyin:

1. https://sifre.universite.edu.tr adresine gidin
2. Öğrenci/Personel numaranızı girin
3. Kayıtlı cep telefonunuza gelen kodu girin
4. Yeni şifrenizi belirleyin

Önemli:
- Şifreniz en az 8 karakter olmalı
- Büyük harf, küçük harf ve rakam içermeli
- Sorun yaşarsanız IT Destek: 1234"""

            # Hesap durumu ekle
            if db_results and "hesap_durumu" in db_results:
                hesap = db_results["hesap_durumu"]
                if hesap.get("kilitli_mi"):
                    response += "\n\nNOT: Hesabiniz kilitli gorunuyor. Sifre sifirlama sonrasi otomatik acilacaktir."

            return response

        # Hesap kilitli
        if "kilitl" in query_lower or "giremiyorum" in query_lower:
            response = """Hesap erişim sorunu için:

1. Şifrenizi 5 kez yanlış girdiyseniz hesabınız 15 dakika kilitlenir
2. Bekleyip tekrar deneyin veya şifre sıfırlama yapın
3. Sürekli sorun yaşıyorsanız IT Destek'i arayın: 1234"""

            if db_results and "hesap_durumu" in db_results:
                hesap = db_results["hesap_durumu"]
                response += f"\n\nHesap Durumu: {'Kilitli' if hesap.get('kilitli_mi') else 'Aktif'}"
                if hesap.get("son_giris"):
                    response += f"\nSon Giriş: {hesap['son_giris']}"

            return response

        # Email/sifre ile ilgili keyword kontrolu - sadece ilgili sorgularda veri dondur
        email_keywords = ["sifre", "şifre", "parola", "email", "e-posta", "hesap", "giris", "giriş", "kilit", "unuttum"]
        has_relevant_keyword = any(kw in query_lower for kw in email_keywords)

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
