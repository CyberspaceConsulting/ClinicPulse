import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import de from '../frontend/src/i18n/locales/de.js'
import en from '../frontend/src/i18n/locales/en.js'

// Placeholders such as {unit} or {a_unit} are filled with the facility terminology (terms.ts).
const termsSource = readFileSync(new URL('../frontend/src/i18n/terms.ts', import.meta.url), 'utf8')
const germanSource = termsSource.slice(termsSource.indexOf('function germanTokens'), termsSource.indexOf('function englishTokens'))
const englishSource = termsSource.slice(termsSource.indexOf('function englishTokens'), termsSource.indexOf('/** Replacement values'))
const lowerFirst = (value) => value.charAt(0).toLowerCase() + value.slice(1)
const isToken = (source, name) => new RegExp(`\\b${lowerFirst(name)}\\s*:`).test(source)
const placeholders = (value) => [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1])

test('locale catalogs have the same keys and interpolation placeholders', () => {
  assert.deepEqual(Object.keys(de).sort(), Object.keys(en).sort())
  for (const key of Object.keys(en)) {
    assert.ok(de[key].trim(), `German translation is empty: ${key}`)
    assert.ok(en[key].trim(), `English translation is empty: ${key}`)
    const values = (value, source) => placeholders(value).filter((name) => !isToken(source, name)).sort()
    assert.deepEqual(values(de[key], germanSource), values(en[key], englishSource), `Placeholder mismatch: ${key}`)
  }
})

test('terminology placeholders only use tokens defined for their language', () => {
  for (const [language, catalog, source] of [['de', de, germanSource], ['en', en, englishSource]]) {
    for (const [key, text] of Object.entries(catalog)) {
      for (const name of placeholders(text).filter((item) => /unit/i.test(item))) {
        assert.ok(isToken(source, name), `Undefined terminology placeholder {${name}} in ${language}:${key}`)
      }
    }
  }
})
