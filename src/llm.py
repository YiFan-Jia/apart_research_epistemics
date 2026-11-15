"""Model calls that must come back as JSON: the diagnosis judge and the vignette checker.

Neither is a model under test, so both go through this one helper instead of the runner's client. It asks
for structured output (the reply is guaranteed to parse against the schema), records usage and which model
actually served the call, and turns a safety decline into an exception instead of a half-read reply.

Settings come from a config section (config.json "judge" or "vignette_check"):
    api_model         required
    max_tokens        default 4000
    request_options   merged into the request; an "output_config" inside it (for example effort) is kept
                      alongside the JSON format
    fallbacks         optional; "default" or a list such as [{"model": "..."}]. When set, a request the model
                      declines is re-run server-side on a fallback model. The model that answered is returned
                      as meta["served_by"], so a fallback is never silent.
    prices_per_mtok   for cost accounting
"""
from __future__ import annotations

import json

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMRefused(Exception):
    """The model (and any fallback) declined the request."""


def cost_usd(usage: dict, prices: dict | None) -> float:
    if not usage or not prices:
        return 0.0
    return ((usage.get("input_tokens") or 0) * prices["input"]
            + (usage.get("output_tokens") or 0) * prices["output"]
            + (usage.get("cache_read_input_tokens") or 0) * prices.get("cache_read", 0)
            + (usage.get("cache_creation_input_tokens") or 0) * prices.get("cache_write", 0)) / 1e6


def build_json_request(mcfg: dict, prompt: str, schema: dict, system: str | None = None) -> dict:
    """The request body, kept as a pure function so tests can check it without a network."""
    opts = dict(mcfg.get("request_options", {}))
    output_config = dict(opts.pop("output_config", {}))
    output_config["format"] = {"type": "json_schema", "schema": schema}
    req = {"model": mcfg["api_model"], "max_tokens": mcfg.get("max_tokens", 4000),
           "messages": [{"role": "user", "content": prompt}], "output_config": output_config, **opts}
    if system:
        req["system"] = system
    return req


class JsonModel:
    """Claude API client for one config section. call() returns (data, meta)."""

    def __init__(self, mcfg: dict, timeout_s: float = 600):
        import anthropic  # noqa: PLC0415
        self.cfg = mcfg
        self.name = mcfg["api_model"]
        # Reads ANTHROPIC_API_KEY from the environment. The key is never printed or logged.
        self.client = anthropic.Anthropic(max_retries=mcfg.get("max_retries", 4), timeout=timeout_s)

    def call(self, prompt: str, schema: dict, system: str | None = None) -> tuple[dict, dict]:
        req = build_json_request(self.cfg, prompt, schema, system)
        fallbacks = self.cfg.get("fallbacks")
        if fallbacks:
            resp = self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks=fallbacks, **req)
        else:
            resp = self.client.messages.create(**req)
        u = resp.usage
        usage = {k: getattr(u, k, 0) or 0 for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                    "cache_creation_input_tokens")}
        meta = {"usage": usage, "cost_usd": cost_usd(usage, self.cfg.get("prices_per_mtok")),
                "served_by": resp.model, "stop_reason": resp.stop_reason,
                "request_id": getattr(resp, "_request_id", None)}
        if resp.stop_reason == "refusal":
            raise LLMRefused(f"{self.name} declined the request")
        if resp.stop_reason == "max_tokens":
            raise ValueError(f"{self.name} reply was cut off at max_tokens; raise max_tokens in config")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return json.loads(text), meta
