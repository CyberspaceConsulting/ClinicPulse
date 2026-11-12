<script setup lang="ts">
import { ref, watch } from 'vue'
import { locale, t } from './i18n'

const props = withDefaults(defineProps<{
  modelValue: string
  label: string
  min?: string
  required?: boolean
}>(), {
  min: undefined,
  required: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const textInput = ref<HTMLInputElement | null>(null)
const datePicker = ref<HTMLInputElement | null>(null)
const textValue = ref('')
let emittedValue: string | null = null

function formatDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return ''
  const [, year, month, day] = match
  return locale.value === 'de' ? `${day}/${month}/${year}` : `${month}/${day}/${year}`
}

function parseDate(value: string) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value.trim())
  if (!match) return ''

  const first = Number(match[1])
  const second = Number(match[2])
  const year = Number(match[3])
  const [day, month] = locale.value === 'de' ? [first, second] : [second, first]
  const date = new Date(0)
  date.setUTCHours(0, 0, 0, 0)
  date.setUTCFullYear(year, month - 1, day)

  if (
    year < 1
    || date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) return ''

  const iso = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  return props.min && iso < props.min ? '' : iso
}

watch([() => props.modelValue, locale], ([value]) => {
  if (emittedValue === value) {
    emittedValue = null
    return
  }
  textValue.value = formatDate(value)
}, { immediate: true })

function updateFromText(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const value = input.value.trim() ? parseDate(input.value) : ''
  textValue.value = value ? formatDate(value) : input.value
  input.value = textValue.value
  input.setCustomValidity(input.value.trim() && !value ? t('date.invalid') : '')
  emittedValue = value
  emit('update:modelValue', value)
}

function openPicker() {
  const picker = datePicker.value
  if (!picker) return
  if (typeof picker.showPicker === 'function') picker.showPicker()
  else picker.click()
}

function updateFromPicker(event: Event) {
  const value = (event.currentTarget as HTMLInputElement).value
  textValue.value = formatDate(value)
  textInput.value?.setCustomValidity('')
  emittedValue = value
  emit('update:modelValue', value)
}
</script>

<template>
  <span class="date-input">
    <input
      ref="textInput"
      :value="textValue"
      :aria-label="label"
      type="text"
      inputmode="numeric"
      maxlength="10"
      :pattern="'[0-9]{2}/[0-9]{2}/[0-9]{4}'"
      :placeholder="locale === 'de' ? 'TT/MM/JJJJ' : 'MM/DD/YYYY'"
      :required="required"
      @input="updateFromText"
    />
    <button class="date-picker-button" type="button" :aria-label="t('date.choose')" :title="t('date.choose')" @click="openPicker">▦</button>
    <input
      ref="datePicker"
      class="date-picker-native"
      type="date"
      :value="modelValue"
      :min="min"
      :aria-label="t('date.choose')"
      tabindex="-1"
      aria-hidden="true"
      @change="updateFromPicker"
    />
  </span>
</template>