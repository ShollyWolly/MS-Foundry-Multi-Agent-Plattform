"""Generates realistic narrative text (executive summaries, commentary) via the Foundry
gpt-5-mini model deployment, conditioned on each report's actual generated numbers — instead of
static template sentences, so the 10 reports read like genuinely different documents.

Deliberately calls the raw model deployment (plain chat completions on
https://<account>.openai.azure.com/openai/deployments/<deployment>/chat/completions), NOT the
agent/Responses API — this is model text generation for document content, unrelated to the
chat agent. Needs the "Cognitive Services OpenAI User" role (see infra/terraform/main.tf,
azurerm_role_assignment.sp_openai_user) in addition to "Foundry User" (agents-only, insufficient
for this).
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from azure.identity import EnvironmentCredential, get_bearer_token_provider
from openai import AzureOpenAI

from .config import generation_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"
API_VERSION = "2024-10-21"


def _terraform_outputs() -> dict:
    result = subprocess.run(
        ["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True, text=True, check=True
    )
    return {k: v["value"] for k, v in json.loads(result.stdout).items()}


@lru_cache(maxsize=1)
def _client_and_deployment() -> tuple[AzureOpenAI, str]:
    outputs = _terraform_outputs()
    account = outputs["foundry_account_name"]
    deployment = outputs["model_deployment_name"]
    credential = EnvironmentCredential()
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=f"https://{account}.openai.azure.com/",
        azure_ad_token_provider=token_provider,
        api_version=API_VERSION,
    )
    return client, deployment


def generate_narrative(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> str:
    """Returns generated text, or a caller-supplied fallback is expected on exception —
    callers should catch and fall back to a static sentence so a flaky/offline LLM call never
    breaks report generation.

    gpt-5-mini is a reasoning model: it spends some of max_completion_tokens on hidden reasoning
    before writing visible output. reasoning_effort="low" keeps that budget small so a short
    paragraph like this doesn't get cut off with zero visible content (finish_reason="length",
    empty message.content) — confirmed happening with the default effort during testing.
    """
    client, deployment = _client_and_deployment()
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=max_tokens,
        reasoning_effort=generation_config().get("llm_reasoning_effort", "low"),
    )
    return (response.choices[0].message.content or "").strip()
