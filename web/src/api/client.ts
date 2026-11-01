export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(path, { cache: 'no-store', ...init })
  } catch (e) {
    throw new ApiError(0, (e as Error).message || 'Network error')
  }
  if (!r.ok) {
    let msg = `HTTP ${r.status}`
    try {
      const b = await r.json()
      const d = b?.detail ?? b?.error
      if (typeof d === 'string' && d) msg = `${msg}: ${d}`
      else if (Array.isArray(d) && d.length) msg = `${msg}: ${d.map((x) => x?.msg ?? String(x)).join('; ')}`
    } catch { /* body is not JSON */ }
    throw new ApiError(r.status, msg)
  }
  try {
    return (await r.json()) as T
  } catch {
    throw new ApiError(r.status, 'Invalid response from server')
  }
}

export const getJSON = <T>(path: string) => request<T>(path)

export const sendJSON = <T>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown) =>
  request<T>(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const postJSON = <T>(path: string, body?: unknown) => sendJSON<T>('POST', path, body)

/** Like sendJSON, but a 200 reply whose body says `ok: false` is an error carrying the server's text. */
export async function sendOk<T extends { ok?: boolean; error?: string }>(
  method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown,
): Promise<T> {
  const r = await sendJSON<T>(method, path, body)
  if (r && r.ok === false) throw new ApiError(200, r.error || 'Request refused')
  return r
}
