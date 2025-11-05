import os
import logging
import httpx
from .models import QSEReportInput, ShapAnalysisExtended, ExplainabilityExtended
from .config import settings

logger = logging.getLogger(__name__)


class ExplainabilityError(Exception):
    pass


async def fetch_explainability(qse: QSEReportInput, timeout_s: float | None = None) -> ExplainabilityExtended | None:
    """
    Call upstream explainability service (e.g., SHAP/LIME) to obtain
    ExplainabilityExtended. Returns None if disabled or unavailable.
    """
    if not settings.EXPLAINABILITY_ENABLED or not settings.EXPLAINABILITY_URL:
        return None
    try:
        payload = qse.model_dump()  # use same input schema for compatibility
        url = settings.EXPLAINABILITY_URL.rstrip("/") + "/v1/explain"
        timeout = timeout_s or settings.REQUEST_TIMEOUT_SECONDS
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Expect upstream to return fields compatible with ExplainabilityExtended
            return ExplainabilityExtended(**data)
    except Exception as e:
        logger.warning(f"Explainability fetch failed: {e}")
        return None