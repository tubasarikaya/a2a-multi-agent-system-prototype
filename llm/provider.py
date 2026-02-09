"""
LLM Provider - Gemini ve Claude API entegrasyonu.

Primary provider çalışmazsa otomatik fallback yapar.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import structlog
import json
from functools import partial

logger = structlog.get_logger()


class BaseLLMProvider(ABC):
    """LLM Provider için abstract base class."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """Metin üretir."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Provider'ın erişilebilir olup olmadığını kontrol eder."""
        pass


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000  # Default'u 2048'den 4000'e artırdık
    ) -> str:
        try:
            client = self._get_client()

            # System prompt'u prompt'a ekle
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # Async wrapper with timeout
            loop = asyncio.get_event_loop()
            logger.debug("gemini_generate_start", prompt_length=len(full_prompt), max_tokens=max_tokens)
            
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.generate_content(
                        full_prompt,
                        generation_config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens
                        }
                    )
                ),
                timeout=30.0  # 30 saniye timeout (15'ten artırıldı - API yavaş olabilir)
            )

            logger.debug("gemini_generate_success", response_length=len(response.text) if response.text else 0)
            return response.text

        except asyncio.TimeoutError:
            logger.error("gemini_timeout", timeout=30.0, prompt_preview=full_prompt[:100])
            raise
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error("gemini_error", 
                       error_type=error_type,
                       error=str(e),
                       error_repr=repr(e),
                       prompt_preview=full_prompt[:100] if 'full_prompt' in locals() else "N/A")
            raise

    async def is_available(self) -> bool:
        try:
            client = self._get_client()
            # Basit bir test
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.generate_content("test", generation_config={"max_output_tokens": 10})
            )
            return True
        except Exception:
            return False


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude API Provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000  # Default'u 2048'den 4000'e artırdık
    ) -> str:
        try:
            client = self._get_client()

            # Async wrapper with timeout
            loop = asyncio.get_event_loop()
            logger.debug("claude_generate_start", prompt_length=len(prompt), max_tokens=max_tokens)
            
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system_prompt or "Sen yardımcı bir asistansın.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                ),
                timeout=30.0  # 30 saniye timeout (15'ten artırıldı - API yavaş olabilir)
            )

            response_text = response.content[0].text
            logger.debug("claude_generate_success", response_length=len(response_text))
            return response_text

        except asyncio.TimeoutError:
            logger.error("claude_timeout", timeout=30.0, prompt_preview=prompt[:100])
            raise
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error("claude_error", 
                       error_type=error_type,
                       error=str(e),
                       error_repr=repr(e),
                       prompt_preview=prompt[:100])
            raise

    async def is_available(self) -> bool:
        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "test"}]
                )
            )
            return True
        except Exception:
            return False


class OllamaQwenProvider(BaseLLMProvider):
    """
    Ollama üzerinden local Qwen 2.5 (veya diğer Qwen modelleri) için provider.
    Varsayılan endpoint: http://localhost:11434/api/chat
    """

    def __init__(self, model: str = "qwen2.5:latest", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _build_payload(self, prompt: str, system_prompt: Optional[str], temperature: float, max_tokens: int) -> Dict[str, Any]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        import requests  # Lokal dependency, yoksa kullanıcıya hata verir

        payload = self._build_payload(prompt, system_prompt, temperature, max_tokens)
        url = f"{self.base_url}/api/chat"

        def _call_ollama() -> str:
            resp = requests.post(url, json=payload, timeout=40)
            resp.raise_for_status()
            data = resp.json()
            # Ollama chat cevabı: {"message": {"role": "...", "content": "..."}, ...}
            message = data.get("message") or {}
            content = message.get("content", "")
            return content

        try:
            loop = asyncio.get_event_loop()
            logger.debug(
                "ollama_qwen_generate_start",
                prompt_length=len(prompt),
                max_tokens=max_tokens,
                model=self.model,
                base_url=self.base_url,
            )
            content = await asyncio.wait_for(
                loop.run_in_executor(None, _call_ollama),
                timeout=45.0,
            )
            logger.debug(
                "ollama_qwen_generate_success",
                response_length=len(content) if content else 0,
            )
            return content or ""
        except asyncio.TimeoutError:
            logger.error("ollama_qwen_timeout", timeout=45.0, prompt_preview=prompt[:100])
            raise
        except Exception as e:
            error_type = type(e).__name__
            logger.error(
                "ollama_qwen_error",
                error_type=error_type,
                error=str(e),
                error_repr=repr(e),
                prompt_preview=prompt[:100],
            )
            raise

    async def is_available(self) -> bool:
        import requests

        url = f"{self.base_url}/api/tags"

        def _check() -> bool:
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                return True
            except Exception:
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _check)


