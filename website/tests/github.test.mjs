import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fetchLatestVersion, fetchStars, formatStars } from '../src/lib/github.ts'

const answer = (status, body) => async () => new Response(JSON.stringify(body), { status })

test('formatStars keeps small counts exact and shortens thousands', () => {
  assert.equal(formatStars(0), '0')
  assert.equal(formatStars(5), '5')
  assert.equal(formatStars(999), '999')
  assert.equal(formatStars(1000), '1k')
  assert.equal(formatStars(1234), '1.2k')
  assert.equal(formatStars(15600), '15.6k')
})

test('fetchStars reads the stargazer count', async () => {
  assert.equal(await fetchStars('o/r', answer(200, { stargazers_count: 42 })), 42)
})

test('fetchStars sends the token when there is one', async () => {
  let sent
  const spy = async (_url, init) => {
    sent = init.headers
    return new Response(JSON.stringify({ stargazers_count: 1 }))
  }
  await fetchStars('o/r', spy, 'secret')
  assert.equal(sent.Authorization, 'Bearer secret')
})

test('fetchStars gives null instead of failing the build', async () => {
  assert.equal(await fetchStars('o/r', answer(403, { message: 'rate limited' })), null)
  assert.equal(await fetchStars('o/r', answer(200, { stargazers_count: 'many' })), null)
  assert.equal(await fetchStars('o/r', async () => { throw new Error('offline') }), null)
})

test('fetchLatestVersion reads the latest release tag without its v', async () => {
  assert.equal(await fetchLatestVersion('o/r', answer(200, { tag_name: 'v0.2.0' })), '0.2.0')
  assert.equal(await fetchLatestVersion('o/r', answer(200, { tag_name: 'v1.10.3' })), '1.10.3')
})

test('fetchLatestVersion gives null for no release or an odd tag', async () => {
  assert.equal(await fetchLatestVersion('o/r', answer(404, { message: 'Not Found' })), null)
  assert.equal(await fetchLatestVersion('o/r', answer(200, { tag_name: 'nightly; rm -rf /' })), null)
})
