"""
Main Orchestrator - Ana koordinatör agent.

Gelen istekleri analiz eder, görevlere ayırır ve
departman orchestrator'larına dağıtır.
"""
import asyncio
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
import structlog

from a2a.protocol import (
    A2ATask,
    TaskStatus,
    TaskLabel,
    create_response,
    create_error_response,
    create_task,
    create_message,
    MessageRole,
    Artifact,
    TextPart
)
from a2a.agent_card import AgentSkill, agent_registry
from a2a.client import A2AClient
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine
from .base_agent import BaseAgent, DepartmentOrchestrator
from task_queue_module.task_queue import InMemoryQueue

logger = structlog.get_logger()


# Departman anahtar kelimeleri (ASCII ve Türkçe karakter alternatifleri)
DEPARTMENT_KEYWORDS = {
    "it": [
        "şifre", "sifre", "parola", "password", "e-posta", "email", "mail",
        "bilgisayar", "laptop", "yazıcı", "yazici", "printer", "internet",
        "wifi", "vpn", "sistem", "erişim", "erisim", "hesap", "kullanıcı", "kullanici",
        "teknik", "destek", "it", "bilgi işlem", "bilgi islem"
    ],
    "student_affairs": [
        "ders", "kayıt", "kayit", "transkript", "belge", "öğrenci", "ogrenci",
        "diploma", "mezuniyet", "devamsızlık", "devamsizlik", "not", "sınav", "sinav",
        "dönem", "donem", "danışman", "danisman", "bölüm", "bolum", "fakülte", "fakulte",
        "kayıt dondurma", "kayit dondurma", "yatay geçiş", "yatay gecis", "çift anadal", "cift anadal",
        "yemek", "yemekhane", "kafeterya", "kantin", "yemek yeri", "ne yer", "ne içer", "yemek menüsü", "yemek menusu",
        "barınma", "barinma", "yurt", "konaklama", "oda", "kampüs", "kampus", "ulaşım", "ulasim"
    ],
    "academic_affairs": [
        "akademik", "gpa", "akademik durum", "akademik durumu",
        "not ortalaması", "not ortalamasi", "kredi", "dönem", "donem", "mezuniyet şartı", "mezuniyet sarti"
    ],
    "finance": [
        "harç", "harc", "ödeme", "odeme", "borç", "borc", "burs", "kredi", "fatura",
        "ücret", "ucret", "para", "mali", "finans", "taksit", "indirim",
        "banka", "dekont", "makbuz"
    ],
    "library": [
        "kitap", "kütüphane", "kutuphane", "kütüphane kartı", "kutuphane karti", "ödünç", "odunc",
        "library", "iade", "uzatma", "rezervasyon"
    ]
}

# Task tipleri ve anahtar kelimeleri (ASCII ve Türkçe karakter alternatifleri)
TASK_TYPE_KEYWORDS = {
    "check_fee_status": ["harç", "harc", "borç", "borc", "harç borcu", "harc borcu", "ödeme durumu", "odeme durumu"],
    "check_course_registration": ["ders kaydı", "ders kaydi", "kayıt yap", "kayit yap", "ders al"],
    "check_academic_status": ["akademik durum", "gpa", "not ortalaması", "not ortalamasi", "akademik"],
    "check_payment_status": ["ödeme", "odeme", "ödedim", "odedim", "ödeme yaptım", "odeme yaptim"],
    "password_reset": ["şifre", "sifre", "parola", "şifre sıfırla", "sifre sifirla", "şifremi unuttum", "sifremi unuttum"],
    "check_scholarship": ["burs", "burs başvurusu", "burs basvurusu", "burs durumu"],
    "search_book": ["kitap", "kitap ara", "kitap bul"],
    "check_library_card": ["kütüphane kartı", "kutuphane karti", "kart durumu"]
}

# Task bağımlılık metadata'sı
TASK_DEPENDENCIES = {
    "check_course_registration": [
        {"task_type": "check_fee_status", "department": "finance"},
        {"task_type": "check_academic_status", "department": "academic_affairs"}
    ],
    "check_payment_status": [
        {"task_type": "check_fee_status", "department": "finance"}
    ],
    "check_scholarship": [
        {"task_type": "check_academic_status", "department": "academic_affairs"}
    ]
}

# Task type'lar için gerekli parametreler
TASK_REQUIRED_PARAMS = {
    "check_fee_status": ["student_id"],
    "check_course_registration": ["student_id"],
    "check_academic_status": ["student_id"],
    "check_payment_status": ["student_id"],
    "password_reset": ["student_id"],  # veya username/email
    "check_scholarship": ["student_id"],
    "search_book": [],  # Genel bilgi, öğrenci numarası gerekmez
    "check_library_card": ["student_id"]  # Kişisel bilgi için
}

# Parametre isimleri (kullanıcıya sorulurken)
PARAM_DISPLAY_NAMES = {
    "student_id": "öğrenci numarası",
    "username": "kullanıcı adı",
    "email": "e-posta adresi"
}


