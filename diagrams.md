# Mermaid Diyagramları

## 1. Genel Mimari Yapısı

```mermaid
flowchart TB
    subgraph User["Kullanıcı"]
        U[Kullanıcı Arayüzü]
    end

    subgraph MainOrch["Ana Orchestrator"]
        MO[MainOrchestrator]
        Q[InMemoryQueue]
        MO --> Q
    end

    subgraph Departments["Departmanlar"]
        subgraph IT["IT Departmanı"]
            IT_O[IT Orchestrator]
            IT_T[TechSupport Agent]
            IT_E[EmailSupport Agent]
            IT_O --> IT_T
            IT_O --> IT_E
        end

        subgraph SA["Öğrenci İşleri"]
            SA_O[StudentAffairs Orchestrator]
            SA_R[Registration Agent]
            SA_C[Course Agent]
            SA_O --> SA_R
            SA_O --> SA_C
        end

        subgraph FIN["Mali İşler"]
            FIN_O[Finance Orchestrator]
            FIN_T[Tuition Agent]
            FIN_S[Scholarship Agent]
            FIN_O --> FIN_T
            FIN_O --> FIN_S
        end

        subgraph AA["Akademik İşler"]
            AA_O[AcademicAffairs Orchestrator]
            AA_S[AcademicStatus Agent]
            AA_O --> AA_S
        end

        subgraph LIB["Kütüphane"]
            LIB_O[Library Orchestrator]
            LIB_B[Book Agent]
            LIB_O --> LIB_B
        end
    end

    subgraph Data["Veri Katmanı"]
        DB[(SQLite DB)]
        RAG[(ChromaDB RAG)]
        LLM[LLM Provider]
    end

    U --> MO
    MO --> IT_O
    MO --> SA_O
    MO --> FIN_O
    MO --> AA_O
    MO --> LIB_O

    IT_T --> DB
    IT_T --> RAG
    SA_R --> DB
    SA_C --> DB
    FIN_T --> DB
    FIN_S --> DB
    AA_S --> DB
    LIB_B --> DB
    LIB_B --> RAG

    MO --> LLM
```

## 2. A2A Protokol Yapısı

```mermaid
classDiagram
    class A2ATask {
        +task_id: str
        +context_id: str
        +from_agent: str
        +to_agent: str
        +status: TaskStatus
        +initial_message: A2AMessage
        +messages: List~A2AMessage~
        +artifacts: List~Artifact~
        +update_status()
        +add_message()
        +get_latest_message()
    }

    class A2AMessage {
        +message_id: str
        +role: MessageRole
        +parts: List~Part~
        +context_id: str
        +get_text()
        +get_data()
    }

    class A2AClient {
        +agent_id: str
        +_local_handlers: Dict
        +send_task()
        +register_local_handler()
    }

    class AgentCard {
        +agent_id: str
        +name: str
        +department: str
        +skills: List~AgentSkill~
        +capabilities: AgentCapability
    }

    class BaseAgent {
        +agent_id: str
        +llm: LLMProvider
        +rag: RAGEngine
        +process_task()
        +send_to_agent()
        +handle_task()
    }

    class DepartmentOrchestrator {
        +_sub_agents: Dict
        +register_sub_agent()
        +route_task()
    }

    A2ATask "1" --> "*" A2AMessage
    A2AClient --> A2ATask
    BaseAgent --> A2AClient
    BaseAgent --> AgentCard
    DepartmentOrchestrator --|> BaseAgent
```

## 3. Senaryo 1: Harç Borcu Sorgulama Akışı

```mermaid
sequenceDiagram
    participant U as Kullanıcı
    participant MO as MainOrchestrator
    participant Q as InMemoryQueue
    participant FO as Finance Orchestrator
    participant TA as Tuition Agent
    participant DB as SQLite DB
    participant LLM as LLM Provider

    U->>MO: "Harç borcum var mı?" (user_id: 20220015)
    activate MO

    MO->>MO: _analyze_request()
    Note over MO: Task tipi: check_fee_status<br/>Departman: finance

    MO->>Q: enqueue(task)
    Q-->>MO: task_enqueued
    MO->>Q: dequeue()
    Q-->>MO: task

    MO->>FO: send_to_agent(query, user_id)
    activate FO

    FO->>FO: route_task()
    Note over FO: Hedef: tuition_agent

    FO->>TA: send_to_agent(query, user_id)
    activate TA

    TA->>DB: get_tuition_status(20220015)
    DB-->>TA: {has_debt: true, amount: 2500}

    TA->>TA: generate_agent_response()
    TA-->>FO: "Borç: 2500 TL, Son ödeme: 15 Aralık"
    deactivate TA

    FO-->>MO: department_result
    deactivate FO

    MO->>LLM: synthesize_response()
    LLM-->>MO: formatted_response

    MO-->>U: "2500 TL harç borcunuz bulunmaktadır..."
    deactivate MO
```

