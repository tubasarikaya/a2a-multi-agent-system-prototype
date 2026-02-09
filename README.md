# Üniversite Kurumsal Destek Sistemi - A2A Protokolü ile

Bu prototip, RAG destekli LLM'ler ve Google A2A (Agent-to-Agent) protokolü kullanarak kurumsal destek ve iş akışı sistemi geliştirmeyi amaçlamaktadır.

##  Mimari Yapı

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Ana Orchestrator                             │
│                    (Host Agent / Gateway)                            │
│  - Gelen mesajları analiz eder                                       │
│  - Görevleri etiketler ve ID atar                                    │
│  - Departman orchestrator'lara dağıtır                              │
│  - Cevapları birleştirir ve kullanıcıya sunar                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ A2A Protocol
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│Bilgiİşlem Dept│  │  Öğrenci İşl. │  │  Mali İşler   │
│  Orchestrator │  │  Orchestrator │  │  Orchestrator │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
   ┌────┴────┐        ┌────┴────┐        ┌────┴────┐
   │         │        │         │        │         │
   ▼         ▼        ▼         ▼        ▼         ▼
┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐
│Teknk│  │Email│  │Kayıt│  │Ders │  │Harç │  │Burs │
│Agent│  │Agent│  │Agent│  │Agent│  │Agent│  │Agent│
└─────┘  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘
```

##  Özellikler

- **A2A Protokolü**: Google'ın Agent-to-Agent protokolü ile agentlar arası iletişim
- **RAG Desteği**: ChromaDB ile vektör tabanlı doküman arama
- **LLM Entegrasyonu**: Gemini API desteği
- **Çoklu Departman**: IT, Öğrenci İşleri, Mali İşler, Akademik İşler, Kütüphane
- **Asenkron İşleme**: QueueManager ile paralel görev yönetimi
- **Bağımlılık Yönetimi**: Otomatik task bağımlılık tespiti ve sıralama
- **Timeout/Retry/Circuit Breaker**: Hata toleransı ve dayanıklılık
- **Context ID Tracking**: Her sorgu için benzersiz context ID ile izleme
- **Çoklu soru desteği**: Birden fazla soru tek seferde cevaplanabilir
- **Bağımlılık yönetimi**: Task'lar otomatik sıralanır

## Main Orchestrator'ın görevleri

**1. İstek analizi (_analyze_request)**
Kullanıcı sorusunu analiz eder
LLM veya keyword-based yöntemle departmanları tespit eder
Çoklu soruları ayrı task'lara böler
Örnek: "Borç durumum nedir? Ders kaydı yapabilir miyim?" → 2 task

**2. Bağımlılık tespiti (_detect_and_add_dependencies)**
Task'lar arası bağımlılıkları tespit eder
Eksik bağımlılıkları otomatik ekler
Örnek: "Ders kaydı" → önce "borç kontrolü" ve "akademik durum" gerekli

**3. Task dağıtımı (_distribute_tasks)**
Task'ları ilgili departman orchestrator'larına dağıtır
Bağımlılıkları sıraya koyar (dependency resolution)
Paralel çalıştırır (bağımlılık yoksa)

**4. Yanıt sentezi (_synthesize_response)**
Departmanlardan gelen yanıtları birleştirir
LLM ile tutarlı bir cevap üretir
Çoklu sorular için her soruya ayrı bölüm oluşturur

## Veri kaynakları

**SQLite (university.db)**
Kişiye özel veriler: öğrenci borcu, notlar, kayıt durumu
Sorgu: "Borç durumum nedir?" → DB'den öğrenci borcu

**ChromaDB (RAG)**
Genel bilgi dokümanları: prosedürler, kurallar, nasıl yapılır
Sorgu: "Kayıt yenileme nasıl yapılır?" → RAG'den prosedür

**Departmanlar**
IT: Şifre sıfırlama, teknik destek, e-posta
Öğrenci İşleri: Ders kaydı, belge işlemleri, kayıt yenileme
Mali İşler: Harç borcu, burs başvurusu, ödeme
Akademik İşler: Not ortalaması, akademik durum, mezuniyet
Kütüphane: Kitap arama, kütüphane kuralları

##  Gereksinimler

- Python 3.10+
- ChromaDB
- SQLite
- LLM API Key (Gemini veya Claude)

## Kurulum

1. **Repository'yi klonlayın:**
```bash
git clone <repository-url>
cd university_support_system
```

2. **Virtual environment oluşturun:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Bağımlılıkları yükleyin:**
```bash
pip install -r requirements.txt
```

4. **Environment değişkenlerini ayarlayın:**
```bash
# .env dosyası oluşturun
GEMINI_API_KEY=your_gemini_api_key
# veya
ANTHROPIC_API_KEY=your_claude_api_key
```

5. **Veritabanını başlatın:**
```bash
python -c "from database import seed_database, get_database; seed_database(get_database())"
```

6. **RAG indeksini oluşturun:**
```bash
python rag/build_index.py
```

## Kullanım

### İnteraktif Demo

```bash
python main.py
```

### Test Scriptleri

```bash
# Async smoke test
python scripts/smoke_async.py

# Kapsamlı test
python scripts/comprehensive_test.py
```

##  Proje Yapısı

```
university_support_system/
├── agents/
│   ├── main_orchestrator.py      # Ana koordinatör
│   ├── base_agent.py              # Temel agent sınıfı
│   └── departments/               # Departman agentları
│       ├── it/
│       ├── student_affairs/
│       ├── finance/
│       ├── academic_affairs/
│       └── library/
├── a2a/                           # A2A protokol implementasyonu
├── rag/                           # RAG motoru
├── llm/                           # LLM provider'lar
├── database/                      # Veritabanı modelleri ve bağlantı
├── task_queue_module/              # Queue yönetimi
├── config/                         # Konfigürasyon
├── data/                           # RAG dokümanları
└── scripts/                        # Test scriptleri
```

##  Özellikler Detayı

### 1. Query/Request ID Yönetimi
Her kullanıcı sorgusu için benzersiz `context_id` oluşturulur ve tüm agentlar arasında taşınır.

### 2. Asenkron/Paralel Çalıştırma
- `InMemoryQueue` ile task yönetimi
- Bağımlılıkları tamamlanmış task'lar paralel çalıştırılır
- `asyncio.gather` ile concurrent execution

### 3. Timeout/Retry/Circuit Breaker
- Configurable timeout'lar
- Exponential backoff ile retry
- Circuit breaker pattern ile hata toleransı

### 4. Logging/Observability
- `structlog` ile structured logging
- `context_id`, `task_id`, `latency_ms` tracking
- Detaylı error logging

### 5. LLM Guardrails
- Karmaşık sorgular için LLM synthesis
- Basit sorgular için direkt birleştirme
- Timeout ve error handling
- Response length kontrolü

### 6. RAG Entegrasyonu
- ChromaDB ile vektör arama
- Departman bazlı collection'lar
- LLM ile formatlanmış cevaplar

##  Örnek Sorular

- "Harç borcum var mı?"
- "Ders kaydı yapabilir miyim?"
- "Şifremi unuttum, ne yapmalıyım?"
- "Kütüphane kurallarını öğrenebilir miyim?"
- "Öğrenciler ne yer?" (yemekhane bilgisi)
- "Borç durumum nedir? Bu borç ders kaydı yapmamı engeller mi? Ayrıca not ortalamamla burs başvurusu yapabilir miyim?" (çoklu soru ve bağımlılık)
- "Harç borcum var mı? Ders kaydı yapabilir miyim?" (çoklu departman)
