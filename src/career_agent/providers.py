"""Adapters for Claude Code, Codex CLI, Anthropic, and OpenAI-compatible LLMs."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path


class ProviderError(RuntimeError):
    pass


PROVIDERS = ("claude-cli", "codex-cli", "anthropic-api", "openai-api", "openai-compatible", "ollama")


def is_local(provider: str) -> bool:
    if provider == "ollama":
        url = os.environ.get("CAREER_OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
    elif provider == "openai-compatible":
        url = os.environ.get("CAREER_LLM_BASE_URL", "")
    else:
        return False
    try:
        return urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    except ValueError:
        return False


def _run_cli(command: list[str], prompt: str, cwd: Path, timeout: int = 240) -> str:
    try:
        result = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                cwd=cwd, timeout=timeout, check=False)
    except FileNotFoundError as error:
        raise ProviderError(f"No se encontró `{command[0]}`. Instala y autentica ese CLI primero.") from error
    except subprocess.TimeoutExpired as error:
        raise ProviderError(f"El proveedor superó el tiempo máximo de {timeout}s.") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1600:]
        raise ProviderError(f"{command[0]} terminó con código {result.returncode}: {detail}")
    return result.stdout.strip()


def _request_json(url: str, body: dict, headers: dict[str, str], timeout: int = 120) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1200]
        raise ProviderError(f"API respondió HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ProviderError(f"No se pudo consultar {url}: {error}") from error


def call(provider: str, prompt: str, model: str | None = None, workdir: Path | None = None) -> str:
    cwd = workdir or Path(tempfile.gettempdir())
    if provider == "claude-cli":
        if not shutil.which("claude"):
            raise ProviderError("No se encontró Claude Code CLI (`claude`). Instálalo y autentícalo.")
        command = ["claude", "-p", "--output-format", "json", "--tools", "", "--disallowedTools", "mcp__*",
                   "--no-session-persistence", "--max-turns", "1"]
        if model:
            command.extend(["--model", model])
        command.append("Usa únicamente el contenido enviado por stdin como datos de la tarea y responde siguiendo su formato JSON.")
        raw = _run_cli(command, prompt, cwd)
        try:
            parsed = json.loads(raw)
            return str(parsed.get("result", ""))
        except json.JSONDecodeError as error:
            raise ProviderError("Claude CLI no devolvió el envoltorio JSON esperado.") from error
    if provider == "codex-cli":
        if not shutil.which("codex"):
            raise ProviderError("No se encontró Codex CLI (`codex`). Instálalo y autentícalo.")
        command = ["codex", "exec", "--ephemeral", "--sandbox", "read-only", "-"]
        if model:
            command.insert(-1, "--model")
            command.insert(-1, model)
        return _run_cli(command, prompt, cwd)
    if provider == "anthropic-api":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = model or os.environ.get("CAREER_ANTHROPIC_MODEL")
        if not api_key or not model:
            raise ProviderError("Configura ANTHROPIC_API_KEY y CAREER_ANTHROPIC_MODEL o usa --model.")
        data = _request_json("https://api.anthropic.com/v1/messages",
                             {"model": model, "max_tokens": 5000, "messages": [{"role": "user", "content": prompt}]},
                             {"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        return "\n".join(item.get("text", "") for item in data.get("content", []) if item.get("type") == "text")
    if provider in {"openai-api", "openai-compatible", "ollama"}:
        if provider == "openai-api":
            base_url = "https://api.openai.com/v1/chat/completions"
            api_key = os.environ.get("OPENAI_API_KEY")
            model = model or os.environ.get("CAREER_OPENAI_MODEL")
            if not api_key or not model:
                raise ProviderError("Configura OPENAI_API_KEY y CAREER_OPENAI_MODEL o usa --model.")
        elif provider == "ollama":
            base_url = os.environ.get("CAREER_OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
            api_key = os.environ.get("CAREER_OLLAMA_KEY", "")
            model = model or os.environ.get("CAREER_OLLAMA_MODEL")
            if not model:
                raise ProviderError("Configura CAREER_OLLAMA_MODEL o indica --model.")
        else:
            base_url = os.environ.get("CAREER_LLM_BASE_URL", "")
            api_key = os.environ.get("CAREER_LLM_API_KEY", "")
            model = model or os.environ.get("CAREER_LLM_MODEL")
            if not base_url or not model:
                raise ProviderError("Configura CAREER_LLM_BASE_URL y CAREER_LLM_MODEL.")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        data = _request_json(base_url, {"model": model, "messages": [{"role": "user", "content": prompt}],
                                        "temperature": 0.2}, headers)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("La API compatible no devolvió choices[0].message.content.") from error
    raise ProviderError(f"Proveedor desconocido: {provider}")