class MainOrchestrator(BaseAgent):
    """
    Ana Orchestrator - Sistemin giriş noktası.

    - Gelen mesajları analiz eder
    - Görevleri etiketler ve departmanlara ayırır
    - Paralel olarak departmanlara dağıtır
    - Sonuçları birleştirir ve kullanıcıya sunar
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="main_orchestrator",
            name="Ana Koordinatör",
            description="Gelen istekleri analiz edip departmanlara dağıtan ana koordinatör",
            department=None,
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

        # Departman orchestrator'ları
        self._department_orchestrators: Dict[str, DepartmentOrchestrator] = {}
        # Basit in-memory queue (Redis'e geçiş için aynı arayüz korunabilir)
        self._queue = InMemoryQueue()
        # Timeout / retry ayarları
        self._send_timeout = 10
        self._send_retries = 2
        self._send_backoff = 0.5

    def _get_skills(self) -> list[AgentSkill]:
        """Ana orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="analyze_request",
                name="İstek Analizi",
                description="Kullanıcı isteğini analiz eder ve görevlere ayırır",
                examples=[
                    "Harç borcum var mı?",
                    "Ders kaydı yapabilir miyim?",
                    "Şifremi unuttum"
                ]
            ),
            AgentSkill(
                id="distribute_tasks",
                name="Görev Dağıtımı",
                description="Görevleri ilgili departmanlara dağıtır"
            ),
            AgentSkill(
                id="synthesize_response",
                name="Yanıt Sentezi",
                description="Departman yanıtlarını birleştirip kullanıcıya sunar"
            )
        ]

    def register_department(self, orchestrator: DepartmentOrchestrator):
        """Departman orchestrator kaydeder."""
        dept = orchestrator.department
        self._department_orchestrators[dept] = orchestrator

        # Lokal handler olarak kaydet
        self.register_peer(orchestrator.agent_id, orchestrator.handle_task)

        logger.info(
            "department_registered",
            department=dept,
            orchestrator_id=orchestrator.agent_id
        )

    def get_department_orchestrator(self, department: str) -> Optional[DepartmentOrchestrator]:
        """Departman orchestrator döndürür."""
        return self._department_orchestrators.get(department)

    async def process_task(self, task: A2ATask) -> A2ATask:
        """
        Ana işlem akışı:
        1. İsteği analiz et
        2. Görevlere ayır ve etiketle
        3. Departmanlara dağıt
        4. Sonuçları birleştir
        """
        user_query = task.initial_message.get_text()
        user_data = task.initial_message.get_data()
        # context_id yoksa üret (query_id olarak)
        if not task.context_id:
            task.context_id = str(uuid.uuid4())

        logger.info(
            "processing_request",
            task_id=task.task_id,
            query=user_query[:100],
            context_id=task.context_id
        )

        # user_id'yi data'dan al
        user_id = user_data.get("user_id") if user_data else None

        # 1. İsteği analiz et
        analysis = await self._analyze_request(user_query, user_data, user_id, context_id=task.context_id)

        if not analysis["tasks"]:
            return create_response(
                task,
                "İsteğinizi anlayamadım. Lütfen daha açık bir şekilde belirtir misiniz?"
            )

        # 1.5. Eksik parametreleri kontrol et
        missing_params = analysis.get("missing_params", {})
        if missing_params:
            # Eksik parametreleri kullanıcıdan sor
            missing_list = []
            for task_type, params in missing_params.items():
                for param in params:
                    display_name = PARAM_DISPLAY_NAMES.get(param, param)
                    missing_list.append(display_name)
            
            # Tekrarları kaldır
            missing_list = list(set(missing_list))
            missing_text = ", ".join(missing_list)
            
            response_text = f"İsteğinizi işlemek için şu bilgilere ihtiyacım var: {missing_text}.\n\nLütfen bu bilgileri belirtir misiniz? (Örnek: 'Öğrenci numaram 20220015' veya '20220015 numaralı öğrenci için')"
            
            # INPUT_REQUIRED status ile döndür
            task.update_status(TaskStatus.INPUT_REQUIRED)
            response_message = create_message(
                role=MessageRole.AGENT,
                text=response_text,
                data={"missing_params": missing_params, "required_for_tasks": list(missing_params.keys())},
                context_id=task.context_id
            )
            task.add_message(response_message)
            return task

        # 1.6. Eğer user_id yoksa ama extracted_student_id varsa, onu kullan
        if not user_id:
            extracted_id = self._extract_student_id(user_query)
            if extracted_id:
                user_id = extracted_id
                logger.info("student_id_extracted", student_id=user_id, context_id=task.context_id)

        # 2. Görevleri departmanlara dağıt
        department_results = await self._distribute_tasks(
            analysis["tasks"],
            context_id=task.context_id,
            parent_task_id=task.task_id,
            user_id=user_id
        )

        # 3. Sonuçları birleştir
        final_response = await self._synthesize_response(
            user_query=user_query,
            analysis=analysis,
            department_results=department_results,
            context_id=task.context_id
        )

        # Artifact olarak detaylı bilgi ekle
        artifact = self.create_artifact(
            name="task_details",
            content=json.dumps({
                "analysis": analysis,
                "department_results": [
                    {
                        "department": r["department"],
                        "status": r["status"],
                        "response": r["response"][:200] if r["response"] else None
                    }
                    for r in department_results
                ]
            }, ensure_ascii=False, indent=2)
        )

        result = create_response(task, final_response)
        result.add_artifact(artifact)

        return result

    async def _analyze_request(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        İsteği analiz eder ve görevlere ayırır.

        Üç aşama:
        1. Task tipi tespiti (anahtar kelime tabanlı)
        2. Bağımlılık tespiti ve otomatik ekleme
        3. Topological sort ile sıralama
        """
        import uuid

        query_lower = query.lower()
        tasks = []
        detected_task_types = set()

        # 1. Task tiplerini tespit et
        for task_type, keywords in TASK_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    detected_task_types.add(task_type)
                    break

        # 2. Her task için departman ve detayları belirle
        task_to_department = {
            "check_fee_status": "finance",
            "check_course_registration": "student_affairs",
            "check_academic_status": "academic_affairs",
            "check_payment_status": "finance",
            "password_reset": "it",
            "check_scholarship": "finance",
            "search_book": "library",
            "check_library_card": "library"
        }

        for task_type in detected_task_types:
            department = task_to_department.get(task_type)
            if department:
                tasks.append({
                    "task_id": str(uuid.uuid4()),
                    "department": department,
                    "task_type": task_type,
                    "query": query,
                    "priority": 3,
                    "dependencies": []
                })

        # 3. Hiç task tespit edilmediyse veya belirsizlik varsa LLM ile analiz et
        if not tasks or self._is_query_ambiguous(query, detected_task_types):
            # LLM ile daha iyi anlama
            if self.llm:
                try:
                    llm_analysis = await self._analyze_by_llm(query, data, context_id=context_id)
                    if llm_analysis.get("tasks"):
                        # LLM'in bulduğu task'ları kullan
                        tasks = []
                        for t in llm_analysis["tasks"]:
                            # Department adını normalize et (Türkçe → İngilizce)
                            dept = self._normalize_department_name(t.get("department", "student_affairs"))
                            tasks.append({
                                "task_id": str(uuid.uuid4()),
                                "department": dept,
                                "task_type": t.get("task_type", "query"),
                                "query": t.get("query", query),
                                "priority": t.get("priority", 3),
                                "dependencies": t.get("depends_on", [])
                            })
                        logger.info("llm_analysis_used", 
                                  query=query[:100],
                                  tasks_found=len(tasks),
                                  context_id=context_id)
                except Exception as e:
                    logger.warning("llm_analysis_failed", error=str(e), context_id=context_id)
                    # Fallback: keyword-based
                    if not tasks:
                        keyword_departments = self._analyze_by_keywords(query)
                        for dept in keyword_departments:
                            tasks.append({
                                "task_id": str(uuid.uuid4()),
                                "department": dept,
                                "task_type": "query",
                                "query": query,
                                "priority": 3,
                                "dependencies": []
                            })
            else:
                # LLM yoksa keyword-based fallback
                if not tasks:
                    keyword_departments = self._analyze_by_keywords(query)
                    for dept in keyword_departments:
                        tasks.append({
                            "task_id": str(uuid.uuid4()),
                            "department": dept,
                            "task_type": "query",
                            "query": query,
                            "priority": 3,
                            "dependencies": []
                        })

        # 4. Bağımlılıkları tespit et ve otomatik ekle
        tasks = self._detect_and_add_dependencies(tasks, query, context_id=context_id)

        # 5. Kullanıcı sorusundan öğrenci numarasını çıkarmaya çalış
        extracted_student_id = self._extract_student_id(query)
        # user_id yoksa extracted'i kullan
        effective_user_id = user_id or extracted_student_id
        
        # 6. Gerekli parametreleri kontrol et ve eksikleri tespit et
        missing_params = self._check_required_params(tasks, query, effective_user_id, data)

        logger.info(
            "request_analyzed",
            detected_tasks=len(tasks),
            task_types=[t["task_type"] for t in tasks],
            missing_params=missing_params,
            extracted_student_id=extracted_student_id,
            context_id=context_id
        )

        return {
            "analysis": f"Tespit edilen görevler: {', '.join([t['task_type'] for t in tasks])}",
            "tasks": tasks,
            "missing_params": missing_params
        }

    def _detect_and_add_dependencies(
        self,
        tasks: List[Dict[str, Any]],
        query: str,
        context_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Task bağımlılıklarını otomatik tespit et ve eksik bağımlılıkları ekle.

        Örnek: check_course_registration için check_fee_status ve
        check_academic_status otomatik eklenir.
        """
        import uuid

        existing_task_types = {t["task_type"] for t in tasks}
        new_tasks = []

        task_to_department = {
            "check_fee_status": "finance",
            "check_course_registration": "student_affairs",
            "check_academic_status": "academic_affairs",
            "check_payment_status": "finance",
            "password_reset": "it",
            "check_scholarship": "finance"
        }

        for task in tasks:
            task_type = task["task_type"]

            # Metadata'dan bağımlılıkları kontrol et
            if task_type in TASK_DEPENDENCIES:
                dependencies = TASK_DEPENDENCIES[task_type]
                task["dependencies"] = dependencies.copy()

                # Eksik bağımlılıkları otomatik ekle
                for dep in dependencies:
                    dep_task_type = dep["task_type"]
                    if dep_task_type not in existing_task_types:
                        new_task = {
                            "task_id": str(uuid.uuid4()),
                            "department": dep["department"],
                            "task_type": dep_task_type,
                            "query": query,
                            "priority": 2,  # Bağımlılıklar öncelikli
                            "dependencies": []
                        }
                        new_tasks.append(new_task)
                        existing_task_types.add(dep_task_type)

                        logger.info(
                            "dependency_auto_added",
                            parent_task=task_type,
                            dependency=dep_task_type,
                            context_id=context_id
                        )

        # Yeni task'ları başa ekle (önce çalışmaları için)
        return new_tasks + tasks

    def _check_required_params(
        self,
        tasks: List[Dict[str, Any]],
        query: str,
        user_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """
        Task'lar için gerekli parametreleri kontrol eder ve eksikleri tespit eder.
        
        Returns:
            {
                "task_type": ["missing_param1", "missing_param2"]
            }
        """
        missing_params = {}
        
        # user_id zaten _analyze_request içinde extracted_student_id ile birleştirilmiş olabilir
        # Ama burada da kontrol edelim
        effective_student_id = user_id
        
        for task in tasks:
            task_type = task.get("task_type")
            if not task_type or task_type not in TASK_REQUIRED_PARAMS:
                continue
            
            required = TASK_REQUIRED_PARAMS[task_type]
            missing = []
            
            for param in required:
                if param == "student_id":
                    if not effective_student_id:
                        missing.append(param)
                elif param == "username":
                    # Username kontrolü (şimdilik basit)
                    if not data or not data.get("username"):
                        missing.append(param)
                elif param == "email":
                    # Email kontrolü (şimdilik basit)
                    if not data or not data.get("email"):
                        missing.append(param)
            
            if missing:
                missing_params[task_type] = missing
        
        return missing_params

    def _extract_student_id(self, query: str) -> Optional[str]:
        """
        Kullanıcı sorusundan öğrenci numarasını çıkarmaya çalışır.
        
        Örnekler:
        - "20220015 numaralı öğrenci"
        - "Öğrenci no: 20220015"
        - "20220015"
        """
        # Öğrenci numarası genellikle 8-10 haneli sayı
        # Pattern: 4 haneli yıl + 4-6 haneli numara
        patterns = [
            r'\b(\d{8})\b',  # 8 haneli: 20220015
            r'\b(\d{10})\b',  # 10 haneli
            r'öğrenci\s*(?:no|numarası|numara)?\s*:?\s*(\d{8,10})',
            r'numara\s*:?\s*(\d{8,10})',
            r'(\d{4})\s*\d{4,6}',  # Yıl + numara
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                student_id = match.group(1) if match.lastindex else match.group(0)
                # 8-10 haneli sayı kontrolü
                if len(student_id) >= 8 and len(student_id) <= 10:
                    return student_id
        
        return None

    def _analyze_by_keywords(self, query: str) -> List[str]:
        """Anahtar kelime tabanlı departman tespiti."""
        query_lower = query.lower()
        matched_departments = []

        for dept, keywords in DEPARTMENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    if dept not in matched_departments:
                        matched_departments.append(dept)
                    break

        return matched_departments if matched_departments else ["student_affairs"]

    def _normalize_department_name(self, dept: str) -> str:
        """
        Departman adını normalize eder (Türkçe → İngilizce).
        LLM bazen Türkçe döndürebilir, sistem İngilizce bekliyor.
        """
        dept_lower = dept.lower().strip()
        
        # Türkçe → İngilizce mapping
        dept_mapping = {
            "kütüphane": "library",
            "kutuphane": "library",
            "it": "it",
            "bilgi işlem": "it",
            "teknoloji": "it",
            "öğrenci işleri": "student_affairs",
            "ogrenci isleri": "student_affairs",
            "mali işler": "finance",
            "mali isler": "finance",
            "akademik işler": "academic_affairs",
            "akademik isler": "academic_affairs"
        }
        
        # Mapping'de varsa döndür
        if dept_lower in dept_mapping:
            return dept_mapping[dept_lower]
        
        # Zaten İngilizce ise olduğu gibi döndür
        valid_departments = ["it", "student_affairs", "finance", "academic_affairs", "library"]
        if dept_lower in valid_departments:
            return dept_lower
        
        # Bulunamazsa default
        logger.warning("unknown_department_normalized", original=dept, normalized="student_affairs")
        return "student_affairs"

    def _is_query_ambiguous(self, query: str, detected_task_types: set) -> bool:
        """
        Sorgunun belirsiz olup olmadığını kontrol eder.
        Belirsiz sorgular LLM ile analiz edilmeli.
        """
        query_lower = query.lower()
        
        # Belirsizlik göstergeleri
        ambiguous_indicators = [
            "nasıl", "neden", "ne zaman", "nerede", "kim", "ne", "nedir",
            "öğrenebilir miyim", "öğrenmek istiyorum", "bilgi almak",
            "kurallar", "prosedür", "süreç", "nasıl yapılır",
            "silebilir miyim", "yapabilir miyim", "edebilir miyim",
            "ne yer", "ne içer", "ne yapılır", "ne yapabilirim",
            "hangi", "hangisi", "nerelerde", "kimler"
        ]
        
        # Belirsiz kelimeler varsa veya hiç task tespit edilmemişse
        has_ambiguous = any(indicator in query_lower for indicator in ambiguous_indicators)
        no_task_detected = len(detected_task_types) == 0
        
        return has_ambiguous or no_task_detected

    async def _analyze_by_llm(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """LLM ile detaylı analiz - karmaşık/ambiguos sorular için."""
        prompt = f"""Kullanıcı isteği: "{query}"

{f'Ek veri: {json.dumps(data, ensure_ascii=False)}' if data else ''}

Bu isteği DETAYLICA ANALİZ ET ve hangi departmanların hangi işlemleri yapması gerektiğini belirle.
Soruyu anlamak için bağlamı dikkate al:
- "Öğrenciler ne yer?" → Yemekhane/kafeterya bilgisi → student_affairs departmanı
- "Kütüphane kuralları?" → Kütüphane bilgisi → library departmanı
- "Harç borcum var mı?" → Mali durum → finance departmanı
- "Ders kaydı yapabilir miyim?" → Kayıt işlemi → student_affairs departmanı

ÖNEMLİ: Departman adlarını MUTLAKA İNGİLİZCE olarak yaz (Türkçe değil!):
- "it" (IT/Bilgi İşlem departmanı için - şifre, e-posta, teknik destek)
- "student_affairs" (Öğrenci İşleri için - kayıt, belge, yemekhane, yurt, kampüs bilgileri)
- "finance" (Mali İşler için - harç, burs, ödeme)
- "academic_affairs" (Akademik İşler için - notlar, akademik durum, mezuniyet)
- "library" (Kütüphane için - kitap, kütüphane kuralları, ödünç alma)

Mevcut departmanlar ve görev tipleri:
- IT (it): password_reset, tech_support, email_support, query
- Öğrenci İşleri (student_affairs): check_course_registration, student_registration, query
  → Ayrıca: yemekhane, kafeterya, yurt, kampüs, ulaşım gibi genel bilgiler için "query" kullan
- Mali İşler (finance): check_fee_status, check_payment_status, check_scholarship, query
- Akademik İşler (academic_affairs): check_academic_status, query
- Kütüphane (library): search_book, check_library_card, query

ÖNEMLİ KURALLAR:
1. "department" alanını MUTLAKA İngilizce yaz: "it", "student_affairs", "finance", "academic_affairs", "library"
2. "kurallar", "prosedür", "nasıl yapılır", "öğrenebilir miyim", "ne yer", "ne içer", "nerede" gibi sorular için "query" task_type kullan
3. "silebilir miyim", "yapabilir miyim" gibi sorular için uygun task_type belirle
4. "query" alanında kullanıcının tam sorusunu kopyala (değiştirme)
5. Yemekhane, kafeterya, yurt, kampüs gibi genel bilgiler için "student_affairs" departmanını kullan

ÖNEMLİ: Eğer kullanıcı BİRDEN FAZLA soru soruyorsa, HER SORU İÇİN AYRI TASK OLUŞTUR!

ÇOKLU SORU TESPİTİ (Her türlü çoklu soru için geçerli):
- Birden fazla "?" işareti varsa → Çoklu soru
- "ayrıca", "ve", "ile", "hem", "hem de", "bir de", "aynı zamanda", "bunun yanında" gibi bağlaçlar varsa → Çoklu soru
- Farklı konular hakkında sorular varsa → Çoklu soru (ör: borç + ders kaydı + burs + not ortalaması)
- Farklı departmanları ilgilendiren sorular varsa → Çoklu soru

TEK SORU ÖRNEKLERİ:
- "Öğrenciler ne yer?" → "Mesela bu anlamsız bir soru departmanlar bu soruyla alakalı değil bağlamda bilgi bulunamadı cevabı dönmelisin"
- "Kütüphane kuralları nelerdir?" → {{"department": "library", "task_type": "query", "query": "Kütüphane kuralları nelerdir?"}}
- "Harç borcum var mı?" → {{"department": "finance", "task_type": "check_fee_status", "query": "Harç borcum var mı?"}}

ÇOKLU SORU ÖRNEKLERİ (Pattern Öğrenme İçin - Bu örnekler sadece pattern gösterir, benzer tüm sorular için geçerlidir):
- "Borç durumum nedir? Bu borç ders kaydı yapmamı engeller mi? Ayrıca not ortalamamla burs başvurusu yapabilir miyim?" → 
  [
    {{"department": "finance", "task_type": "check_fee_status", "query": "Borç durumum nedir?", "priority": 1}},
    {{"department": "student_affairs", "task_type": "check_course_registration", "query": "Bu borç ders kaydı yapmamı engeller mi?", "priority": 2, "depends_on": [{{"task_type": "check_fee_status", "department": "finance"}}]}},
    {{"department": "academic_affairs", "task_type": "check_academic_status", "query": "Not ortalamam kaç?", "priority": 1}},
    {{"department": "finance", "task_type": "check_scholarship", "query": "Not ortalamamla burs başvurusu yapabilir miyim?", "priority": 3, "depends_on": [{{"task_type": "check_academic_status", "department": "academic_affairs"}}]}}
  ]

- "Ders kaydı yapabilir miyim? Not ortalamam kaç?" →
  [
    {{"department": "student_affairs", "task_type": "check_course_registration", "query": "Ders kaydı yapabilir miyim?", "priority": 1}},
    {{"department": "academic_affairs", "task_type": "check_academic_status", "query": "Not ortalamam kaç?", "priority": 1}}
  ]

GENEL KURALLAR (TÜM ÇOKLU SORULAR İÇİN - Örneklerden bağımsız):
1. Soruları parçala: Her soru için ayrı task oluştur
2. Departman tespiti: Her sorunun hangi departmana ait olduğunu belirle
3. Task type tespiti: Her sorunun hangi task_type'a ait olduğunu belirle (check_fee_status, check_course_registration, check_academic_status, check_scholarship, query, vb.)
4. Bağımlılık tespiti:
   - Ders kaydı için → önce borç kontrolü (check_fee_status) ve akademik durum (check_academic_status) gerekli
   - Burs başvurusu için → önce akademik durum (check_academic_status) gerekli
   - Ödeme durumu için → önce borç kontrolü (check_fee_status) gerekli
5. "depends_on" formatı: [{{"task_type": "check_fee_status", "department": "finance"}}]
6. Priority: Önce çalışması gerekenler 1, sonra çalışacaklar 2, 3...
7. Query alanı: Her task'ın "query" alanına o spesifik soruyu yaz (tüm soruyu değil, sadece o task'a ait kısmı)

JSON formatında yanıt ver (sadece JSON, başka açıklama yok):
{{
    "analysis": "İsteğin kısa analizi",
    "tasks": [
        {{
            "department": "student_affairs",
            "task_type": "query",
            "query": "{query}",
            "priority": 3,
            "depends_on": []
        }}
    ]
}}"""

        try:
            response = await asyncio.wait_for(
                self.llm.generate(
                    prompt=prompt,
                    system_prompt=SystemPrompts.MAIN_ORCHESTRATOR,
                    max_tokens=2000  # Task analizi için yeterli
                ),
                timeout=30.0  # LLM analizi için timeout
            )
            
            logger.debug("llm_analysis_response_received", 
                        response_length=len(response),
                        response_preview=response[:200],
                        context_id=context_id)
        except asyncio.TimeoutError:
            logger.warning("llm_analysis_timeout", 
                         query=query[:100],
                         context_id=context_id)
            # Fallback
            return {
                "analysis": "LLM analizi zaman aşımına uğradı",
                "tasks": [{
                    "department": "student_affairs",
                    "task_type": "query",
                    "query": query,
                    "priority": 3,
                    "depends_on": []
                }]
            }
        except Exception as e:
            logger.error("llm_analysis_error", 
                        error=str(e),
                        error_type=type(e).__name__,
                        query=query[:100],
                        context_id=context_id)
            # Fallback
            return {
                "analysis": f"LLM analizi hatası: {str(e)}",
                "tasks": [{
                    "department": "student_affairs",
                    "task_type": "query",
                    "query": query,
                    "priority": 3,
                    "depends_on": []
                }]
            }

        # JSON parse - daha güçlü parsing
        def fix_json_string(json_str: str) -> str:
            """JSON string'ini düzeltmeye çalışır."""
            # Trailing comma'ları kaldır
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            # Çift tırnak sorunlarını düzelt
            json_str = re.sub(r'([^\\])"([^",:}\]]*)"([^",:}\]]*)"', r'\1"\2\3"', json_str)
            return json_str
        
        def extract_json_from_text(text: str) -> Optional[str]:
            """Metinden JSON bloğunu çıkarır."""
            # Markdown code block - greedy match kullan (non-greedy değil)
            json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                # JSON'un tamamını almak için balanced braces kontrolü yap
                return json_str
            
            # Sadece JSON bloğu (tasks içeren) - greedy match
            json_match = re.search(r'\{[\s\S]*?"tasks"[\s\S]*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                # Balanced braces kontrolü
                brace_count = json_str.count('{') - json_str.count('}')
                if brace_count == 0:
                    return json_str
                # Eksik braces varsa, sonuna kadar ekle
                if brace_count > 0:
                    # En son } bul ve ondan sonrasını ekle
                    last_brace = text.rfind('}', json_match.end())
                    if last_brace > json_match.end():
                        return text[json_match.start():last_brace+1]
            
            # En dıştaki {} bloğu - balanced braces ile
            start_idx = text.find('{')
            if start_idx != -1:
                brace_count = 0
                for i in range(start_idx, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            return text[start_idx:i+1]
            
            return None
        
        try:
            # Önce JSON'u metinden çıkar
            json_str = extract_json_from_text(response)
            if not json_str:
                logger.warning("llm_analysis_no_json_found", 
                             response_preview=response[:500],
                             context_id=context_id)
                raise ValueError("JSON bulunamadı")
            
            # JSON'u parse etmeyi dene
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                # JSON hatalı, düzeltmeyi dene
                logger.debug("llm_analysis_json_fixing_attempt",
                           error=str(e),
                           context_id=context_id)
                fixed_json = fix_json_string(json_str)
                try:
                    parsed = json.loads(fixed_json)
                    logger.debug("llm_analysis_json_fixed",
                               context_id=context_id)
                except json.JSONDecodeError:
                    # Hala parse edilemiyorsa, ham response'u logla
                    logger.warning("llm_analysis_json_parse_error", 
                                 error=str(e),
                                 json_preview=json_str[:500],
                                 context_id=context_id)
                    raise
            
            # Parse başarılı, kontrol et
            if not isinstance(parsed, dict) or "tasks" not in parsed:
                logger.warning("llm_analysis_invalid_structure",
                             parsed_keys=list(parsed.keys()) if isinstance(parsed, dict) else "not_dict",
                             context_id=context_id)
                raise ValueError("Geçersiz JSON yapısı")
            
            tasks_count = len(parsed.get("tasks", []))
            logger.info("llm_analysis_json_parsed_success",
                       tasks_count=tasks_count,
                       context_id=context_id)
            return parsed
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("llm_analysis_json_parse_error", 
                         error=str(e),
                         response_preview=response[:500],
                         context_id=context_id)
        except Exception as e:
            logger.error("llm_analysis_parse_exception", 
                        error=str(e),
                        error_type=type(e).__name__,
                        context_id=context_id)

        # Parse edilemezse fallback - ama önce response'u analiz et
        logger.warning("llm_analysis_fallback_used", 
                      query=query[:100],
                      response_preview=response[:1000] if response else "no_response",
                      context_id=context_id)
        
        # Fallback: Basit keyword-based analiz yap
        # Çoklu soru tespiti
        question_count = query.count("?")
        if question_count > 1:
            # Çoklu soru var, keyword-based task'lar oluştur
            tasks = []
            query_lower = query.lower()
            
            # Borç durumu
            if any(kw in query_lower for kw in ["borç", "borc", "harc", "harç"]):
                tasks.append({
                    "department": "finance",
                    "task_type": "check_fee_status",
                    "query": query,
                    "priority": 1,
                    "depends_on": []
                })
            
            # Ders kaydı
            if any(kw in query_lower for kw in ["ders kaydı", "ders kaydi", "kayıt", "kayit"]):
                tasks.append({
                    "department": "student_affairs",
                    "task_type": "check_course_registration",
                    "query": query,
                    "priority": 2,
                    "depends_on": []
                })
            
            # Akademik durum / GPA
            if any(kw in query_lower for kw in ["not ortalaması", "not ortalamasi", "gpa", "akademik durum"]):
                tasks.append({
                    "department": "academic_affairs",
                    "task_type": "check_academic_status",
                    "query": query,
                    "priority": 1,
                    "depends_on": []
                })
            
            # Burs
            if any(kw in query_lower for kw in ["burs", "burs başvurusu", "burs basvurusu"]):
                tasks.append({
                    "department": "finance",
                    "task_type": "check_scholarship",
                    "query": query,
                    "priority": 3,
                    "depends_on": []
                })
            
            if tasks:
                logger.info("llm_analysis_fallback_tasks_created",
                          tasks_count=len(tasks),
                          context_id=context_id)
                return {
                    "analysis": "Fallback: Keyword-based task tespiti",
                    "tasks": tasks
                }
        
        # Hiçbir şey bulunamazsa default
        return {
            "analysis": response[:200] if response else "LLM analizi başarısız",
            "tasks": [{
                "department": "student_affairs",
                "task_type": "query",
                "query": query,
                "priority": 3,
                "depends_on": []
            }]
        }

    async def _distribute_tasks(
        self,
        tasks: List[Dict[str, Any]],
        context_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Görevleri topological sort ile sıralayarak dağıtır.

        Bağımlılıkları tamamlanmış görevler paralel çalıştırılır.
        Bağımlı görevlere, bağımlılıklarının sonuçları iletilir.
        """
        results = []
        completed_tasks = {}  # task_type -> result mapping
        remaining_tasks = tasks.copy()

        while remaining_tasks:
            # Bağımlılıkları tamamlanmış task'ları bul
            ready_tasks = []
            for task in remaining_tasks:
                dependencies = task.get("dependencies", [])
                if not dependencies:
                    ready_tasks.append(task)
                else:
                    # Tüm bağımlılıklar tamamlandı mı?
                    all_deps_completed = all(
                        dep["task_type"] in completed_tasks
                        for dep in dependencies
                    )
                    if all_deps_completed:
                        ready_tasks.append(task)

            if not ready_tasks:
                # Circular dependency veya hata
                logger.error(
                    "dependency_resolution_failed",
                    remaining=[t["task_type"] for t in remaining_tasks]
                )
                for task in remaining_tasks:
                    results.append({
                        "department": task["department"],
                        "status": "failed",
                        "response": "Bağımlılık çözümlenemedi",
                        "task_type": task["task_type"]
                    })
                break

            # Ready task'ları kuyruk + paralel çalıştır
            async def enqueue_ready_tasks():
                for t in ready_tasks:
                    # Task metadata'ya context_id ekle
                    t["context_id"] = context_id
                    await self._queue.enqueue(
                        A2ATask(
                            task_id=t["task_id"],
                            context_id=context_id,
                            from_agent=self.agent_id,
                            to_agent=self._department_orchestrators[t["department"]].agent_id if t["department"] in self._department_orchestrators else "unknown",
                            initial_message=create_message(
                                role=MessageRole.USER,
                                text=t.get("query", ""),
                                data={
                                    "task_type": t.get("task_type", "query"),
                                    "dependency_results": {},
                                    "parent_task_id": parent_task_id,
                                    "user_id": user_id
                                } if user_id else {
                                    "task_type": t.get("task_type", "query"),
                                    "dependency_results": {},
                                    "parent_task_id": parent_task_id
                                },
                                context_id=context_id
                            )
                        ),
                        priority=t.get("priority", 3)
                    )

            await enqueue_ready_tasks()

            async def process_dequeued_task(q_task: A2ATask, original_task: Dict[str, Any]) -> Dict[str, Any]:
                # Bağımlılık sonuçlarını parametrelere ekle
                dependency_results = {}
                for dep in original_task.get("dependencies", []):
                    dep_type = dep["task_type"]
                    if dep_type in completed_tasks:
                        dependency_results[dep_type] = completed_tasks[dep_type]

                # Gönder
                return await self._send_to_department(
                    department=original_task["department"],
                    query=original_task["query"],
                    task_type=original_task.get("task_type", "query"),
                    context_id=context_id,
                    parent_task_id=parent_task_id,
                    dependency_results=dependency_results,
                    user_id=user_id
                )

            dequeued_tasks = []
            for _ in range(len(ready_tasks)):
                dq = await self._queue.dequeue()
                if dq:
                    dequeued_tasks.append(dq)

            parallel_results = await asyncio.gather(*[
                process_dequeued_task(dq, rt) for dq, rt in zip(dequeued_tasks, ready_tasks)
            ], return_exceptions=True)

            for task, result in zip(ready_tasks, parallel_results):
                if isinstance(result, Exception):
                    result_dict = {
                        "department": task["department"],
                        "status": "failed",
                        "response": str(result),
                        "task_type": task["task_type"]
                    }
                else:
                    result_dict = result

                results.append(result_dict)
                completed_tasks[task["task_type"]] = result_dict
                remaining_tasks.remove(task)

                logger.info(
                    "task_completed",
                    task_type=task["task_type"],
                    department=task["department"],
                    status=result_dict.get("status"),
                    context_id=context_id
                )

        return results

    async def _send_to_department(
        self,
        department: str,
        query: str,
        task_type: str = "query",
        context_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        dependency_results: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Departman orchestrator'a task gönderir.

        dependency_results: Bağımlı task'ların sonuçları (varsa)
        user_id: Kullanıcı kimliği (veritabanı sorguları için)
        """
        orchestrator = self._department_orchestrators.get(department)

        if not orchestrator:
            logger.warning("department_not_found", department=department)
            return {
                "department": department,
                "status": "not_found",
                "response": f"{department} departmanı bulunamadı.",
                "task_type": task_type
            }

        try:
            send_start = asyncio.get_event_loop().time()
            # Task verilerini oluştur - user_id dahil
            task_data = {"task_type": task_type}
            if user_id:
                task_data["user_id"] = user_id
            if dependency_results:
                task_data["dependency_results"] = dependency_results
                logger.info(
                    "sending_with_dependencies",
                    department=department,
                    task_type=task_type,
                        dependencies=list(dependency_results.keys()),
                        context_id=context_id
                )

            result = await self.send_to_agent(
                to_agent=orchestrator.agent_id,
                text=query,
                data=task_data,
                context_id=context_id,
                timeout=self._send_timeout,
                max_retries=self._send_retries,
                retry_backoff=self._send_backoff
            )

            if result.status == TaskStatus.COMPLETED:
                latency_ms = round((asyncio.get_event_loop().time() - send_start) * 1000, 2)
                logger.info(
                    "department_task_success",
                    department=department,
                    task_type=task_type,
                    latency_ms=latency_ms,
                    context_id=context_id
                )
                return {
                    "department": department,
                    "status": "completed",
                    "response": result.get_latest_message().get_text(),
                    "task_type": task_type,
                    "artifacts": [a.model_dump() for a in result.artifacts],
                    "data": result.get_latest_message().get_data()
                }
            else:
                return {
                    "department": department,
                    "status": "failed",
                    "response": result.error or "Bilinmeyen hata",
                    "task_type": task_type
                }

        except Exception as e:
            logger.error(
                "department_task_error",
                department=department,
                error=str(e)
            )
            return {
                "department": department,
                "status": "error",
                "response": str(e),
                "task_type": task_type
            }

    async def _synthesize_response(
        self,
        user_query: str,
        analysis: Dict[str, Any],
        department_results: List[Dict[str, Any]],
        context_id: Optional[str] = None
    ) -> str:
        """Departman yanıtlarını birleştirir."""
        # Başarılı yanıtları filtrele
        successful_results = [
            r for r in department_results
            if r["status"] == "completed" and r["response"]
        ]

        if not successful_results:
            return "İsteğiniz işlenirken bir sorun oluştu. Lütfen daha sonra tekrar deneyin."

        # "Bilgi bulunamadı" kontrolü - tüm departmanlar bilgi bulamadıysa
        not_found_indicators = [
            "bilgi bulunamadı",
            "bulunamadı",
            "veri bulunamadı",
            "sonuç bulunamadı",
            "kayıt bulunamadı"
        ]

        all_not_found = all(
            any(indicator in r["response"].lower() for indicator in not_found_indicators)
            for r in successful_results
        )

        if all_not_found:
            return "Sorgunuzla ilgili sistemde kayıtlı bilgi bulunamadı. Lütfen sorunuzu farklı şekilde ifade edin veya ilgili birime doğrudan başvurun."

        # Tek departman ve tek yanıt varsa, direkt döndür (LLM gerekmez)
        if len(successful_results) == 1:
            response = successful_results[0]["response"]
            # Emojileri temizle
            response = self._remove_emojis(response)
            logger.info("response_single_department",
                       department=successful_results[0]["department"],
                       context_id=context_id)
            return response

        # Birden fazla departman varsa sentez gerekli mi kontrol et
        needs_synthesis = self._needs_response_synthesis(
            user_query=user_query,
            analysis=analysis,
            department_results=successful_results
        )

        if needs_synthesis and self.llm:
            try:
                prompt = SystemPrompts.get_response_synthesizer_prompt(
                    user_query=user_query,
                    responses=[
                        {"department": r["department"], "response": r["response"]}
                        for r in successful_results
                    ]
                )
                logger.info("synthesis_llm_start",
                           reason="needs_synthesis",
                           departments=[r["department"] for r in successful_results],
                           context_id=context_id)

                # Çoklu sorular için daha fazla token gerekli
                # 4 departman yanıtı varsa, detaylı sentez için daha fazla token
                num_departments = len(successful_results)
                max_tokens = 4000 if num_departments >= 3 else 3000
                timeout_seconds = 45.0 if num_departments >= 3 else 35.0
                
                llm_answer = await asyncio.wait_for(
                    self.llm.generate(
                        prompt=prompt,
                        system_prompt=SystemPrompts.MAIN_ORCHESTRATOR,
                        max_tokens=max_tokens
                    ),
                    timeout=timeout_seconds
                )
                final_text = self._remove_emojis(llm_answer) if llm_answer else self._format_simple_response(successful_results)
                logger.info("synthesis_llm_completed",
                           response_length=len(final_text),
                           context_id=context_id)
            except Exception as e:
                logger.warning("synthesis_llm_fallback",
                             error=str(e),
                             context_id=context_id)
                final_text = self._format_simple_response(successful_results)
        else:
            # LLM gerekmiyorsa basit formatlama
            final_text = self._format_simple_response(successful_results)
            logger.info("response_synthesized_simple",
                       departments=[r["department"] for r in successful_results],
                       context_id=context_id)

        # Uzunluk kontrolü
        max_len = 3000
        if len(final_text) > max_len:
            final_text = final_text[:max_len] + "\n\n(Yanıt uzunluk sınırı nedeniyle kısaltıldı.)"

        return final_text

    def _format_simple_response(self, results: List[Dict[str, Any]]) -> str:
        """Basit yanıt formatlama - LLM kullanmadan."""
        dept_names = {
            "it": "IT Departmanı",
            "student_affairs": "Öğrenci İşleri",
            "finance": "Mali İşler",
            "academic_affairs": "Akademik İşler",
            "library": "Kütüphane"
        }

        if len(results) == 1:
            return self._remove_emojis(results[0]["response"])

        parts = []
        for result in results:
            dept_name = dept_names.get(result["department"], result["department"])
            response = self._remove_emojis(result["response"])
            parts.append(f"[{dept_name}]\n{response}")

        return "\n\n".join(parts)

    def _remove_emojis(self, text: str) -> str:
        """Metinden emojileri kaldırır."""
        import re
        # Emoji pattern - Unicode emoji ranges
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"  # dingbats
            "\U000024C2-\U0001F251"  # enclosed characters
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended-A
            "\U00002600-\U000026FF"  # misc symbols
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub('', text).strip()

    def _needs_response_synthesis(
        self,
        user_query: str,
        analysis: Dict[str, Any],
        department_results: List[Dict[str, Any]]
    ) -> bool:
        """
        Yanıtların LLM ile birleştirilmesi gerekip gerekmediğini belirler.

        LLM sentezi SADECE şu durumlarda gerekli:
        1. Birden fazla departmandan yanıt var VE yanıtlar birbiriyle ilişkili
        2. Yanıtlar arasında çelişki var
        3. Kullanıcının sorusu birden fazla konuyu kapsıyor

        LLM sentezi GEREKMİYOR:
        - Tek departman yanıtı
        - Birden fazla departman AMA yanıtlar bağımsız (sadece alt alta gösterilebilir)
        - Basit bilgi sorguları
        """
        unique_departments = set(r["department"] for r in department_results)

        # Tek departman - sentez gerekmez
        if len(unique_departments) <= 1:
            return False

        # 2+ departman varsa, yanıtların ilişkili olup olmadığını kontrol et
        query_lower = user_query.lower()

        # Bağımlılık içeren task'lar - sentez gerekli
        tasks = analysis.get("tasks", [])
        has_dependencies = any(
            task.get("dependencies") and len(task.get("dependencies", [])) > 0
            for task in tasks
        )
        if has_dependencies:
            logger.debug("synthesis_needed", reason="has_dependencies")
            return True

        # Çoklu soru işareti - kullanıcı birden fazla soru sormuş
        if query_lower.count("?") >= 2:
            logger.debug("synthesis_needed", reason="multiple_questions")
            return True

        # Bağlaçlar - kullanıcı birbiriyle ilişkili şeyler soruyor
        connectors = [" ve ", " ile ", " hem ", " hem de ", " ayrıca ", " aynı zamanda "]
        has_connector = any(conn in query_lower for conn in connectors)
        if has_connector and len(unique_departments) >= 2:
            logger.debug("synthesis_needed", reason="connector_multiple_dept")
            return True

        # Basit durumda sentez gerekmez - yanıtlar bağımsız gösterilebilir
        logger.debug("synthesis_not_needed", reason="independent_responses")
        return False

    async def handle_user_message(
        self,
        message: str,
        user_id: Optional[str] = None,
        context_id: Optional[str] = None
    ) -> str:
        """
        Kullanıcı mesajını işler (basitleştirilmiş API).
        Frontend entegrasyonu için kullanılır.
        """
        task = create_task(
            from_agent="user",
            to_agent=self.agent_id,
            text=message,
            data={"user_id": user_id} if user_id else None,
            context_id=context_id
        )

        result = await self.handle_task(task)

        return result.get_latest_message().get_text()