class MockProvider(BaseLLMProvider):
    """
    Mock LLM Provider - API anahtarı yokken test için.
    Basit kural tabanlı yanıtlar üretir.
    """

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        logger.warning("using_mock_provider")

        prompt_lower = prompt.lower()

        # Main orchestrator JSON formatı bekliyorsa
        if "json" in prompt_lower and "department" in prompt_lower:
            return self._generate_task_json(prompt_lower)

        # Departman yönlendirmesi
        if "servis adını yaz" in prompt_lower:
            return self._route_department(prompt_lower)

        # Basit anahtar kelime tabanlı yanıtlar
        if "harç" in prompt_lower and ("borç" in prompt_lower or "var mı" in prompt_lower):
            return "Harç borcu durumunuzu kontrol ettim. Sonuçları ilgili departmandan alınan bilgilere göre değerlendiriyorum."

        if "ders kaydı" in prompt_lower or "ders kayıt" in prompt_lower:
            return "Ders kaydı işlemi için öğrenci işleri departmanından bilgi alınmıştır. Sonuçları değerlendiriyorum."

        if "şifre" in prompt_lower or "parola" in prompt_lower:
            return "Şifre sıfırlama işlemi IT departmanı tarafından ele alınacaktır."

        if "burs" in prompt_lower:
            return "Burs başvuru durumunuz mali işler departmanı tarafından kontrol edilecektir."

        return f"İsteğiniz alındı ve ilgili departmanlara iletildi. Toplanan bilgiler: {prompt[:100]}..."

    def _generate_task_json(self, prompt: str) -> str:
        """Orchestrator için task JSON'ı üretir."""
        import json

        tasks = []

        # Harç ile ilgili
        if "harç" in prompt:
            tasks.append({
                "department": "finance",
                "task_type": "query",
                "query": "Harç borcu durumu sorgulanıyor",
                "priority": 3,
                "depends_on": []
            })

        # Ders kaydı ile ilgili
        if "ders" in prompt and "kayı" in prompt:
            tasks.append({
                "department": "student_affairs",
                "task_type": "query",
                "query": "Ders kaydı durumu sorgulanıyor",
                "priority": 3,
                "depends_on": []
            })

        # Şifre ile ilgili
        if "şifre" in prompt or "parola" in prompt:
            tasks.append({
                "department": "it",
                "task_type": "action",
                "query": "Şifre sıfırlama işlemi",
                "priority": 4,
                "depends_on": []
            })

        # Burs ile ilgili
        if "burs" in prompt:
            tasks.append({
                "department": "finance",
                "task_type": "query",
                "query": "Burs başvurusu bilgisi",
                "priority": 2,
                "depends_on": []
            })

        # Varsayılan task
        if not tasks:
            tasks.append({
                "department": "student_affairs",
                "task_type": "query",
                "query": "Genel sorgu",
                "priority": 2,
                "depends_on": []
            })

        return json.dumps({
            "analysis": "Anahtar kelime tabanlı analiz yapıldı",
            "tasks": tasks
        }, ensure_ascii=False)

    def _route_department(self, prompt: str) -> str:
        """Departman içi yönlendirme."""
        # IT departmanı
        if "tech_support" in prompt or "email_support" in prompt:
            if "şifre" in prompt or "email" in prompt or "hesap" in prompt:
                return "email_support"
            return "tech_support"

        # Öğrenci işleri
        if "registration" in prompt or "course" in prompt:
            if "ders" in prompt:
                return "course"
            return "registration"

        # Mali işler
        if "tuition" in prompt or "scholarship" in prompt:
            if "burs" in prompt:
                return "scholarship"
            return "tuition"

        return "registration"

    async def is_available(self) -> bool:
        return True


