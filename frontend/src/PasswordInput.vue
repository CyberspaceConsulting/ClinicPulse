<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  label: string
  autocomplete?: string
  required?: boolean
  optional?: boolean
}>(), {
  autocomplete: 'new-password',
  required: false,
  optional: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const breachStatus = ref<'idle' | 'checking' | 'safe' | 'compromised' | 'unavailable'>('idle')
const breachCount = ref(0)
let debounceTimer: ReturnType<typeof setTimeout> | undefined
let activeController: AbortController | undefined

const strength = computed(() => {
  const value = props.modelValue
  let score = 0
  if (value.length >= 8) score++
  if (value.length >= 12) score++
  if (value.length >= 16) score++
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score++
  if (/\d/.test(value)) score++
  if (/[^A-Za-z0-9]/.test(value)) score++
  if (value.length < 8) return { score: 0, label: 'Mindestens 8 Zeichen erforderlich' }
  if (score <= 2) return { score: 1, label: 'Schwach' }
  if (score <= 4) return { score: 2, label: 'Mittel' }
  return { score: 3, label: 'Stark' }
})

watch(() => props.modelValue, (value) => {
  clearTimeout(debounceTimer)
  activeController?.abort()
  breachStatus.value = 'idle'
  breachCount.value = 0
  if (value.length < 8) return
  breachStatus.value = 'checking'
  debounceTimer = setTimeout(() => void checkBreach(value), 500)
})

async function checkBreach(value: string) {
  activeController = new AbortController()
  try {
    const response = await fetch('/api/password/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: value }),
      signal: activeController.signal,
    })
    if (!response.ok) throw new Error(`Prüfung fehlgeschlagen (${response.status})`)
    const result = await response.json() as { compromised_count: number }
    if (props.modelValue !== value) return
    breachCount.value = result.compromised_count
    breachStatus.value = result.compromised_count ? 'compromised' : 'safe'
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    if (props.modelValue === value) breachStatus.value = 'unavailable'
  }
}

onBeforeUnmount(() => {
  clearTimeout(debounceTimer)
  activeController?.abort()
})
</script>

<template>
  <label class="password-input">
    {{ label }}<span v-if="optional" class="optional"> (optional)</span>
    <input
      type="password"
      :value="modelValue"
      :autocomplete="autocomplete"
      :required="required"
      minlength="8"
      maxlength="256"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="modelValue" class="password-strength" :class="`strength-${strength.score}`" aria-live="polite">
      Stärke: {{ strength.label }}
    </span>
    <span v-else class="password-breach muted">Mindestens 8 Zeichen; eine längere und abwechslungsreiche Passphrase ist sicherer.</span>
    <span v-if="breachStatus === 'checking'" class="password-breach muted">Prüfe auf bekannte Datenpannen …</span>
    <span v-else-if="breachStatus === 'safe'" class="password-breach password-safe">Nicht in bekannten Datenpannen gefunden</span>
    <span v-else-if="breachStatus === 'compromised'" class="password-breach password-compromised">In Datenpannen gefunden ({{ breachCount }} Mal). Bitte ein anderes Passwort wählen.</span>
    <span v-else-if="breachStatus === 'unavailable'" class="password-breach muted">Datenpannen-Prüfung momentan nicht verfügbar; die lokale Stärkeanzeige funktioniert weiterhin.</span>
    <small class="muted">Das Passwort wird nicht an HIBP gesendet. Für den Abgleich wird nur ein gekürztes SHA-1-Präfix übertragen.</small>
  </label>
</template>
