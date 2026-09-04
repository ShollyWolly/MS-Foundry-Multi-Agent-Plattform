"""Executive-summary generation via the Foundry model deployment, with a static fallback so a
flaky/offline LLM call never breaks report generation (see lib/llm.py).

Every call is grounded in the company/business context (lib.common.COMPANY_DESCRIPTION) and the
specific report's title/purpose — without this, generated summaries read as generic corporate
filler disconnected from the rest of the document; with it, the numbers the LLM references stay
consistent with the fictional company the whole document set is built around.

Controlled by config.yaml's generation.use_llm_narrative — set to false to always use each
report's static fallback sentence (no API calls, no Azure credentials needed) for fast iteration.
"""
from __future__ import annotations

from .common import COMPANY_DESCRIPTION
from .config import generation_config
from .llm import generate_narrative

SYSTEM_PROMPT_TEMPLATE = (
    "You are a business intelligence analyst at Contoso Analytics Group. {company_description}\n\n"
    "You are writing the executive summary section of an internal management report titled "
    "\"{report_title}\". This report is prepared for internal leadership review as part of the "
    "company's standard reporting cycle — write as if you are that analyst, summarizing this "
    "specific report's findings for that audience.\n\n"
    "Write 2-4 sentences in a professional, neutral corporate tone. Reference the specific "
    "figures provided naturally, as a human analyst would, and make sure your framing is "
    "consistent with the company description above (e.g. don't invent an unrelated industry or "
    "business model). Do not use markdown formatting, headers, or bullet points — plain prose "
    "only. Do not repeat the report title verbatim as your first sentence."
)


def generate_summary(report_title: str, data_highlights: str, fallback: str) -> str:
    if not generation_config().get("use_llm_narrative", True):
        return fallback
    try:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            company_description=COMPANY_DESCRIPTION, report_title=report_title
        )
        user_prompt = (
            f"Report: {report_title}\n\n"
            f"Key data points to reference:\n{data_highlights}\n\n"
            "Write the executive summary paragraph now."
        )
        text = generate_narrative(system_prompt, user_prompt)
        return text or fallback
    except Exception as exc:  # noqa: BLE001 - any failure falls back to static text
        print(f"  [narrative] LLM call failed for '{report_title}', using static fallback: {exc}")
        return fallback
