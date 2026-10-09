"""
Thin wrapper around Hugging Face's Inference Providers router
(an OpenAI-compatible chat completions API). Free tier, rate-limited --
see https://huggingface.co/docs/inference-providers for current limits.

Model choice: Qwen2.5-7B-Instruct by default -- reliable structured/JSON
output, 32K context (fits long invoices/contracts), and it's one of the
more free-tier-friendly options across HF's providers. Swap it with the
HF_MODEL env var if you want to try meta-llama/Meta-Llama-3.1-8B-Instruct
or a larger Qwen variant.

provider="auto" matters here: HF's own first-party "hf-inference" backend
only serves a small curated model list, not every model on the Hub. Using
"auto" lets the router pick whichever of its 20+ partner providers
(Together, Novita, Fireworks, etc.) actually hosts HF_MODEL, so swapping
HF_MODEL just works without also having to guess the right provider name.
"""
import re

from huggingface_hub import InferenceClient
from app.config import HF_TOKEN, HF_MODEL

_client = InferenceClient(provider="auto", api_key=HF_TOKEN) if HF_TOKEN else None


def is_configured() -> bool:
    return _client is not None


def complete_json(user_prompt: str, system: str = "") -> str:
    """Sends a prompt, returns the raw text response (expected to be JSON)."""
    if not _client:
        raise RuntimeError("HF_TOKEN is not set")

    system_prompt = (
        "You are a precise document-data-extraction engine. "
        "Respond with ONLY valid JSON -- no markdown fences, no commentary, no preamble. "
        + system
    )

    response = _client.chat.completions.create(
        model=HF_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2000,
        temperature=0.1,
    )
    text = (response.choices[0].message.content or "").strip()

    # Open models are less consistent than Claude about staying JSON-only --
    # strip code fences and pull out the first {...} block defensively.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    return text.strip()
