import { describe, expect, it, vi } from 'vitest'
import { createApiClient, resolveApiMode } from '../src/data/client'
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
