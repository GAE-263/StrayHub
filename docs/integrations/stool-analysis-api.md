# Stool analysis provider

The worker can optionally send server-classified `subject=stool` report media to an external
stool-photo analysis API. Care report persistence does not depend on this provider.

## Configuration

Set all three values in the worker environment:

```text
STOOL_API_URL=https://provider.example
STOOL_API_KEY=<secret>
STOOL_TIMEOUT_SECONDS=30
```

If URL or key is absent, the worker keeps the current safe local/mock provider policy. The API key
must be supplied through the runtime secret environment and must never be committed or logged.

## Request

The adapter sends one stool image per request:

```http
POST /v1/analyze/base64
X-API-Key: <secret>
Content-Type: application/json

{"image_base64":"<base64>"}
```

Only cleaned media attached to the target report, owned by the current organization, and carrying
the server-assigned `stool` subject is eligible. Portrait, null/unknown-subject and cross-shelter
media are filtered before object download. A report without eligible stool media records a safe
`no_stool_media` skip and makes no provider call.

## Output governance

The complete provider JSON is retained as authorized-review `raw_ai_output`. Formal observations
are restricted to the canonical `defecation.normal`, `defecation.soft`, or
`defecation.abnormal` descriptive suggestions and pass the existing AI output validator. Scores,
assessments and care recommendations never enter the formal observation.

Timeouts, network errors, HTTP 408/429 and 5xx responses are retryable with bounded exponential
backoff. Deterministic 4xx rejections and invalid formal output are terminal. None of these outcomes
roll back or delete the submitted care report.