## 4. Senaryo 2: Ders Kaydı (Bağımlılıklı) Akışı

```mermaid
sequenceDiagram
    participant U as Kullanıcı
    participant MO as MainOrchestrator
    participant FO as Finance Orchestrator
    participant TA as Tuition Agent
    participant AAO as Academic Orchestrator
    participant ASA as AcademicStatus Agent
    participant SAO as StudentAffairs Orchestrator
    participant CA as Course Agent
    participant DB as SQLite DB

    U->>MO: "Ders kaydı yapabilir miyim?" (user_id: 20220015)
    activate MO

    MO->>MO: _analyze_request()
    Note over MO: Task: check_course_registration<br/>Bağımlılıklar tespit edildi

    MO->>MO: _detect_and_add_dependencies()
    Note over MO: Auto-add: check_fee_status<br/>Auto-add: check_academic_status

    rect rgb(200, 230, 200)
        Note over MO,ASA: Faz 1: Bağımlılıklar (Paralel)
        par Harç Kontrolü
            MO->>FO: check_fee_status
            FO->>TA: query
            TA->>DB: get_tuition_status()
            DB-->>TA: {has_debt: false}
            TA-->>FO: "Borç yok"
            FO-->>MO: fee_result
        and Akademik Durum
            MO->>AAO: check_academic_status
            AAO->>ASA: query
            ASA->>DB: get_academic_status()
            DB-->>ASA: {gpa: 3.2, status: active}
            ASA-->>AAO: "GPA: 3.2, Aktif"
            AAO-->>MO: academic_result
        end
    end

    rect rgb(200, 200, 230)
        Note over MO,CA: Faz 2: Ana Görev (Bağımlılık sonuçlarıyla)
        MO->>SAO: check_course_registration + dependency_results
        SAO->>CA: query + dependency_results
        CA->>CA: Kontrol: borç yok ✓, GPA uygun ✓
        CA->>DB: get_course_registration_status()
        DB-->>CA: {period_open: true}
        CA-->>SAO: "Kayıt yapılabilir"
        SAO-->>MO: registration_result
    end

    MO-->>U: "Ders kaydı yapabilirsiniz. Harç borcunuz yok, GPA: 3.2"
    deactivate MO
```

## 5. Bileşen İlişki Diyagramı

```mermaid
flowchart LR
    subgraph Core["Çekirdek Katman"]
        A2A[A2A Protocol]
        Client[A2A Client]
        Registry[Agent Registry]
    end

    subgraph Agents["Agent Katmanı"]
        Base[BaseAgent]
        DeptOrch[DepartmentOrchestrator]
        DeptAgent[BaseDepartmentAgent]
    end

    subgraph Services["Servis Katmanı"]
        LLM[LLM Provider]
        RAG[RAG Engine]
        DB[Database]
        Queue[Task Queue]
    end

    subgraph External["Dış Servisler"]
        Gemini[Gemini API]
        Chroma[ChromaDB]
        SQLite[SQLite]
    end

    A2A --> Client
    Client --> Registry
    Base --> Client
    Base --> LLM
    Base --> RAG
    DeptOrch --> Base
    DeptAgent --> Base
    DeptAgent --> DB

    LLM --> Gemini
    RAG --> Chroma
    DB --> SQLite
    Queue --> Base
```

## 6. Veri Akış Diyagramı

```mermaid
flowchart TD
    subgraph Input["Giriş"]
        Query[Kullanıcı Sorgusu]
        UserID[User ID]
    end

    subgraph Processing["İşleme"]
        Analyze[Sorgu Analizi]
        Keywords[Keyword Tespiti]
        TaskType[Task Tipi Belirleme]
        Deps[Bağımlılık Çözümleme]
        Route[Departman Yönlendirme]
    end

    subgraph DataSources["Veri Kaynakları"]
        DBQuery[DB Sorgusu]
        RAGQuery[RAG Sorgusu]
    end

    subgraph Output["Çıkış"]
        Merge[Sonuç Birleştirme]
        Synth[LLM Sentezi]
        Response[Kullanıcı Yanıtı]
    end

    Query --> Analyze
    UserID --> Analyze
    Analyze --> Keywords
    Keywords --> TaskType
    TaskType --> Deps
    Deps --> Route

    Route --> DBQuery
    Route --> RAGQuery

    DBQuery --> Merge
    RAGQuery --> Merge
    Merge --> Synth
    Synth --> Response
```
