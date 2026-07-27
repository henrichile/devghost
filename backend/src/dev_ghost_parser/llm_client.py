"""Encapsula la comunicación con Amazon Bedrock via OpenAI-compatible API."""

import logging
import os
from typing import Optional

from dotenv import find_dotenv, load_dotenv
import openai

# Carga variables del .env más cercano subiendo por la jerarquía de directorios
load_dotenv(find_dotenv(usecwd=True), override=True)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://bedrock-mantle.us-east-1.api.aws/v1"
_DEFAULT_MODEL = "amazon.nova-lite-v1:0"
_TIMEOUT_SECONDS = 60.0


class LLM_Client:
    """Cliente LLM centralizado con endpoint compatible OpenAI."""

    def __init__(self) -> None:
        self._available: bool = False
        self._client: Optional[openai.OpenAI] = None
        self._model: str = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)

        api_key = os.environ.get("LLM_API_KEY", "").strip()
        if not api_key:
            return  # available remains False

        base_url = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL).strip()
        if not base_url.startswith(("http://", "https://")):
            return  # invalid URL, available remains False

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self._available = True

    @property
    def available(self) -> bool:
        """True si el cliente está configurado y listo para hacer requests."""
        return self._available

    def complete(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Envía un prompt al LLM y retorna el texto generado, o None ante cualquier error."""
        if not self._available:
            return None

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"},
                ],
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            return content.strip() if content else None

        except openai.APITimeoutError as exc:
            logger.warning("LLM timeout: %s", exc)
            return None
        except openai.APIConnectionError as exc:
            logger.warning("LLM connection error: %s", exc)
            return None
        except openai.APIError as exc:
            logger.warning("LLM API error (status %s): %s", getattr(exc, 'status_code', '?'), exc)
            return None
        except Exception as exc:
            logger.warning("LLM error (%s): %s", type(exc).__name__, exc)
            return None

    async def complete_async(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Async version — runs the sync LLM call in a thread pool."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.complete, system_prompt, user_prompt)
