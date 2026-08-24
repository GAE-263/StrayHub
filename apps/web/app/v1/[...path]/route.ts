import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 1_048_576;
const MAX_RESPONSE_BYTES = 10_485_760;
const STREAM_TIMEOUT_MS = 10_000;
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

type StreamReadResult = { ok: true; body: ArrayBuffer | null } | { ok: false };

function forwardedHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key)) headers.set(key, value);
  });
  return headers;
}

function errorResponse(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

function resolveApiOrigin(raw: string): URL | null {
  try {
    const origin = new URL(raw);
    const localDevelopment =
      origin.protocol === "http:" &&
      (origin.hostname === "127.0.0.1" || origin.hostname === "localhost");
    if (origin.protocol !== "https:" && !localDevelopment) return null;
    return origin;
  } catch {
    return null;
  }
}

async function readStream(
  stream: ReadableStream<Uint8Array> | null,
  maxBytes: number,
): Promise<StreamReadResult> {
  if (!stream) return { ok: true, body: null };

  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  const deadline = Date.now() + STREAM_TIMEOUT_MS;
  let totalBytes = 0;
  try {
    while (true) {
      let timeout: ReturnType<typeof setTimeout> | undefined;
      const remainingMs = deadline - Date.now();
      if (remainingMs <= 0) {
        await reader.cancel().catch(() => undefined);
        return { ok: false };
      }
      try {
        const result = await Promise.race([
          reader.read(),
          new Promise<never>((_, reject) => {
            timeout = setTimeout(
              () => reject(new Error("stream timeout")),
              remainingMs,
            );
          }),
        ]);
        if (result.done) break;
        if (result.value) {
          totalBytes += result.value.byteLength;
          if (totalBytes > maxBytes) {
            await reader.cancel().catch(() => undefined);
            return { ok: false };
          }
          chunks.push(result.value);
        }
      } finally {
        if (timeout) clearTimeout(timeout);
      }
    }
  } catch {
    await reader.cancel().catch(() => undefined);
    return { ok: false };
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(new ArrayBuffer(totalBytes));
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { ok: true, body: body.buffer };
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const rawApiBaseUrl = process.env.API_BASE_URL?.replace(/\/$/, "");
  const apiOrigin = rawApiBaseUrl ? resolveApiOrigin(rawApiBaseUrl) : null;
  if (!apiOrigin) return errorResponse(503, "API proxy is not configured");

  const hasBody = !["GET", "HEAD"].includes(request.method) && request.body;
  if (hasBody) {
    const contentLength = request.headers.get("content-length");
    const bodyBytes = contentLength ? Number(contentLength) : NaN;
    if (!Number.isSafeInteger(bodyBytes) || bodyBytes < 0) {
      return errorResponse(413, "Request body size is required");
    }
    if (bodyBytes > MAX_BODY_BYTES) {
      return errorResponse(413, "Request body is too large");
    }
  }

  const requestBody = hasBody
    ? await readStream(request.body, MAX_BODY_BYTES)
    : { ok: true as const, body: null };
  if (!requestBody.ok) return errorResponse(413, "Request body is invalid");

  const { path } = await context.params;
  if (path.some((pathSegment) => pathSegment === "." || pathSegment === "..")) {
    return errorResponse(400, "Invalid API path");
  }
  const basePath =
    apiOrigin.pathname === "/" ? "" : apiOrigin.pathname.replace(/\/$/, "");
  const targetUrl = new URL(
    `${basePath}/v1/${path.map((segment) => encodeURIComponent(segment)).join("/")}`,
    apiOrigin,
  );
  targetUrl.search = request.nextUrl.search;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers: forwardedHeaders(request),
      body: requestBody.body ?? undefined,
      cache: "no-store",
      redirect: "manual",
      signal: controller.signal,
    });

    if (upstream.status >= 300 && upstream.status < 400) {
      return errorResponse(502, "Upstream API redirect rejected");
    }

    const upstreamBody = await readStream(upstream.body, MAX_RESPONSE_BYTES);
    if (!upstreamBody.ok) {
      return errorResponse(503, "Upstream API response is unavailable");
    }

    const responseHeaders = new Headers();
    upstream.headers.forEach((value, key) => {
      if (!HOP_BY_HOP_HEADERS.has(key)) responseHeaders.set(key, value);
    });
    return new Response(upstreamBody.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return errorResponse(503, "Upstream API is temporarily unavailable");
  } finally {
    clearTimeout(timeout);
  }
}

export const GET = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
