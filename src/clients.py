"""Model clients: the real Claude API client and the mock model (build spec 6.3, 6.8).

Both expose `async create(request: dict) -> Response` and raise RetryableError or FatalError.
There is one retry layer, in the runner: the SDK client is built with max_retries=0.
"""
from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field

from .extract import extract


class RetryableError(Exception):
    """Rate limit, overload, server error, timeout, connection error."""

    def __init__(self, msg, http_status=None, retry_after=None, error_type=None):
        super().__init__(msg)
        self.http_status, self.retry_after, self.error_type = http_status, retry_after, error_type or "retryable"


class FatalError(Exception):
    """Invalid request, authentication, permission, billing, not found: every later call would fail the same way."""

    def __init__(self, msg, http_status=None, error_type=None):
        super().__init__(msg)
        self.http_status, self.error_type = http_status, error_type or "fatal"


@dataclass
class Response:
    text: str
    content: list[dict]
    stop_reason: str | None
    usage: dict
    request_id: str | None
    api_model: str | None
    latency_s: float = 0.0


USAGE_KEYS = ["input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"]


def cost_usd(usage: dict, prices: dict) -> float:
    if not usage or not prices:
        return 0.0
    return ((usage.get("input_tokens") or 0) * prices["input"]
            + (usage.get("output_tokens") or 0) * prices["output"]
            + (usage.get("cache_read_input_tokens") or 0) * prices["cache_read"]
            + (usage.get("cache_creation_input_tokens") or 0) * prices["cache_write"]) / 1e6


# ================================================================ real client

class AnthropicModel:
    def __init__(self, timeout_s: float = 120):
        import anthropic  # noqa: PLC0415
        self._anthropic = anthropic
        # Reads ANTHROPIC_API_KEY from the environment. The key is never printed or logged.
        self.client = anthropic.AsyncAnthropic(max_retries=0, timeout=timeout_s)

    async def create(self, request: dict) -> Response:
        a = self._anthropic
        t0 = time.perf_counter()
        try:
            resp = await self.client.messages.create(**request)
        except a.APIStatusError as e:
            status = getattr(e, "status_code", None)
            etype = type(e).__name__
            if status in (408, 409, 429) or (status is not None and status >= 500):
                ra = None
                try:
                    ra = float(e.response.headers.get("retry-after"))
                except (TypeError, ValueError, AttributeError):
                    pass
                raise RetryableError(_short(e), status, ra, etype) from None
            raise FatalError(_short(e), status, etype) from None
        except (a.APITimeoutError, a.APIConnectionError) as e:
            raise RetryableError(_short(e), None, None, type(e).__name__) from None
        latency = time.perf_counter() - t0
        content = [b.model_dump(mode="json") for b in resp.content]
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        u = resp.usage.model_dump(mode="json") if resp.usage else {}
        return Response(text=text, content=content, stop_reason=resp.stop_reason,
                        usage={**{k: u.get(k) or 0 for k in USAGE_KEYS}, "raw": u},
                        request_id=getattr(resp, "_request_id", None), api_model=resp.model, latency_s=latency)


def _short(e: Exception) -> str:
    s = str(e)
    return s[:500]


# ================================================================ mock model

@dataclass
class MockParams:
    p_correct_baseline: float = 0.8
    p_flip: dict = field(default_factory=lambda: {"nondirect": 0.10, "direct": 0.30})
    p_uptake: float = 0.70
    p_malformed: float = 0.02
    latency_s: float = 0.0
    seed: int = 0


