"""Thin client for Google Gemini's `generateContent` REST endpoint — used
only by the adoption suitability-analysis feature (see line_adoption_flex.py
/ adoption_matching.py docstrings for why this is a separate integration
from the unrelated `services/worker` AI job pipeline).

Two auth modes, picked automatically by what's configured:

- API key (`api_key`) — Google AI Studio's Generative Language API,
  `?key=...` on the query string.
- Service account (`service_account_path`) — Vertex AI's own copy of the
  same models, authenticated as that service account via a hand-signed
  OAuth2 JWT-bearer exchange (RFC 7523) using `cryptography`, which this
  project already depends on for PII encryption — no `google-auth`/
  `google-cloud-aiplatform` SDK needed for this one token exchange.

Deliberately never raises: every failure mode (missing credentials, network
error, non-2xx, malformed JSON, missing fields) collapses to `None` so a
caller can treat this as "the analysis wasn't available this time" without a
try/except of its own — this runs from a best-effort background task, never
inline with a reply the adopter is waiting on."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from services.api.app.observability.logging import get_logger

logger = get_logger(__name__)

_AI_STUDIO_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# Refresh a bit before the token's real expiry so a slow request never races
# a token that expires mid-flight.
_TOKEN_REFRESH_MARGIN_SECONDS = 60
# Gemini's default sampling temperature (~1.0) occasionally hallucinates a
# field the free text never mentioned when extracting questionnaire answers
# (confirmed by reproducing the exact same input against the live model) —
# a low temperature makes this strict "grounded in the text, or null"
# classification task noticeably more conservative. Not applied to any
# other call: the adopter-facing reply/explanation text elsewhere benefits
# from Gemini's default variety, this one specifically doesn't want it.
_EXTRACTION_TEMPERATURE = 0.1


@dataclass(frozen=True)
class GeminiSuitabilityResult:
    score: int
    explanation: str


@dataclass(frozen=True)
class GeminiAnimalRecommendation:
    animal_id: str
    reason: str


@dataclass(frozen=True)
class GeminiRankedRecommendation:
    animal_id: str
    score: int
    explanation: str


@dataclass(frozen=True)
class GeminiGrowthDiaryAnalysis:
    mood: str  # positive | neutral | concern
    adopter_reply: str
    staff_summary: str


_VALID_GROWTH_DIARY_MOODS = {"positive", "neutral", "concern"}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_service_account_jwt(service_account_info: dict[str, Any], *, scope: str) -> str:
    """RFC 7523 JWT-bearer assertion, self-signed with the service account's
    own RSA private key — this is the one piece Google's client libraries
    normally do for you; hand-rolled here to avoid pulling in `google-auth`
    for what's otherwise a single token exchange."""
    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    claims = {
        "iss": service_account_info["client_email"],
        "scope": scope,
        "aud": _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = (
        f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    ).encode()
    private_key = serialization.load_pem_private_key(
        service_account_info["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
    return signing_input.decode() + "." + _b64url(signature)


class GeminiClient:
    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None = None,
        service_account_path: str | None = None,
        location: str = "us-central1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key and not service_account_path:
            raise ValueError("GeminiClient needs either api_key or service_account_path")
        self.api_key = api_key
        self.location = location
        self.model_name = model_name
        self._service_account_info: dict[str, Any] | None = None
        self._project_id: str | None = None
        if service_account_path:
            # A local JSON read at construction time, not network I/O — the
            # actual key material never leaves this process; only the
            # resulting short-lived OAuth2 access token goes over the wire.
            info = json.loads(Path(service_account_path).read_text(encoding="utf-8"))
            self._service_account_info = info
            self._project_id = info["project_id"]
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0

    async def _vertex_access_token(self) -> str:
        if self._cached_token and time.monotonic() < self._token_expires_at:
            return self._cached_token
        assertion = _sign_service_account_jwt(
            self._service_account_info,  # type: ignore[arg-type]
            scope=_CLOUD_PLATFORM_SCOPE,
        )
        response = await self._client.post(
            _TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._cached_token = payload["access_token"]
        self._token_expires_at = (
            time.monotonic() + payload.get("expires_in", 3600) - _TOKEN_REFRESH_MARGIN_SECONDS
        )
        return self._cached_token

    async def _generate_content(
        self,
        prompt: str,
        *,
        image: bytes | None = None,
        image_mime_type: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Returns the raw text of Gemini's one response part. Raises on any
        failure — callers are the `try/except -> None` boundary, matching
        this module's "never raises" contract at the public-method level.

        `image`, when given, is sent as a second `parts` entry (inline
        base64) alongside the text prompt — the same multimodal shape on
        both AI Studio and Vertex AI, so no other branching is needed here
        beyond the existing auth-mode split.

        `temperature`, when given, overrides Gemini's default sampling
        temperature (~1.0) — left unset for calls that want some natural-
        language variety (a warm adopter-facing reply, an explanation), but
        worth pinning low for a strict classification task like extracting
        questionnaire answers from free text, where "confidently grounded in
        the input, or null" matters far more than variety and a high default
        temperature measurably invites the odd hallucinated field."""
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": image_mime_type or "image/jpeg",
                        "data": base64.b64encode(image).decode("ascii"),
                    }
                }
            )
        generation_config: dict[str, Any] = {"responseMimeType": "application/json"}
        if temperature is not None:
            generation_config["temperature"] = temperature
        body = {
            # Vertex AI (unlike AI Studio) rejects a content entry with no
            # explicit "role" — harmless to always send it either way.
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        if self._service_account_info is not None:
            token = await self._vertex_access_token()
            # The "global" location is a real Vertex AI location (some
            # models — e.g. gemini-3.5-flash-lite — are served there and
            # 404 from region-pinned hosts), and it does NOT take a
            # location-prefixed hostname the way "us-central1" etc. do.
            host = (
                "aiplatform.googleapis.com"
                if self.location == "global"
                else f"{self.location}-aiplatform.googleapis.com"
            )
            url = (
                f"https://{host}/v1/projects/{self._project_id}/locations/"
                f"{self.location}/publishers/google/models/{self.model_name}:generateContent"
            )
            response = await self._client.post(
                url, headers={"Authorization": f"Bearer {token}"}, json=body
            )
        else:
            response = await self._client.post(
                f"{_AI_STUDIO_BASE}/{self.model_name}:generateContent",
                params={"key": self.api_key},
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    async def analyze_suitability(self, prompt: str) -> GeminiSuitabilityResult | None:
        try:
            text = await self._generate_content(prompt)
            parsed = json.loads(text)
            score = int(parsed["score"])
            explanation = str(parsed["explanation"])
        except Exception:
            logger.exception("gemini_suitability_analysis_failed")
            return None
        return GeminiSuitabilityResult(score=max(0, min(100, score)), explanation=explanation)

    async def recommend_alternatives(
        self, prompt: str, *, valid_animal_ids: set[str]
    ) -> list[GeminiAnimalRecommendation] | None:
        """Asks Gemini to pick 2-3 alternative animals (by id, copied
        verbatim from the candidate list embedded in `prompt`) given a free-
        text special request. `valid_animal_ids` guards against a
        hallucinated id slipping through to a Flex card with no real animal
        behind it — any recommendation naming an id outside this set is
        dropped rather than failing the whole call."""
        try:
            text = await self._generate_content(prompt)
            parsed = json.loads(text)
            raw_recommendations = parsed["recommendations"]
        except Exception:
            logger.exception("gemini_alternatives_recommendation_failed")
            return None
        recommendations: list[GeminiAnimalRecommendation] = []
        for item in raw_recommendations:
            try:
                animal_id = str(item["animal_id"])
                reason = str(item["reason"])
            except (KeyError, TypeError):
                continue
            if animal_id in valid_animal_ids:
                recommendations.append(
                    GeminiAnimalRecommendation(animal_id=animal_id, reason=reason)
                )
        return recommendations[:3]

    async def rank_recommendations(
        self, prompt: str, *, valid_animal_ids: set[str]
    ) -> list[GeminiRankedRecommendation] | None:
        """Asks Gemini to rerank a rule-filtered candidate pool (推薦名單
        path) — each pick carries its own 0-100 score and explanation,
        unlike `recommend_alternatives` which only attaches a reason.
        Same hallucination guard as `recommend_alternatives`: any id outside
        `valid_animal_ids` is dropped rather than failing the whole call."""
        try:
            text = await self._generate_content(prompt)
            parsed = json.loads(text)
            raw_recommendations = parsed["recommendations"]
        except Exception:
            logger.exception("gemini_recommendation_ranking_failed")
            return None
        results: list[GeminiRankedRecommendation] = []
        for item in raw_recommendations:
            try:
                animal_id = str(item["animal_id"])
                score = int(item["score"])
                explanation = str(item["explanation"])
            except (KeyError, TypeError, ValueError):
                continue
            if animal_id in valid_animal_ids:
                results.append(
                    GeminiRankedRecommendation(
                        animal_id=animal_id,
                        score=max(0, min(100, score)),
                        explanation=explanation,
                    )
                )
        return results[:5]

    async def extract_adoption_profile(
        self, prompt: str, *, valid_values: dict[str, set[str]]
    ) -> dict[str, str]:
        """Parses a free-text self-introduction into the same question-code
        answers the one-by-one questionnaire collects (see
        AdoptionProfileExtractionService). Any field Gemini omits, returns
        null for, or returns a value outside `valid_values[key]` for is
        simply absent from the result — the caller then knows to ask that
        one directly rather than trusting a hallucinated code. Returns {}
        (not None) on any failure, consistent with "nothing was extracted
        this round" rather than a distinct error case the caller has to
        handle separately."""
        try:
            text = await self._generate_content(prompt, temperature=_EXTRACTION_TEMPERATURE)
            parsed = json.loads(text)
        except Exception:
            logger.exception("gemini_adoption_profile_extraction_failed")
            return {}
        if not isinstance(parsed, dict):
            return {}
        result: dict[str, str] = {}
        for key, allowed in valid_values.items():
            value = parsed.get(key)
            if isinstance(value, str) and value in allowed:
                result[key] = value
        return result

    async def analyze_growth_diary_entry(
        self, prompt: str, *, image: bytes | None = None, image_mime_type: str | None = None
    ) -> GeminiGrowthDiaryAnalysis | None:
        """One call produces both outputs 毛孩日記 needs: a warm reply for the
        adopter and an objective observation summary for shelter staff, plus
        a mood classification that decides whether staff also get pushed a
        LINE notification (`concern`) or just the written record. `image`
        lets this look at the shared photo itself, not just its presence —
        see growth_diary_ai_analysis_service.py's prompt builder."""
        try:
            text = await self._generate_content(
                prompt, image=image, image_mime_type=image_mime_type
            )
            parsed = json.loads(text)
            mood = str(parsed["mood"]).strip().lower()
            adopter_reply = str(parsed["adopter_reply"])
            staff_summary = str(parsed["staff_summary"])
        except Exception:
            logger.exception("gemini_growth_diary_analysis_failed")
            return None
        if mood not in _VALID_GROWTH_DIARY_MOODS:
            mood = "neutral"
        return GeminiGrowthDiaryAnalysis(
            mood=mood, adopter_reply=adopter_reply, staff_summary=staff_summary
        )
