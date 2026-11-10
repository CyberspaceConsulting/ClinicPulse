import { ref, watch } from 'vue'
import de from './locales/de.js'
import en from './locales/en.js'

export type TranslationKey = keyof typeof en

const translations = { de, en } satisfies Record<string, Record<TranslationKey, string>>
export type Locale = keyof typeof translations

export const localeOptions: { value: Locale; label: TranslationKey; flag: string }[] = [
  { value: 'de', label: 'language.de', flag: '🇩🇪' },
  { value: 'en', label: 'language.en', flag: '🇬🇧' },
]

function isLocale(value: string | null): value is Locale {
  return value !== null && Object.hasOwn(translations, value)
}

const storageKey = 'clinicpulse-locale'
const storedLocale = localStorage.getItem(storageKey)
export const locale = ref<Locale>(isLocale(storedLocale) ? storedLocale : 'de')

watch(locale, (value) => {
  document.documentElement.lang = value
  localStorage.setItem(storageKey, value)
}, { immediate: true })

export function t(key: TranslationKey, values: Record<string, string | number> = {}): string {
  return translations[locale.value][key].replace(/\{(\w+)\}/g, (placeholder, name: string) => {
    const value = values[name]
    if (value === undefined) throw new Error(`Missing value for ${placeholder} in translation ${key}`)
    return String(value)
  })
}
