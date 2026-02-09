"""
Basit async smoke test:
- Sorgu 1: Harç + ders kaydı (harç/gpa bağımlılık zinciri)
- Sorgu 2: Şifre sıfırlama (IT)

Çalıştırma:
    python -m scripts.smoke_async
"""
import asyncio
import time

from main import UniversitySupportSystem


QUERIES = [
    ("20220015", "Harç borcum var mı? Ders kaydı yapabilir miyim?"),
    ("20220099", "Şifremi unuttum, ne yapmalıyım?")
]


async def run_smoke():
    system = UniversitySupportSystem()
    await system.initialize()

    async def run_query(user_id: str, message: str):
        t0 = time.perf_counter()
        try:
            resp = await system.process_message(message, user_id=user_id)
            elapsed = (time.perf_counter() - t0) * 1000
            return {"user": user_id, "ok": True, "ms": round(elapsed, 2), "resp": resp[:2000]}
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return {"user": user_id, "ok": False, "ms": round(elapsed, 2), "error": str(e)}

    results = await asyncio.gather(*[run_query(u, q) for u, q in QUERIES])
    for r in results:
        if r["ok"]:
            print(f"[OK] user={r['user']} time_ms={r['ms']} resp_preview={r['resp']}")
        else:
            print(f"[ERR] user={r['user']} time_ms={r['ms']} error={r['error']}")


if __name__ == "__main__":
    asyncio.run(run_smoke())

