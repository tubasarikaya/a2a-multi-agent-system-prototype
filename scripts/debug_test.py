"""
Debug Test - Harç sorgulama akışını test eder.
"""
import sys
from pathlib import Path

# Proje root'unu sys.path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()


async def test_tuition_query():
    """Harç sorgusu test."""
    from main import UniversitySupportSystem

    print("\n" + "="*80)
    print("HARC SORGUSU DEBUG TESTI")
    print("="*80 + "\n")

    system = UniversitySupportSystem()
    await system.initialize()

    # Test 1: Harç borcu sorgulama
    user_id = "20220015"
    query = "Harc borcum var mi?"

    print(f"User ID: {user_id}")
    print(f"Sorgu: {query}")
    print("-"*80)

    # Keyword matching test
    query_lower = query.lower()
    harc_keywords = ["harc", "harç"]
    borc_keywords = ["borc", "borç", "var mi", "var mı", "ne kadar"]

    has_harc = any(kw in query_lower for kw in harc_keywords)
    has_borc = any(kw in query_lower for kw in borc_keywords)

    print(f"\nKeyword Analizi:")
    print(f"  query_lower: '{query_lower}'")
    print(f"  has_harc: {has_harc} (keywords: {harc_keywords})")
    print(f"  has_borc: {has_borc} (keywords: {borc_keywords})")
    print(f"  Sonuc: {has_harc and has_borc}")

    # Orchestrator'a gonder
    print("\n" + "-"*80)
    print("MainOrchestrator'a gonderiliyor...")

    response = await system.process_message(
        query,
        user_id=user_id
    )

    print("\n" + "="*80)
    print("YANIT:")
    print("="*80)
    print(response)

    # Emoji kontrolu
    emoji_check = any(ord(c) > 127 and ord(c) not in range(0x00C0, 0x024F) for c in response)
    if emoji_check:
        print("\n[UYARI] Yanıtta emoji veya özel karakter olabilir!")
    else:
        print("\n[OK] Yanıtta emoji yok.")


async def test_not_found():
    """Bulunamadı durumu test."""
    from main import UniversitySupportSystem

    print("\n" + "="*80)
    print("BULUNAMADI DURUMU DEBUG TESTI")
    print("="*80 + "\n")

    system = UniversitySupportSystem()
    await system.initialize()

    # Anlamsız/olmayan bilgi sorgusu
    user_id = "20220015"
    query = "Universite uzay programi hakkinda bilgi ver"

    print(f"User ID: {user_id}")
    print(f"Sorgu: {query}")
    print("-"*80)

    response = await system.process_message(
        query,
        user_id=user_id
    )

    print("\n" + "="*80)
    print("YANIT:")
    print("="*80)
    print(response)

    # "Bulunamadı" kontrolu
    not_found_indicators = ["bulunamadı", "bulunamadi", "bilgi yok", "mevcut değil"]
    has_not_found = any(ind in response.lower() for ind in not_found_indicators)

    if has_not_found:
        print("\n[OK] Yanıt 'bulunamadı' içeriyor.")
    else:
        print("\n[UYARI] Yanıt 'bulunamadı' içermiyor!")


async def test_multiple_departments():
    """Çoklu departman test."""
    from main import UniversitySupportSystem

    print("\n" + "="*80)
    print("COKLU DEPARTMAN DEBUG TESTI")
    print("="*80 + "\n")

    system = UniversitySupportSystem()
    await system.initialize()

    user_id = "20220015"
    query = "Harc borcum var mi ve ders kaydi yapabilir miyim?"

    print(f"User ID: {user_id}")
    print(f"Sorgu: {query}")
    print("-"*80)

    response = await system.process_message(
        query,
        user_id=user_id
    )

    print("\n" + "="*80)
    print("YANIT:")
    print("="*80)
    print(response)


async def main():
    """Ana test fonksiyonu."""
    print("\n" + "#"*80)
    print("# DEBUG TEST SUITE")
    print("#"*80)

    await test_tuition_query()
    print("\n\n")

    await test_not_found()
    print("\n\n")

    await test_multiple_departments()


if __name__ == "__main__":
    asyncio.run(main())