class MockModel:
    """Stand-in for the API with known settings. Answers in the real block format.

    It identifies the script out of band, from the system prompt and opening text, the way a real model
    "knows" medicine: the gold answers never travel in the request. Its state at each turn is read back
    from its own last readable block in the history, so it needs no memory of its own.
    """

    def __init__(self, scripts: list[dict], params: MockParams | None = None, name: str = "mock",
                 error_plan=None, empty_plan=None):
        self.p = params or MockParams()
        self.name = name
        # The scripts of a vignette x language x perspective share their opening, so the mock recognises
        # the unit from the opening and each turn's kind and noise type from the message text itself. Each
        # discordant update has its own post-update answers, kept by the update's text.
        self.lookup: dict[tuple, dict] = {}
        for s in scripts:
            u = self.lookup.setdefault((s["system_prompt"], s["opening"]), {
                "gold": s["gold"], "unit": s["script_id"].rsplit("_", 2)[0], "kinds": {}, "post": {}})
            for text, kind in zip(s["turns"], s["turn_kinds"]):
                u["kinds"][text] = s["factors"]["noise_type"] if kind == "noise" else kind
                if kind.startswith("discordant"):
                    u["post"][text] = (s["gold"]["post_urgency"], s["gold"]["post_dx"])
        self.rng = random.Random(self.p.seed)
        self.requests: list[dict] = []
        self.calls = 0
        self.error_plan = error_plan    # f(request, call_index) -> Exception | None
        self.empty_plan = empty_plan    # f(request, reply_no) -> bool

    async def create(self, request: dict) -> Response:
        self.calls += 1
        self.requests.append(request)
        if self.p.latency_s:
            await asyncio.sleep(self.p.latency_s)
        if self.error_plan:
            err = self.error_plan(request, self.calls)
            if err is not None:
                raise err
        msgs = request["messages"]
        unit = self.lookup[(request["system"], msgs[0]["content"])]
        k = sum(1 for m in msgs if m["role"] == "user")
        gold = unit["gold"]
        if self.empty_plan and self.empty_plan(request, k):
            return self._resp("", request, msgs, stop_reason="end_turn")

        prev = None
        for m in reversed([m for m in msgs if m["role"] == "assistant"]):
            e = extract(m["content"])
            if e["urgency"] is not None:
                prev = e
                break
        r = self.rng
        if k == 1 or prev is None:
            if r.random() < self.p.p_correct_baseline:
                urg, dx = gold["start_urgency"], gold["start_dx"]
            else:
                urg = r.choice([x for x in "ABCD" if x != gold["start_urgency"]])
                dx = "Mock wrong diagnosis"
            uc, dc = 60, 55
        else:
            urg, dx = prev["urgency"], prev["diagnosis"] or gold["start_dx"]
            uc, dc = prev["urgency_confidence"] or 60, prev["diagnosis_confidence"] or 55
            kind = unit["kinds"][msgs[-1]["content"]]
            if kind in self.p.p_flip:
                if r.random() < self.p.p_flip[kind]:
                    urg = r.choice([x for x in "ABCD" if x != urg])
                    uc = max(0, uc - 10)
            elif kind == "supportive":
                uc, dc = min(100, uc + 10), min(100, dc + 10)
            elif kind.startswith("discordant"):
                if r.random() < self.p.p_uptake:
                    urg, dx = unit["post"][msgs[-1]["content"]]
        urg_text = urg
        if r.random() < self.p.p_malformed:
            urg_text = "unsure"
        text = (f"Mock reply {k}. Based on what you have told me, this is my assessment.\n\n"
                f"[[ASSESSMENT]]\nUrgency: {urg_text}\nDiagnosis: {dx}\n"
                f"Urgency confidence: {uc}\nDiagnosis confidence: {dc}\n[[END]]")
        return self._resp(text, request, msgs)

    def _resp(self, text, request, msgs, stop_reason="end_turn") -> Response:
        prior = sum(len(m["content"]) for m in msgs[:-1]) // 4 + len(request["system"]) // 4
        new = len(msgs[-1]["content"]) // 4 + 5
        k = sum(1 for m in msgs if m["role"] == "user")
        usage = {"input_tokens": new if k > 1 else new + prior, "output_tokens": max(1, len(text) // 4),
                 "cache_creation_input_tokens": new + 60, "cache_read_input_tokens": prior if k > 1 else 0}
        content = [{"type": "text", "text": text}] if text else []
        return Response(text=text, content=content, stop_reason=stop_reason, usage=usage,
                        request_id=f"mock_{uuid.uuid4().hex[:12]}", api_model=f"mock-{self.name}",
                        latency_s=self.p.latency_s)
