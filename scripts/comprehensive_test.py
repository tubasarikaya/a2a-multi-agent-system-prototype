"""
Kapsamlı Test Scripti - Tüm senaryoları test eder.
"""
import sys
from pathlib import Path

# Proje root'unu sys.path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import time
import structlog
from uuid import uuid4
from typing import List, Tuple, Dict, Optional

from main import UniversitySupportSystem

logger = structlog.get_logger()

# Test kategorileri
TEST_CATEGORIES = {
    "basit_tek_departman": [
        ("20220015", "Harç borcum var mı?"),
        ("20220015", "Ders kaydı yapabilir miyim?"),
        ("20220015", "Şifremi unuttum, ne yapmalıyım?"),
        ("20220015", "Kütüphane kurallarını öğrenebilir miyim?"),
        ("20220015", "Akademik durumumu öğrenmek istiyorum"),
        ("20220015", "Burs başvurusu yapabilir miyim?"),
        ("20220015", "Öğrenci belgesi almak istiyorum"),
    ],
    "karmasik_cok_departman": [
        ("20220015", "Harç borcum var mı? Ders kaydı yapabilir miyim?"),
        ("20220015", "Harç borcum var mı ve burs başvurusu yapabilir miyim?"),
        ("20220015", "Akademik durumumu öğrenmek istiyorum ve ders kaydı yapabilir miyim?"),
        ("20220015", "Şifremi unuttum ve e-posta sorunum var, ayrıca harç borcum var mı?"),
        ("20220015", "Kütüphane kurallarını öğrenmek istiyorum ve kitap aramak istiyorum"),
    ],
    "belirsiz_llm_gerektiren": [
        ("20220015", "Öğrenciler ne yer?"),
        ("20220015", "Kampüste nerede yemek yiyebilirim?"),
        ("20220015", "Yurt başvurusu nasıl yapılır?"),
        ("20220015", "Üniversiteye nasıl ulaşabilirim?"),
        ("20220015", "Kütüphane kuralları nelerdir?"),
        ("20220015", "Kayıt silme işlemi nasıl yapılır?"),
        ("20220015", "Ders kaydı prosedürü nedir?"),
    ],
    "anlamsiz_sorular": [
        ("20220015", "Ayşe nerede?"),
        ("20220015", "Bugün hava nasıl?"),
        ("20220015", "Kaç tane yıldız var?"),
        ("20220015", "En sevdiğin renk nedir?"),
        ("20220015", "Matematik 2+2 kaç?"),
        ("20220015", "Dünya ne kadar büyük?"),
    ],
    "eksik_parametreli": [
        (None, "Harç borcum var mı?"),  # Öğrenci ID yok
        (None, "Ders kaydı yapabilir miyim?"),  # Öğrenci ID yok
        (None, "Akademik durumumu öğrenmek istiyorum"),  # Öğrenci ID yok
        (None, "Burs başvurusu yapabilir miyim?"),  # Öğrenci ID yok
    ],
    "farkli_ogrenciler": [
        ("20210001", "Harç borcum var mı?"),  # Ahmet Yılmaz
        ("20230042", "Ders kaydı yapabilir miyim?"),  # Mehmet Kaya
        ("20190088", "Akademik durumumu öğrenmek istiyorum"),  # Fatma Şahin
        ("20220015", "Burs başvurusu yapabilir miyim?"),  # Ayşe Demir
    ],
    "karmasik_yapili": [
        ("20220015", "Harç borcum var mı ve eğer varsa ders kaydı yapabilir miyim?"),
        ("20220015", "Akademik durumum uygunsa burs başvurusu yapabilir miyim?"),
        ("20220015", "Şifremi unuttum, e-posta sorunum var ve ayrıca kütüphane kartımı kontrol etmek istiyorum"),
        ("20220015", "Ders kaydı yapmak istiyorum ama önce harç borcum var mı öğrenmek istiyorum"),
    ],
    "coklu_soru": [
        ("20220015", "Harç borcum var mı? Ders kaydı yapabilir miyim? Akademik durumum nasıl?"),
        ("20220015", "Kütüphane kuralları nelerdir? Kitap aramak istiyorum. Kütüphane kartım var mı?"),
        ("20220015", "Şifremi unuttum. E-posta sorunum var. Teknik destek alabilir miyim?"),
    ],
}


