export type ApiMode = 'preview' | 'connected'
export type HostProfile = 'full' | 'private'
export type Method = 'GET' | 'POST'
export type Transport = (method: Method, path: string, payload?: unknown) => Promise<unknown>
export type FixtureReader = (path: string) => unknown

export function resolveApiMode(value: unknown): ApiMode {
  return value === 'connected' ? 'connected' : 'preview'
}

// The private host (deploy/private_dashboard.py) serves the read-only session API
// and nothing else. Only the exact token opts in; anything else is the full backend.
export function resolveHostProfile(value: unknown): HostProfile {
  return value === 'private' ? 'private' : 'full'
}

/** A read the current host has no data source for. Never sent, never retried. */
export class HostUnavailableError extends Error {
  constructor(path: string) {
    super(`Not available on this host: ${new URL(path, 'https://host.invalid').pathname}. No request was sent.`)
    this.name = 'HostUnavailableError'
  }
}

const SESSION_PREFIX = '/api/rehearsals'
const LIBRARY_PREFIX = '/api/library/'
// The owner's Settings (models, key, daily budget): the private host's one write.
export const SETTINGS_PATH = '/api/settings'
// Check connection: tests the saved key and models; sends no paid reply.
export const CHECK_PATH = '/api/settings/check'
// The heartbeat page: read-only status, today's wakes, cost and the market window.
export const HEARTBEAT_PATH = '/api/heartbeat'

export function servedByPrivateHost(path: string): boolean {
  const route = new URL(path, 'https://host.invalid').pathname
  return route === SESSION_PREFIX || route.startsWith(`${SESSION_PREFIX}/`) || route === SETTINGS_PATH
    || route === CHECK_PATH || route === HEARTBEAT_PATH
}

export function isSettingsWrite(method: Method, path: string): boolean {
  const route = new URL(path, 'https://host.invalid').pathname
  return method === 'POST' && (route === SETTINGS_PATH || route === CHECK_PATH)
}

/** The source library is imported text bundled with the site, read in the browser. */
export function readLocallyOnPrivateHost(path: string): boolean {
  return new URL(path, 'https://host.invalid').pathname.startsWith(LIBRARY_PREFIX)
}

export function createApiClient(mode: ApiMode, readFixture: FixtureReader, transport: Transport, host: HostProfile = 'full') {
  async function local<T>(path: string): Promise<T> {
    // Local source-library modules can load lazily. Never fall through to
    // transport on a local read error, and never share mutable source objects.
    return structuredClone(await readFixture(path)) as T
  }
  return async function request<T>(method: Method, path: string, payload?: unknown): Promise<T> {
    if (mode !== 'connected') {
      if (method !== 'GET') {
        throw new Error('Preview is read-only. No backend action was sent.')
      }
      return local<T>(path)
    }
    if (host === 'private') {
      if (method !== 'GET' && !isSettingsWrite(method, path)) throw new Error('This private host is read-only. No backend action was sent.')
      if (readLocallyOnPrivateHost(path)) return local<T>(path)
      if (!servedByPrivateHost(path)) throw new HostUnavailableError(path)
    }
    return await transport(method, path, payload) as T
  }
}
