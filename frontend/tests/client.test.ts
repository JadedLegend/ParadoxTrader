import { describe, expect, it, vi } from 'vitest'
import { HostUnavailableError, createApiClient, resolveApiMode, resolveHostProfile } from '../src/data/client'
import type { ApiMode } from '../src/data/client'
import { readFixture } from '../src/preview/readFixture'

const invalidModes: [string, unknown][] = [
  ['missing', undefined], ['null', null], ['empty', ''], ['preview', 'preview'],
  ['uppercase', 'CONNECTED'], ['title case', 'Connected'], ['trailing space', 'connected '],
  ['leading space', ' connected'], ['true string', 'true'], ['boolean', true],
  ['number', 1], ['object', { mode: 'connected' }], ['array', ['connected']],
]

describe('central fixture/connected client boundary', () => {
  it.each(invalidModes)('%s is not an affirmative connected opt-in', async (_name, value) => {
    expect(resolveApiMode(value)).toBe('preview')
    const transport = vi.fn(async () => ({ mustNeverReach: true }))
    const request = createApiClient(resolveApiMode(value), readFixture, transport)
    expect(await request('GET', '/api/status')).toMatchObject({ kind: 'fixture' })
    await expect(request('POST', '/api/init')).rejects.toThrow(/read-only/i)
    expect(transport).not.toHaveBeenCalled()
  })

  it('fails closed at the client boundary if an invalid runtime mode bypasses TypeScript', async () => {
    const transport = vi.fn(async () => ({ forbiddenTransport: true }))
    // Environment/configuration inputs are runtime values despite TypeScript.
    const request = createApiClient('CONNECTED' as ApiMode, readFixture, transport)
    expect(await request('GET', '/api/status')).toMatchObject({ kind: 'fixture' })
    await expect(request('POST', '/api/init')).rejects.toThrow(/read-only/i)
    expect(transport).not.toHaveBeenCalled()
  })

  it('only the exact connected token opts in, using a mock transport and no application request', async () => {
    expect(resolveApiMode('connected')).toBe('connected')
    const reader = vi.fn(() => { throw new Error('connected mode must not read fixtures') })
    const transport = vi.fn(async () => ({ kind: 'mock_transport', value: 123 }))
    const request = createApiClient(resolveApiMode('connected'), reader, transport)
    const payload = { solely: 'injected mock data' }
    expect(await request('GET', '/mock-only/read')).toEqual({ kind: 'mock_transport', value: 123 })
    expect(await request('POST', '/mock-only/write', payload)).toEqual({ kind: 'mock_transport', value: 123 })
    expect(transport.mock.calls).toEqual([
      ['GET', '/mock-only/read', undefined], ['POST', '/mock-only/write', payload],
    ])
    expect(reader).not.toHaveBeenCalled()
  })

  it.each(['/api/unknown', '/api/wake/tempest', '/api/agents/missing/journal', '/api/inbox/missing', '/api/agents/tempest/innermost'])('unknown preview route %s fails closed', async path => {
    const transport = vi.fn(async () => ({ forbiddenFallback: true }))
    const request = createApiClient('preview', readFixture, transport)
    await expect(request('GET', path)).rejects.toThrow(/No fixture is available.*No backend fallback was attempted/)
    expect(transport).not.toHaveBeenCalled()
  })

  it('does not fall through when the fixture reader fails', async () => {
    const error = new Error('broken fixture')
    const reader = vi.fn(() => { throw error })
    const transport = vi.fn(async () => ({ forbiddenFallback: true }))
    const request = createApiClient('preview', reader, transport)
    await expect(request('GET', '/fixture-only')).rejects.toBe(error)
    expect(reader).toHaveBeenCalledOnce()
    expect(transport).not.toHaveBeenCalled()
  })

  it('rejects mutations before even consulting the fixture reader', async () => {
    const reader = vi.fn(() => ({ fakeWrite: true }))
    const transport = vi.fn(async () => ({ fakeWrite: true }))
    const request = createApiClient('preview', reader, transport)
    await expect(request('POST', '/mock-only/write', { fake: true })).rejects.toThrow(/read-only/)
    expect(reader).not.toHaveBeenCalled()
    expect(transport).not.toHaveBeenCalled()
  })

  it('deep-clones nested fixture output separately on every read', async () => {
    const source = { items: [{ label: 'original', values: ['original'] }] }
    const reader = vi.fn(() => source)
    const transport = vi.fn(async () => null)
    const request = createApiClient('preview', reader, transport)
    const first = await request<typeof source>('GET', '/fixture-only')
    const second = await request<typeof source>('GET', '/fixture-only')
    first.items[0].label = 'changed'
    first.items[0].values.push('changed')
    expect(second).toEqual({ items: [{ label: 'original', values: ['original'] }] })
    expect(source).toEqual(second)
    expect(first.items).not.toBe(source.items)
    expect(second.items).not.toBe(source.items)
    expect(transport).not.toHaveBeenCalled()
  })

  it('propagates mock connected errors rather than reporting a fixture success', async () => {
    const error = new Error('mock transport failure')
    const reader = vi.fn(() => ({ fakeSuccess: true }))
    const transport = vi.fn(async () => { throw error })
    const request = createApiClient('connected', reader, transport)
    await expect(request('GET', '/mock-only/failure')).rejects.toBe(error)
    expect(reader).not.toHaveBeenCalled()
  })
})