class LLMProvider:
    """
    Multi-provider LLM wrapper.
    Primary provider başarısız olursa fallback yapar.
    """

    def __init__(
        self,
        primary_provider: BaseLLMProvider,
        fallback_provider: Optional[BaseLLMProvider] = None
    ):
        self.primary = primary_provider
        self.fallback = fallback_provider
        self._current_provider: Optional[BaseLLMProvider] = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        LLM'den metin üretir.
        Primary başarısız olursa fallback'e geçer.
        """
        # Primary dene
        try:
            logger.debug("trying_primary_provider", provider=self.primary.__class__.__name__)
            result = await self.primary.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            self._current_provider = self.primary
            logger.info("primary_provider_success", provider=self.primary.__class__.__name__)
            return result

        except Exception as e:
            error_type = type(e).__name__
            logger.warning("primary_provider_failed", 
                         provider=self.primary.__class__.__name__,
                         error_type=error_type,
                         error=str(e))

            # Fallback dene
            if self.fallback:
                try:
                    logger.info("trying_fallback_provider", provider=self.fallback.__class__.__name__)
                    result = await self.fallback.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    self._current_provider = self.fallback
                    logger.info("fallback_provider_success", provider=self.fallback.__class__.__name__)
                    return result

                except Exception as e2:
                    error_type2 = type(e2).__name__
                    logger.error("fallback_provider_failed", 
                               provider=self.fallback.__class__.__name__,
                               error_type=error_type2,
                               error=str(e2))
                    raise RuntimeError(f"Tüm LLM provider'lar başarısız oldu: primary={error_type}, fallback={error_type2}")

            raise RuntimeError(f"Tüm LLM provider'lar başarısız oldu: primary={error_type}, fallback=yok")

    @property
    def current_provider_name(self) -> str:
        """Şu an kullanılan provider adı."""
        if self._current_provider is None:
            return "none"
        return self._current_provider.__class__.__name__


def get_llm_provider(
    google_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    primary: str = "gemini",
    gemini_model: str = "gemini-2.0-flash",
    claude_model: str = "claude-sonnet-4-20250514",
    ollama_qwen_model: str = "qwen2.5:latest",
    ollama_base_url: str = "http://localhost:11434",
) -> LLMProvider:
    """
    LLM Provider factory function.
    Konfigürasyona göre uygun provider'ları oluşturur.
    """
    providers: Dict[str, BaseLLMProvider] = {}

    # Gemini provider
    if google_api_key:
        providers["gemini"] = GeminiProvider(
            api_key=google_api_key,
            model=gemini_model
        )

    # Claude provider
    if anthropic_api_key:
        providers["claude"] = ClaudeProvider(
            api_key=anthropic_api_key,
            model=claude_model
        )

    # Ollama Qwen provider (local, API key yok)
    providers["ollama_qwen"] = OllamaQwenProvider(
        model=ollama_qwen_model,
        base_url=ollama_base_url,
    )

    # Mock provider (her zaman mevcut)
    providers["mock"] = MockProvider()

    # Primary ve fallback belirle
    if primary in providers and primary != "mock":
        primary_provider = providers[primary]

        # Fallback: önce gemini, sonra claude, sonra diğerleri
        fallback_provider = None
        fallback_order = ["gemini", "claude", "ollama_qwen"]
        for name in fallback_order:
            if name in providers and name != primary and name != "mock":
                fallback_provider = providers[name]
                break
        
        # Eğer fallback_order'da yoksa, diğer provider'ları kontrol et
        if fallback_provider is None:
            for name, provider in providers.items():
                if name != primary and name != "mock" and name not in fallback_order:
                    fallback_provider = provider
                    break

        if fallback_provider is None:
            fallback_provider = providers["mock"]

    else:
        # Primary yoksa, herhangi bir gerçek provider veya mock
        primary_provider = None
        for name, provider in providers.items():
            if name != "mock":
                primary_provider = provider
                break

        if primary_provider is None:
            primary_provider = providers["mock"]

        fallback_provider = providers["mock"] if primary_provider != providers["mock"] else None

    logger.info(
        "llm_provider_initialized",
        primary=primary_provider.__class__.__name__,
        fallback=fallback_provider.__class__.__name__ if fallback_provider else "none"
    )

    return LLMProvider(primary_provider, fallback_provider)
