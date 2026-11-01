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
  if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`)
  return (await r.json()) as T
}

export const getJSON = <T>(path: string) => request<T>(path)

export const sendJSON = <T>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown) =>
  request<T>(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const postJSON = <T>(path: string, body?: unknown) => sendJSON<T>('POST', path, body)
