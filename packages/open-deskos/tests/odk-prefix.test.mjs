import test from 'node:test'
import assert from 'node:assert/strict'
import { readOdkLinkConfig, DEFAULT_DESKS_FILE } from '../src/config.ts'

test('only ODK Link configuration names are read', () => {
  const config = readOdkLinkConfig({ ODK_LINK_ADDRESS: '127.0.0.1:8765', ODK_LINK_TOKEN: 'fixture-token' })
  assert.equal(config?.port, 8765)
  assert.equal(readOdkLinkConfig({ [['ODK', 'DESK', 'LINK', 'ADDRESS'].join('_')]: '127.0.0.1:8765', [['ODK', 'DESK', 'LINK', 'TOKEN'].join('_')]: 'fixture-token' }), null)
  assert.match(DEFAULT_DESKS_FILE, /[/\\]odk[/\\]desks\.json$/)
})