async def run_test_category(
    system: UniversitySupportSystem,
    category_name: str,
    tests: List[Tuple[Optional[str], str]]
):
    """Bir test kategorisini çalıştırır."""
    print(f"\n{'='*80}")
    print(f"KATEGORİ: {category_name.upper()}")
    print(f"{'='*80}\n")
    
    results = []
    
    for idx, (user_id, query) in enumerate(tests, 1):
        print(f"\n[TEST {idx}/{len(tests)}]")
        print(f"Kullanıcı ID: {user_id or '(Belirtilmedi)'}")
        print(f"Soru: {query}")
        print("-" * 80)
        
        start_time = time.monotonic()
        context_id = str(uuid4())
        
        try:
            response = await system.process_message(
                query,
                user_id=user_id,
                context_id=context_id
            )
            end_time = time.monotonic()
            latency_ms = round((end_time - start_time) * 1000, 2)
            
            print(f"✅ BAŞARILI (Süre: {latency_ms}ms)")
            print(f"\nYANIT:")
            print(response[:500] + ("..." if len(response) > 500 else ""))
            
            results.append({
                "status": "success",
                "latency_ms": latency_ms,
                "response_length": len(response),
                "user_id": user_id,
                "query": query
            })
            
        except Exception as e:
            end_time = time.monotonic()
            latency_ms = round((end_time - start_time) * 1000, 2)
            
            print(f"❌ HATA (Süre: {latency_ms}ms)")
            print(f"Hata: {str(e)}")
            
            results.append({
                "status": "error",
                "latency_ms": latency_ms,
                "error": str(e),
                "user_id": user_id,
                "query": query
            })
        
        # Kısa bir bekleme (rate limiting için)
        await asyncio.sleep(0.5)
    
    return results


async def run_all_tests():
    """Tüm testleri çalıştırır."""
    print("\n" + "="*80)
    print("KAPSAMLI TEST BAŞLATILIYOR")
    print("="*80)
    
    system = UniversitySupportSystem()
    await system.initialize()
    
    all_results = {}
    
    for category_name, tests in TEST_CATEGORIES.items():
        results = await run_test_category(system, category_name, tests)
        all_results[category_name] = results
    
    # Özet rapor
    print("\n\n" + "="*80)
    print("TEST ÖZET RAPORU")
    print("="*80)
    
    total_tests = 0
    total_success = 0
    total_errors = 0
    total_latency = 0
    
    for category_name, results in all_results.items():
        category_total = len(results)
        category_success = sum(1 for r in results if r["status"] == "success")
        category_errors = sum(1 for r in results if r["status"] == "error")
        category_latency = sum(r.get("latency_ms", 0) for r in results if r["status"] == "success")
        
        total_tests += category_total
        total_success += category_success
        total_errors += category_errors
        total_latency += category_latency
        
        print(f"\n{category_name}:")
        print(f"  Toplam: {category_total}")
        print(f"  Başarılı: {category_success}")
        print(f"  Hata: {category_errors}")
        if category_success > 0:
            avg_latency = category_latency / category_success
            print(f"  Ortalama Süre: {avg_latency:.2f}ms")
    
    print(f"\n{'='*80}")
    print(f"GENEL ÖZET:")
    print(f"  Toplam Test: {total_tests}")
    print(f"  Başarılı: {total_success} ({total_success/total_tests*100:.1f}%)")
    print(f"  Hata: {total_errors} ({total_errors/total_tests*100:.1f}%)")
    if total_success > 0:
        avg_latency = total_latency / total_success
        print(f"  Ortalama Süre: {avg_latency:.2f}ms")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(run_all_tests())

