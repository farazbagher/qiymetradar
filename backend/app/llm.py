"""Model fabriki: lokal (Ollama, pulsuz, sənəd maşından çıxmır) və bulud (Claude). ReklamPilot-dakı yoxlanmış ayarlarla."""

import os
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "qwen3:4b")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


@lru_cache
def local_chat() -> ChatOllama:
    # temperature=0: ekstraksiyada hər dəfə eyni nəticə lazımdır. reasoning=False: qwen3 "düşünməsi" vaxt yeyir.
    # num_predict=350: düzgün JSON ~120 tokendir, döngüyə düşəndə kəsirik (parse xətası -> növbəti pillə).
    return ChatOllama(model=OLLAMA_CHAT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0, num_ctx=4096, num_predict=350,
                      keep_alive="10m", reasoning=False, client_kwargs={"timeout": LLM_TIMEOUT})


@lru_cache
def claude_chat() -> ChatAnthropic:
    return ChatAnthropic(model=CLAUDE_MODEL, temperature=0, max_tokens=800, timeout=LLM_TIMEOUT, max_retries=2)


def has_claude() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
