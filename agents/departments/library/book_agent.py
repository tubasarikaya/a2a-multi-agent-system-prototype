"""
Book Agent - Kitap işlemleri agentı.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class BookAgent(BaseDepartmentAgent):
    """
    Kitap İşlemleri Agentı.

    Sorumluluklar:
    - Kitap arama
    - Ödünç alma bilgisi
    - İade ve uzatma
    - Kütüphane kartı işlemleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="library_book_agent",
            name="Kitap İşlemleri Uzmanı",
            description="Kitap arama ve ödünç işlemlerini yönetir",
            department="library",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Kitap agentı yetenekleri."""
        return [
            AgentSkill(
                id="book_search",
                name="Kitap Arama",
                description="Kütüphanede kitap arar",
                examples=["Python kitabı var mı?", "Veri yapıları kitabı ara"]
            ),
            AgentSkill(
                id="borrow_info",
                name="Ödünç Alma Bilgisi",
                description="Ödünç alma kuralları hakkında bilgi verir",
                examples=["Kaç kitap ödünç alabilirim?", "Ödünç süresi ne kadar?"]
            ),
            AgentSkill(
                id="library_card",
                name="Kütüphane Kartı",
                description="Kütüphane kartı işlemleri",
                examples=["Kütüphane kartı nasıl alınır?"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return """Sen üniversite kütüphanesi asistanısın.
Kitap arama, ödünç alma, iade ve kütüphane kartı işlemlerinde yardımcı oluyorsun.
Kütüphane kuralları hakkında doğru bilgi ver."""

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Kütüphane veritabanından bilgi çeker."""
        # Şimdilik mock veri
        return {
            "kutuphane_kurallari": {
                "max_kitap": 5,
                "odunc_suresi_gun": 14,
                "uzatma_hakki": 2,
                "gecikme_ucreti_gun": 1.0
            }
        }

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Kütüphane yanıtı oluşturur."""
        query_lower = query.lower()

        # Base class'taki _format_rag_results zaten RAG sonuçlarını formatlıyor
        # Özel durumlar için kontrol et, yoksa base class'a bırak

        # Kitap arama
        if "kitap" in query_lower and ("ara" in query_lower or "bul" in query_lower or "var mı" in query_lower):
            return """Kitap Arama:

Kutuphane katalogunda kitap aramak icin:

1. Online Katalog: kutuphane.universite.edu.tr
   - Baslik, yazar veya ISBN ile arama
   - Rafta mevcut durumunu gorme
   - Rezervasyon yapabilme

2. Mobil Uygulama: Kutuphane uygulamasi
   - QR kod ile kitap bilgisi
   - Odunc aldiklarinizi takip

3. Kutuphanede:
   - Bilgi masasindan yardim alabilirsiniz
   - Self-servis terminalleri kullanabilirsiniz

Odunc Kurallari:
- Maksimum 5 kitap
- 14 gun odunc suresi
- 2 kez uzatma hakki"""

        # Ödünç bilgisi
        if "ödünç" in query_lower or "odunc" in query_lower or "kaç kitap" in query_lower:
            rules = db_results.get("kutuphane_kurallari", {}) if db_results else {}
            return f"""Odunc Alma Kurallari:

Maksimum Kitap Sayisi: {rules.get('max_kitap', 5)} adet
Odunc Suresi: {rules.get('odunc_suresi_gun', 14)} gun
Uzatma Hakki: {rules.get('uzatma_hakki', 2)} kez
Gecikme Ucreti: {rules.get('gecikme_ucreti_gun', 1.0)} TL/gun

Odunc Alma Adimlari:
1. Kutuphane kartinizla giris yapin
2. Kitabi self-servis cihazina okutun
3. Kartinizi okutun
4. Islem tamamlandi!

Not: Geciken kitaplar yeni odunc almayi engeller."""

        # Kütüphane kuralları, prosedürler - Base class RAG'i handle edecek
        # Eğer RAG sonucu yoksa fallback bilgi ver
        if ("kural" in query_lower or "prosedür" in query_lower or "prosedur" in query_lower) and (not rag_results or not rag_results.get("answer")):
            # Fallback: Genel bilgi
            return """Kutuphane Kurallari ve Prosedurler:

Genel Kurallar:
- Sessiz calisma ortami korunmalidir
- Yemek ve icecek getirilmemelidir
- Cep telefonu sessiz modda olmalidir
- Kitaplar dikkatli kullanilmalidir

Odunc Alma:
- Maksimum 5 kitap
- 14 gun odunc suresi
- 2 kez uzatma hakki

Detayli bilgi icin: kutuphane.universite.edu.tr veya kutuphane bilgi masasi"""

        # Kütüphane kartı
        if "kart" in query_lower or "üyelik" in query_lower or "uyelik" in query_lower:
            return """Kutuphane Karti Islemleri:

Yeni Kart:
1. Ogrenci Isleri'nden onayli ogrenci belgesi alin
2. Kutuphane Uyelik Masasi'na basvurun
3. Fotografli kimlik gosterin
4. Kartiniz aninda verilir

Not: Ogrenci kimlik kartiniz kutuphane karti olarak da kullanilabilir.

Kayip/Calinti:
- Hemen kutuphanaye bildirin
- Yeni kart ucreti: 25 TL

Calisma Saatleri:
- Hafta ici: 08:00 - 22:00
- Hafta sonu: 10:00 - 18:00
- Sinav donemi: 24 saat acik"""

        # Kutuphane ile ilgili keyword kontrolu - ONCE kontrol et
        kutuphane_keywords = ["kutuphane", "kütüphane", "kitap", "odunc", "ödünç", "kart", "uyelik", "üyelik", "iade", "calisma"]
        has_relevant_keyword = any(kw in query_lower for kw in kutuphane_keywords)

        # Keyword eslesmiyor - ilgisiz sorgu
        if not has_relevant_keyword:
            return "Bu konuda ilgili bilgi bulunamadi."

        # RAG sonucu var mi kontrol et
        if rag_results:
            answer = rag_results.get("answer", "")
            sources = rag_results.get("sources", [])
            if answer and answer.strip() and sources:
                return await super().generate_agent_response(query, db_results, rag_results, data)

        # Genel kutuphane bilgisi
        return """Kutuphane Hizmetleri:

- Kitap arama ve odunc alma
- Calisma alanlari
- Bireysel calisma odalari (rezervasyon gerekli)
- Bilgisayar kullanimi
- Fotokopi ve baski hizmetleri

Online: kutuphane.universite.edu.tr
Telefon: 4567 (dahili)
E-posta: kutuphane@universite.edu.tr"""
