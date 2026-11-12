export type ApiMode = 'preview' | 'connected'
export type Method = 'GET' | 'POST'
export type Transport = (method: Method, path: string, payload?: unknown) => Promise<unknown>
export type FixtureReader = (path: string) => unknown

export function resolveApiMode(value: unknown): ApiMode {
  return value === 'connected' ? 'connected' : 'preview'
}

export function createApiClient(mode: ApiMode, readFixture: FixtureReader, transport: Transport) {
  return async function request<T>(method: Method, path: string, payload?: unknown): Promise<T> {
    if (mode !== 'connected') {
      if (method !== 'GET') {
        throw new Error('Preview is read-only. No backend action was sent.')
      }
      // Local source-library modules can load lazily. Never fall through to
      // transport on a local read error, and never share mutable source objects.
      return structuredClone(await readFixture(path)) as T
    }
    return await transport(method, path, payload) as T
  }
}
