# UniversitySupportSystem – Detaylı Açıklama

## Proje Amacı
Bu proje, **"RAG Destekli LLM'lerle Türkçe Soru-Cevap Sistemleri"** ile **"A2A Protokolü ile Kurumsal Destek ve İş Akışı Sistemi"** konularının birleşimidir. Üniversite destek hizmetlerini (harç, kayıt, IT, kütüphane vb.) çoklu agent mimarisi ile otomatize eder; Türkçe doğal dil sorularına RAG+LLM ile yanıt verir, kişiye özgü verileri DB'den çeker ve A2A protokolü ile agent'lar arası koordinasyonu sağlar.

---

Bu belge, UniversitySupportSystem prototipinin bileşenlerini (A2A, queue, RAG, LLM, DB, orchestrator ve agent katmanları) ayrıntılı olarak açıklar ve sistemde veri/karar akışının nasıl yönetildiğini özetler.

## 1. Genel Mimari
- **Ana Orchestrator (MainOrchestrator)**: Kullanıcı sorgusunu alır, görevleri çıkarır, bağımlılıkları uygular, departman orchestrator’larına dağıtır ve sonuçları sentezler.
- **Departman Orchestrator’ları**: Departman içi alt agent’lara görev yönlendirir, sonuçları birleştirir.
- **Departman Agent’ları**: DB ve RAG kullanarak departman bazlı işi yapar, yanıt üretir. LLM departman seviyesinde kapalıdır (deterministik akış).
- **A2A Protokolü**: Agent’lar arası mesajlaşma; `A2ATask` yapısı, `A2AClient` ile local veya HTTP üzerinden çağrı.
- **Queue**: Şu an in-process `InMemoryQueue`; ready görevler enqueue/dequeue edilip aynı proses/loop içinde çalıştırılır (temel paralellik). Redis ve ayrı worker desteği için `task_queue_module` hazır.
- **DB Katmanı (SQLAlchemy + SQLite)**: Canlı, kişiye özgü veriler (harç borcu, ödeme geçmişi, akademik durum, ders kayıt durumu vb.) burada tutulur. Karar/hesaplamalar DB verisi ve kodla yapılır.
- **RAG Katmanı (Chroma)**: Departman dokümanları (prosedür, SSS, kural metinleri) vektör aramasıyla çekilir. Yanıt için LLM devre dışı (`use_llm=False`); doküman bağlamı direkt dönülür.
- **LLM**: Ana orchestrator’da yanıt sentezi ve görev analizi fallback için kullanılır (kontrollü). Departman seviyesinde kapalı.

## 2. Veri / Karar Akışı
- **Canlı veri**: DB’den gelir. Harç, ödeme, GPA, ders kaydı açık mı, akademik durum vb. her zaman DB sorgusu + iş kuralı ile sonuçlanır.
- **Kural / prosedür / SSS**: RAG’den gelir. Prosedür anlatımı, başvuru adımları, şifre sıfırlama yönergeleri vb. için RAG dokümanları kullanılır; karar vermez, sadece bilgi verir.
- **Karar mantığı**: Kod + DB verisi. Örneğin ders kaydı: harç borcu yok + GPA uygun + kayıt dönemi açık → kayıt yapılabilir; aksi durumda gerekçe belirtir.
- **LLM kullanımı**:
  - Ana orchestrator yanıt sentezinde: Departman yanıtları yeniden ifade edilir, yeni bilgi eklemez. Uzun yanıtlar 1200 karakterde kısaltılır.
  - Görev analizi fallback (keyword yetmezse): JSON şeması ile hangi departman/görev gerektiğini tahmin etmek için kullanılabilir (kontrollü).
  - Departman agent’larında kapalı; metin üretimi DB/RAG ile deterministik.

## 3. Kuyruklama (Queue)
- **Mevcut durum**: `InMemoryQueue` ile ready görevler enque/deque edilip aynı event loop’ta çalışıyor; loglarda `task_enqueued` / `task_dequeued` görülüyor.
- **Sınırlar**: Ayrı worker/proses yok; Redis veya gerçek asenkron tüketim henüz yok. Fail/ack/visibility timeout gibi gelişmiş mekanizma yok.
- **Hazır altyapı**: `task_queue_module/task_queue.py` (InMemory/Redis), `worker.py` (QueueWorker/MultiQueueWorker) ileride gerçek kuyruk/worker için kullanılabilir.

## 4. A2A Protokolü
- **`a2a/protocol.py`**: `A2ATask`, `A2AMessage`, `TaskStatus`; görev yaşam döngüsü (submitted, working, completed, failed).
- **`a2a/client.py`**: Lokal handler (aynı proses) veya HTTP ile agent'a `send_task`; paralel gönderim yardımcıları (`send_tasks_parallel`); task status/cancel yardımcıları.
- **Agent kartları** (`a2a/agent_card.py`): Agent yetenekleri, endpoint, meta; registry ile orchestrator alt-üst ilişki kurar.
- **Mevcut çalışma modu**: Şu an **local handler** modunda çalışıyor; agent'lar `register_local_handler()` ile birbirine kaydedilip aynı process içinde doğrudan çağrılıyor (HTTP kullanılmıyor). Dağıtık senaryo için `a2a/server.py` HTTP server altyapısı hazır.

