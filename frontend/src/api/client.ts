/** 唯一的后端调用出口。所有请求带 cookie，错误统一成 ApiError。 */

import { createSseParser, type SseEvent } from '../lib/sse';

const BASE = import.meta.env.VITE_API_BASE ?? '';

/** 给非 fetch 的场景（`<img src>` 等）拼上同一个 API 前缀。 */
export function apiPath(path: string): string {
  return `${BASE}${path}`;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === '') continue;
    params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `${path}?${serialized}` : path;
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = response.statusText || '请求失败';
  try {
    const payload: unknown = await response.json();
    if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
      const raw = (payload as { detail: unknown }).detail;
      detail = typeof raw === 'string' ? raw : JSON.stringify(raw);
    }
  } catch {
    // 非 JSON 响应，保留 statusText
  }
  return new ApiError(response.status, detail);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...init.headers,
    },
  });

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** POST 并逐帧消费 SSE。响应不是 2xx 时交给 parseError（预检失败仍是普通 JSON 错误）。 */
async function streamRequest(
  path: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  if (!response.body) throw new ApiError(response.status, '流式响应没有内容');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
  }
}

export const http = {
  get: <T>(path: string, query?: Query) => request<T>(withQuery(path, query)),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  /** SSE：逐帧回调，响应结束才 resolve；响应非 2xx 时和普通请求一样抛 ApiError。 */
  stream: (path: string, body: unknown, onEvent: (event: SseEvent) => void): Promise<void> =>
    streamRequest(path, body, onEvent),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, file: File | Blob, filename = 'file') => {
    const form = new FormData();
    form.append('file', file, filename);
    return request<T>(path, { method: 'POST', body: form });
  },
};

/** 触发浏览器下载（导出 OPML / JSON）。 */
export function download(path: string, filename: string): void {
  const anchor = document.createElement('a');
  anchor.href = `${BASE}${path}`;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

/** 前端主动下载二进制/文本内容（用于 Markdown 导出）。 */
export function downloadText(filename: string, text: string, mime = 'text/markdown'): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
