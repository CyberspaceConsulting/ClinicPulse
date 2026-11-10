import assert from 'node:assert/strict'
import test from 'node:test'
import de from '../frontend/src/i18n/locales/de.js'
import en from '../frontend/src/i18n/locales/en.js'

test('locale catalogs have the same keys and interpolation placeholders', () => {
  assert.deepEqual(Object.keys(de).sort(), Object.keys(en).sort())
  for (const key of Object.keys(en)) {
    assert.ok(de[key].trim(), `German translation is empty: ${key}`)
    assert.ok(en[key].trim(), `English translation is empty: ${key}`)
    const placeholders = (value) => [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort()
    assert.deepEqual(placeholders(de[key]), placeholders(en[key]), `Placeholder mismatch: ${key}`)
  }
})