## 5. Orchestrator Mantığı
- **MainOrchestrator**:
  - Görev çıkarımı: keyword tabanlı; bağımlılık metadata’sı (örn. ders kaydı → harç + akademik durum) otomatik eklenir.
  - Bağımlılık yürütme: Topological sıralama; bağımlılık sonuçları sonraki görevlere `dependency_results` ile aktarılır.
  - Kuyruk: Ready görevler `InMemoryQueue`’ya konur, hemen çekilip paralel çalıştırılır.
  - Yanıt sentezi: Departman yanıtlarını LLM ile yeniden ifade eder (mevcut bilgilerle sınırlı), uzunluk sınırı uygular.
- **Department Orchestrator**:
  - Gelen görevi ilgili alt agent’a yönlendirir (`route_task`).
  - Alt agent sonuçlarını birleştirir, `combined_result` döner.

## 6. Agent Seviyesi
- **BaseDepartmentAgent**:
  - `process_task`: DB sorgusu (`query_database`), RAG sorgusu (`use_llm=False`), deterministik yanıt (LLM kapalı).
  - `generate_agent_response`: DB varsa formatlı döner; DB yoksa RAG cevabı; yoksa “bilgi bulunamadı”.
- **Örnekler**:
  - AcademicStatusAgent: `db.get_student`, `get_academic_status`; GPA ve kayıt uygunu kodla hesaplanır.
  - TuitionAgent: `get_tuition_status`, `get_payment_history`; borç, ödeme geçmişi DB’den.
  - CourseAgent: Ders kaydı durumu, harç/gpa kontrolü için `dependency_results` veya DB.

## 7. RAG Katmanı
- **vector_store.py**: Chroma koleksiyonları (departman bazlı), embedding modeli `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Metadatalar temizlenerek ekleniyor.
- **rag_engine.py**: Arama + (opsiyonel) LLM cevabı; biz departmanlarda `use_llm=False` kullanıyoruz, sadece bağlamı dönüyor.
- **build_index.py**: `python -m rag.build_index` ile `data/` içindeki `.txt` dokümanları paragraflara bölüp koleksiyonları yeniden oluşturur.
- **Veri kaynağı**: `data/` altındaki departman txt’leri; Chroma klasörü `settings.chroma_dir`.

## 8. LLM Katmanı
- Sağlayıcı: `llm/provider.py` (Gemini öncelikli, Claude yedek). Yanıt sentezinde ana orchestrator kullanır.
- Departman LLM devre dışı (deterministik). İstenirse sadece biçimlendirme için açılabilir, karar için değil.
- Yanıt kısaltma: 1200 karakter üstü kesilerek uyarı eklenir (sentez çıktısında).

## 9. DB Katmanı
- **connection.py**: SQLAlchemy + SQLite, singleton `get_database`. Örnek metotlar:
  - Öğrenci: `get_student`, `get_student_info`, `get_academic_status`, `get_current_courses`, `get_course_registration_status`.
  - Harç: `get_tuition_status`, `get_payment_history`, `get_installment_info`.
  - IT: cihaz, ticket, bilinen sorun sorguları.
- **seed_data.py**: Sentetik veriler (harç borcu 2500 TL vs.) demo için yükleniyor.

## 10. Kuyruk ve Zamanlama Notları
- Şu an görevler aynı proses içinde kuyruklanıp anında tüketiliyor; bekleme veya backpressure yok.
- Timeout/retry: `BaseAgent.send_to_agent` içinde (default 10s, 2 retry, backoff 0.5s). Circuit breaker basit sayaçla var.
- Gelişmiş kuyruk/worker istenirse: `task_queue_module`’deki `QueueWorker` + RedisQueue devreye alınmalı.

## 11. LLM/RAG Kullanım İlkeleri (Projede Uygulanan)
- **LLM**: Karar/veri değil, ifade/sentez için; departman seviyesinde kapalı. Ana orchestrator sentezde mevcut bilgiyi yeniden anlatır, yeni bilgi eklemez.
- **RAG**: Kural/prosedür/FAQ metinleri için; canlı veri veya karar için kullanılmaz. `use_llm=False` ile halüsinasyon riski yok.
- **DB**: Kişiye özgü, anlık gerçek durum; tüm kritik kararlar DB verisi + kodla yapılır.

## 12. Bilinen Sınırlar / Yapılabilecekler
- Kuyruk: In-process; Redis + ayrı worker’a geçilerek gerçek asenkron, ack/retry/visibility eklenebilir.
- Embedding indirimi: İlk çalıştırmada internet yoksa gecikme; modeli lokal cache’e almak veya offline path belirtmek başlangıç süresini kısaltır.
- Observability: Log var, ancak metrik/trace yok; eklenebilir.
- LLM sentezi uzun yanıtlar üretebilir; uzunluk sınırı var ama istenirse daha düşük tutulabilir veya tekrar kapatılabilir.

## 13. Çalıştırma / Test
- Ana sistem: `python -m scripts.smoke_async` (iki paralel sorgu: harç+ders kaydı, şifre reset).
- RAG yeniden indeks: `python -m rag.build_index`.
- Demo CLI: `python main.py` (interactive).

Bu yapı, prototip seviyesinde A2A + RAG + LLM + DB bileşenlerini doğru ayrımla kullanır: canlı veriler ve kararlar DB/kod üzerinden, kural/prosedür bilgisi RAG’den, LLM ise yalnızca ifade/sentez amacıyla ana orchestrator katmanında. separate worker/redis ve lokal embedding cache gibi iyileştirmeler ileride eklenebilir.

