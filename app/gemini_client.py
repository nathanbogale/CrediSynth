import os
import asyncio
from typing import Any

import google.generativeai as genai

from .models import QSEReportInput, QAAQualitativeReport


class DownstreamError(Exception):
    pass


def configure(api_key: str | None, model: str):
    if not api_key:
        raise DownstreamError("Missing GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)


def build_prompt(qse: QSEReportInput, analysis_id: str) -> str:
    # Minimal prompt content; production should use a structured template and JSON Mode
    return (
        "System: You are CrediSynth, a senior risk analyst at the National Bank of Ethiopia. "
        "Generate a concise qualitative JSON report per the QAAQualitativeReport schema.\n\n"
        f"qse_request_id: {qse.request_id}\n"
        f"customer_id: {qse.customer_id}\n"
        f"risk_level: {qse.risk_level}\n"
        f"default_probability: {qse.default_probability}\n"
        f"model_version: {qse.model_version}\n"
    )


async def run_gemini(qse: QSEReportInput, analysis_id: str) -> QAAQualitativeReport:
    try:
        model = configure(os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL", "gemini-1.5-pro"))
        prompt = build_prompt(qse, analysis_id)

        # Retries with exponential backoff and timeout
        max_retries = 3
        timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12.0"))
        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                if hasattr(model, "generate_content_async"):
                    resp = await asyncio.wait_for(
                        model.generate_content_async(
                            prompt,
                            generation_config={
                                "temperature": 0.2,
                                "max_output_tokens": 1024,
                                "response_mime_type": "application/json",
                            },
                        ),
                        timeout=timeout_seconds,
                    )
                else:
                    # Fallback to sync call executed in a thread
                    def _call_sync():
                        return model.generate_content(
                            prompt,
                            generation_config={
                                "temperature": 0.2,
                                "max_output_tokens": 1024,
                                "response_mime_type": "application/json",
                            },
                        )

                    resp = await asyncio.wait_for(asyncio.to_thread(_call_sync), timeout=timeout_seconds)
                data = resp.text  # JSON Mode returns JSON text
                qaa = QAAQualitativeReport.model_validate_json(data)
                if not qaa.analysis_id:
                    qaa.analysis_id = analysis_id
                return qaa
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    break
    except Exception as e:
        last_err = e

    raise DownstreamError(str(last_err) if last_err else "Gemini call failed")