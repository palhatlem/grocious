"""Receipt-only provider adapters. Network calls have no tools and no archive context."""

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Protocol

from . import store
from .heuristics import parse
import receipt_archive as archive

HERE = Path(__file__).parent
SCHEMA = json.loads((HERE / "schema.json").read_text())
PROMPT = (HERE / "prompts/interpret-v1.md").read_text()


class Provider(Protocol):
    id: str
    label: str
    vision: bool

    def interpret(self, *, text, image, mimetype, hints): ...


class Rules:
    id, label, vision, model = "none", "Regler", False, "rules-1"
    available = True

    def interpret(self, *, text, image, mimetype, hints):
        return dict(parsed=parse(text or ""), raw={}, input_tokens=0, output_tokens=0)


class OpenAI:
    id, label, vision = "openai", "Codex (OpenAI)", True

    @property
    def model(self):
        return os.getenv("GROCIOUS_LLM_OPENAI_MODEL", "gpt-6-astra")

    @property
    def available(self):
        return bool(os.getenv("OPENAI_API_KEY"))

    def interpret(self, *, text, image, mimetype, hints):
        from openai import OpenAI as Client

        content = [{"type": "input_text", "text": json.dumps({"text": text, "hints": hints})}]
        for data, mime in image or []:
            content.append(
                {"type": "input_image", "image_url": f"data:{mime};base64," + base64.b64encode(data).decode()}
            )
        response = Client(timeout=120, max_retries=0).responses.create(
            model=self.model,
            store=False,
            instructions=PROMPT,
            input=[{"role": "user", "content": content}],
            max_output_tokens=4096,
            text={"format": {"type": "json_schema", "name": "receipt", "strict": True, "schema": SCHEMA}},
        )
        if response.status != "completed" or not response.output_text:
            raise ValueError("Modellen fullførte ikke tolkingen. Regelresultatet er beholdt.")
        return dict(
            parsed=json.loads(response.output_text),
            raw=response.model_dump(mode="json"),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class Claude:
    id, label, vision = "claude", "Claude", True

    @property
    def model(self):
        return getattr(self, "selected_model", None) or os.getenv("GROCIOUS_LLM_CLAUDE_MODEL", "claude-opus-5")

    @property
    def available(self):
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    def interpret(self, *, text, image, mimetype, hints):
        from anthropic import Anthropic

        content = [{"type": "text", "text": json.dumps({"text": text, "hints": hints})}]
        for data, mime in image or []:
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()},
                }
            )
        response = Anthropic(timeout=120, max_retries=0).messages.create(
            model=self.model,
            max_tokens=4096,
            system=[{"type": "text", "text": PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if response.stop_reason != "end_turn":
            raise ValueError("Modellen fullførte ikke tolkingen. Regelresultatet er beholdt.")
        raw_text = "".join(b.text for b in response.content if b.type == "text")
        return dict(
            parsed=json.loads(raw_text),
            raw=response.model_dump(mode="json"),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class Gateway:
    id, label, vision = "litellm", "Gateway (EU)", False

    @property
    def model(self):
        return os.getenv("GROCIOUS_LLM_LITELLM_MODEL", "")

    @property
    def available(self):
        return bool(self.model and os.getenv("GROCIOUS_LLM_LITELLM_URL"))

    def interpret(self, *, text, image, mimetype, hints):
        if not text:
            raise ValueError("Gateway krever tekst. Velg en bildemodell eller fyll inn feltene.")
        from openai import OpenAI as Client

        response = Client(
            base_url=os.environ["GROCIOUS_LLM_LITELLM_URL"],
            api_key=os.getenv("GROCIOUS_LLM_LITELLM_KEY") or "unused",
            timeout=120,
            max_retries=0,
        ).chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": json.dumps({"text": text, "hints": hints})},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "receipt", "strict": True, "schema": SCHEMA},
            },
        )
        if response.choices[0].finish_reason != "stop":
            raise ValueError("Gateway fullførte ikke tolkingen")
        return dict(
            parsed=json.loads(response.choices[0].message.content),
            raw=response.model_dump(mode="json"),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )


REGISTRY = {p.id: p for p in (Rules(), Claude(), OpenAI(), Gateway())}


def providers():
    return [
        dict(
            id=p.id,
            label=p.label,
            vision=p.vision,
            available=p.available,
            model=p.model,
            models=[p.model, os.getenv("GROCIOUS_LLM_CLAUDE_CHEAP_MODEL", "claude-sonnet-5")]
            if p.id == "claude"
            else [],
        )
        for p in REGISTRY.values()
    ]


def history(rid):
    directory = archive.folder("inbox", rid)
    result = []
    for path in directory.glob("interpretation-*.json"):
        run = json.loads(path.read_text())
        result.append(dict(run=int(path.stem.split("-")[-1]), **run["metadata"], parsed=run["parsed"]))
    return sorted(result, key=lambda x: x["run"], reverse=True)


def select(rid, number):
    with store.locked():
        if archive.read_receipt("inbox", rid).get("linked_to"):
            raise ValueError("Kvitteringen er allerede koblet")
        directory = archive.folder("inbox", rid)
        path = directory / f"interpretation-{int(number)}.json"
        if not path.exists():
            raise ValueError("Ukjent tolkning")
        archive.atomic_json(directory / "active.json", {"run": int(number)})
        archive.atomic_json(
            directory / "review.json", {"review": {"state": "needs_review", "by": "user", "at": store.now()}}
        )
        archive.rebuild("inbox")


def run(rid, provider_id, model=None):
    if not isinstance(provider_id, str):
        raise ValueError("Ugyldig leverandør")
    provider = REGISTRY.get(provider_id)
    if provider is None or not provider.available:
        raise ValueError("Leverandøren er ikke konfigurert")
    if model:
        import copy

        if provider_id != "claude" or model not in (
            provider.model,
            os.getenv("GROCIOUS_LLM_CLAUDE_CHEAP_MODEL", "claude-sonnet-5"),
        ):
            raise ValueError("Ukjent modellvalg")
        provider = copy.copy(provider)
        provider.selected_model = model
    r = archive.read_receipt("inbox", rid)
    if r.get("linked_to"):
        raise ValueError("Kvitteringen er allerede koblet")
    hints = {k: r["intake"].get(k) for k in ("filename", "mimetype", "received_at", "sender_domain")}
    images, hashes = [], []
    if provider.vision:
        for doc in r["documents"]:
            if doc["role"] == "derived" and doc["mimetype"] in ("image/png", "image/jpeg"):
                path, _ = archive.document("inbox", rid, doc["filename"])
                images.append((path.read_bytes(), doc["mimetype"]))
                hashes.append(doc["sha256"])
    started = time.monotonic()
    try:
        result = provider.interpret(text=r.get("document_text"), image=images, mimetype=None, hints=hints)
    except ValueError:
        raise
    except Exception as e:
        # SDK error bodies can contain provider/account details. Do not expose them.
        raise ValueError("Tolkingen feilet hos leverandøren. Prøv igjen senere; eksisterende data er beholdt.") from e
    parsed = result["parsed"]
    if provider_id != "none":
        import jsonschema

        try:
            jsonschema.validate(parsed, SCHEMA)
            store.normalize(parsed)
            import datetime as dt

            if parsed.get("date"):
                dt.date.fromisoformat(parsed["date"])
            if parsed.get("time"):
                dt.time.fromisoformat(parsed["time"])
            if any(v is not None and not 0 <= v <= 1 for v in (parsed.get("confidence") or {}).values()):
                raise ValueError("Invalid confidence")
        except (jsonschema.ValidationError, ValueError, TypeError) as e:
            raise ValueError("Tolkingen hadde ugyldige felter; eksisterende data er beholdt.") from e
    raw = json.dumps(result["raw"], ensure_ascii=False)
    metadata = dict(
        provider=provider_id,
        model=provider.model,
        prompt_version="interpret-v1" if provider_id != "none" else "rules-1",
        ran_at=store.now(),
        latency_ms=round((time.monotonic() - started) * 1000),
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        confidence=parsed.get("confidence") or {},
        raw_response_sha256=hashlib.sha256(raw.encode()).hexdigest(),
    )
    with store.locked():
        directory = archive.folder("inbox", rid)
        number = max((x["run"] for x in history(rid)), default=0) + 1
        archive.atomic_json(
            directory / f"interpretation-{number}.json",
            dict(
                request={
                    "text": r.get("document_text"),
                    "image_sha256": hashes,
                    "hints": hints,
                    "prompt": PROMPT,
                    "schema": SCHEMA,
                },
                response=result["raw"],
                parsed=parsed,
                metadata=metadata,
            ),
        )
    select(rid, number)
    return number
