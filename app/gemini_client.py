import os
import asyncio
import json
from typing import Any, List

import google.generativeai as genai

from .models import QSEReportInput, QAAQualitativeReport, ExplainabilityExtended


class DownstreamError(Exception):
    pass


def configure(api_key: str | None, model: str):
    if not api_key:
        raise DownstreamError("Missing GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)


def discover_supported_models(api_key: str | None) -> List[str]:
    if not api_key:
        raise DownstreamError("Missing GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    names: List[str] = []
    try:
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", getattr(m, "generation_methods", []))
            if methods and ("generateContent" in methods or "generate_content" in methods):
                names.append(m.name)  # Full name like 'models/gemini-1.5-pro-latest'
    except Exception as e:
        # If model listing fails, propagate a helpful error
        raise DownstreamError(f"ListModels failed: {e}")
    # Return full names; GenerativeModel accepts full IDs reliably across SDK versions
    return names


def build_prompt(qse: QSEReportInput, analysis_id: str) -> str:
    # Stricter instruction for JSON Mode to conform exactly to QAAQualitativeReport
    return (
        "You are CrediSynth, a senior risk analyst at the National Bank of Ethiopia. "
        "Respond ONLY with a single JSON object that strictly matches the QAAQualitativeReport schema. "
        "Do not include any prose outside JSON. Use these fields exactly: "
        "analysis_id, qse_request_id, customer_id, executive_summary, ability_to_repay, willingness_to_repay, "
        "key_risk_synthesis, key_strengths_synthesis, nbe_compliance_summary, final_recommendation, recommendation_justification.\n"
        "CRITICAL: final_recommendation MUST be one of exactly these strings: "
        "'Approve', 'Approve with Conditions', 'Manual Review', 'Decline'. Do NOT use synonyms.\n"
        "Return valid JSON only. No markdown, no comments, no extra keys.\n\n"
        f"analysis_id: {analysis_id}\n"
        f"qse_request_id: {qse.request_id}\n"
        f"customer_id: {qse.customer_id}\n"
        f"risk_level: {qse.risk_level}\n"
        f"default_probability: {qse.default_probability}\n"
        f"model_version: {qse.model_version}\n"
    )


def build_explainability_prompt(qse: QSEReportInput, analysis_id: str) -> str:
    # Instruct Gemini to produce ExplainabilityExtended JSON strictly
    return (
        "You are CrediSynth, an explainability specialist. Respond ONLY with a single JSON object that strictly matches the ExplainabilityExtended schema. "
        "Do not include any prose outside JSON. Use these fields exactly: shap_analysis (with global_importance[], local_explanation, description, confidence_factors[], risk_factors[]), "
        "feature_importance[] (items: feature, importance, impact one of 'positive','neutral','negative'), explanation_available, interpretation.\n"
        "Return valid JSON only. No markdown, no comments, no extra keys.\n\n"
        f"analysis_id: {analysis_id}\n"
        f"qse_request_id: {qse.request_id}\n"
        f"customer_id: {qse.customer_id}\n"
        "Use the quantitative inputs to infer top-5 global importance drivers and concise local explanation."
    )


def _normalize_enums(payload: dict) -> dict:
    """Normalize enum-like values from common synonyms to accepted literals."""
    val = (payload or {}).get("final_recommendation")
    if isinstance(val, str):
        s = val.strip().lower()
        mapping = {
            # Approve variants
            "approve": "Approve",
            "approved": "Approve",
            "approval": "Approve",
            "approve loan application": "Approve",
            "approve application": "Approve",
            # Approve with Conditions variants
            "approve with conditions": "Approve with Conditions",
            "approved with conditions": "Approve with Conditions",
            "conditional approve": "Approve with Conditions",
            "approve with condition": "Approve with Conditions",
            # Manual Review variants
            "manual review": "Manual Review",
            "needs manual review": "Manual Review",
            "refer to underwriter": "Manual Review",
            "underwriter review": "Manual Review",
            # Decline variants
            "decline": "Decline",
            "rejected": "Decline",
            "reject": "Decline",
            "do not approve": "Decline",
        }
        if s in mapping:
            payload["final_recommendation"] = mapping[s]
    return payload


async def run_gemini(qse: QSEReportInput, analysis_id: str) -> QAAQualitativeReport:
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        configured_model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
        # Discover models available to this key; prefer pro then flash using full IDs
        available = discover_supported_models(api_key)
        avail_set = set(available)

        # Try configured first (support both short and full configured names)
        configured_full = configured_model if configured_model.startswith("models/") else f"models/{configured_model}"
        candidates: List[str] = []
        if configured_full in avail_set:
            candidates.append(configured_full)
        # Then add best pro and flash options based on current families
        pro_tokens = [
            "gemini-2.5-pro",
            "gemini-pro-latest",
            "gemini-2.0-pro",
            "gemini-pro",
        ]
        flash_tokens = [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
            "gemini-2.0-flash-lite",
            "gemini-flash",
        ]

        def find_first_available(tokens: List[str]) -> str | None:
            for tok in tokens:
                for n in available:
                    if tok in n:
                        return n
            return None

        for c in [find_first_available(pro_tokens), find_first_available(flash_tokens)]:
            if c and c not in candidates:
                candidates.append(c)
        if not candidates:
            raise DownstreamError(
                f"No supported Gemini models available to this API key. Available: {available}"
            )
        prompt = build_prompt(qse, analysis_id)

        # Retries with exponential backoff and timeout
        max_retries = 3
        timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12.0"))
        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                # Try each candidate model; skip quickly on not-found/unsupported errors
                for model_name in candidates:
                    try:
                        model = configure(api_key, model_name)
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
                        # Validate JSON strictly; normalize enums to tolerate minor wording variations
                        try:
                            obj = json.loads(data)
                        except Exception as je:
                            raise DownstreamError(f"Invalid JSON from Gemini: {je}; raw={data[:300]}")
                        obj = _normalize_enums(obj)
                        try:
                            qaa = QAAQualitativeReport.model_validate(obj)
                        except Exception as ve:
                            raise DownstreamError(f"Invalid JSON from Gemini: {ve}; raw={data[:300]}")
                        if not qaa.analysis_id:
                            qaa.analysis_id = analysis_id
                        return qaa
                    except Exception as me:
                        # If specific model error suggests not found/unsupported, try next candidate without delaying
                        msg = str(me)
                        if (
                            "not found" in msg
                            or "not supported" in msg
                            or "404 models/" in msg
                            or "Model does not support generateContent" in msg
                        ):
                            last_err = me
                            continue
                        # Otherwise, propagate to outer retry/backoff
                        raise me
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    break
    except Exception as e:
        last_err = e

    raise DownstreamError(str(last_err) if last_err else "Gemini call failed")


async def run_gemini_explainability(qse: QSEReportInput, analysis_id: str) -> ExplainabilityExtended:
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        configured_model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
        available = discover_supported_models(api_key)
        avail_set = set(available)

        configured_full = configured_model if configured_model.startswith("models/") else f"models/{configured_model}"
        candidates: List[str] = []
        if configured_full in avail_set:
            candidates.append(configured_full)
        pro_tokens = [
            "gemini-2.5-pro",
            "gemini-pro-latest",
            "gemini-2.0-pro",
            "gemini-pro",
        ]
        flash_tokens = [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
            "gemini-2.0-flash-lite",
            "gemini-flash",
        ]

        def find_first_available(tokens: List[str]) -> str | None:
            for tok in tokens:
                for n in available:
                    if tok in n:
                        return n
            return None

        for c in [find_first_available(pro_tokens), find_first_available(flash_tokens)]:
            if c and c not in candidates:
                candidates.append(c)
        if not candidates:
            raise DownstreamError(
                f"No supported Gemini models available to this API key. Available: {available}"
            )
        prompt = build_explainability_prompt(qse, analysis_id)

        max_retries = 3
        timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12.0"))
        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                for model_name in candidates:
                    try:
                        model = configure(api_key, model_name)
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

                        data = resp.text
                        try:
                            obj = json.loads(data)
                        except Exception as je:
                            raise DownstreamError(f"Invalid JSON from Gemini: {je}; raw={data[:300]}")
                        try:
                            return ExplainabilityExtended.model_validate(obj)
                        except Exception as ve:
                            raise DownstreamError(f"Invalid JSON from Gemini: {ve}; raw={data[:300]}")
                    except Exception as me:
                        msg = str(me)
                        if (
                            "not found" in msg
                            or "not supported" in msg
                            or "404 models/" in msg
                            or "Model does not support generateContent" in msg
                        ):
                            last_err = me
                            continue
                        raise me
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    break
    except Exception as e:
        last_err = e

    raise DownstreamError(str(last_err) if last_err else "Gemini explainability call failed")