const invalidProfiles: [string, unknown][] = [
  ['missing', undefined], ['null', null], ['empty', ''], ['full', 'full'], ['uppercase', 'PRIVATE'],
  ['title case', 'Private'], ['trailing space', 'private '], ['leading space', ' private'],
  ['boolean', true], ['number', 1], ['object', { profile: 'private' }], ['array', ['private']],
]

describe('private host profile boundary', () => {
  it('only the exact private token selects the private host', () => {
    expect(resolveHostProfile('private')).toBe('private')
  })

  it.each(invalidProfiles)('%s resolves to the full host', (_name, value) => {
    expect(resolveHostProfile(value)).toBe('full')
  })

  function privateClient() {
    const reader = vi.fn(() => ({ kind: 'local_library' }))
    const transport = vi.fn(async () => ({ kind: 'server' }))
    return { reader, transport, request: createApiClient('connected', reader, transport, 'private') }
  }

  it.each(['/api/rehearsals', '/api/rehearsals?limit=20&offset=0', '/api/rehearsals/x', '/api/rehearsals/x/jobs'])('GET %s reaches the server transport', async path => {
    const { reader, transport, request } = privateClient()
    expect(await request('GET', path)).toEqual({ kind: 'server' })
    expect(transport).toHaveBeenCalledExactlyOnceWith('GET', path, undefined)
    expect(reader).not.toHaveBeenCalled()
  })

  it('reads the library locally and never sends it to the server', async () => {
    const { reader, transport, request } = privateClient()
    expect(await request('GET', '/api/library/documents?limit=50&offset=0')).toEqual({ kind: 'local_library' })
    expect(reader).toHaveBeenCalledExactlyOnceWith('/api/library/documents?limit=50&offset=0')
    expect(transport).not.toHaveBeenCalled()
  })

  it.each(['/api/status', '/api/forum', '/api/forum/threads', '/api/queue', '/api/config', '/api/lineage/inquiries', '/api/rehearsalsX', '/api/rehearsals-x/jobs', '/api/libraryX'])('GET %s is unavailable and nothing is sent', async path => {
    const { reader, transport, request } = privateClient()
    const failure = request('GET', path)
    await expect(failure).rejects.toBeInstanceOf(HostUnavailableError)
    await expect(failure).rejects.toThrow(/Not available on this host.*No request was sent/)
    expect(transport).not.toHaveBeenCalled()
    expect(reader).not.toHaveBeenCalled()
  })

  it.each(['/api/rehearsals', '/api/rehearsals/x', '/api/library/documents', '/api/forum', '/api/queue/1/approve', '/api/config'])('POST %s is rejected as read-only and calls nothing', async path => {
    const { reader, transport, request } = privateClient()
    await expect(request('POST', path, { value: 1 })).rejects.toThrow(/read-only/)
    expect(transport).not.toHaveBeenCalled()
    expect(reader).not.toHaveBeenCalled()
  })

  it('preview mode ignores the private host profile', async () => {
    const transport = vi.fn(async () => ({ mustNeverReach: true }))
    const request = createApiClient('preview', readFixture, transport, 'private')
    expect(await request('GET', '/api/status')).toMatchObject({ kind: 'fixture' })
    await expect(request('POST', '/api/init')).rejects.toThrow(/Preview is read-only/)
    expect(transport).not.toHaveBeenCalled()
  })

  it('the full connected host still passes every request to the transport', async () => {
    const reader = vi.fn(() => { throw new Error('full host must not read locally') })
    const transport = vi.fn(async () => ({ kind: 'server' }))
    for (const request of [createApiClient('connected', reader, transport, 'full'), createApiClient('connected', reader, transport)]) {
      expect(await request('GET', '/api/status')).toEqual({ kind: 'server' })
      expect(await request('GET', '/api/library/documents')).toEqual({ kind: 'server' })
      expect(await request('POST', '/api/forum', { content: 'x' })).toEqual({ kind: 'server' })
    }
    expect(transport).toHaveBeenCalledTimes(6)
    expect(reader).not.toHaveBeenCalled()
  })
})

describe('private host settings routes', () => {
  it('allows only the settings save and the connection check as writes', async () => {
    const { isSettingsWrite, servedByPrivateHost } = await import('../src/data/client')
    expect(isSettingsWrite('POST', '/api/settings')).toBe(true)
    expect(isSettingsWrite('POST', '/api/settings/check')).toBe(true)
    expect(servedByPrivateHost('/api/settings/check')).toBe(true)
    expect(isSettingsWrite('POST', '/api/settings/other')).toBe(false)
    expect(isSettingsWrite('GET', '/api/settings/check')).toBe(false)
  })

  it('serves the heartbeat page read-only', async () => {
    const { isSettingsWrite, servedByPrivateHost } = await import('../src/data/client')
    expect(servedByPrivateHost('/api/heartbeat')).toBe(true)
    expect(isSettingsWrite('POST', '/api/heartbeat')).toBe(false)
  })
})
