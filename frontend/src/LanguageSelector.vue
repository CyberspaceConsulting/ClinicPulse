<script setup lang="ts">
import { locale, localeOptions, t } from './i18n'

defineProps<{ compact?: boolean }>()
</script>

<template>
  <div class="language-control">
    <label class="language-selector">
      <span aria-hidden="true">{{ localeOptions.find((option) => option.value === locale)?.flag }}</span>
      <span class="sr-only">{{ t('language.label') }}</span>
      <select v-model="locale">
        <option v-for="option in localeOptions" :key="option.value" :value="option.value" :lang="option.value">{{ t(option.label) }}</option>
      </select>
    </label>
    <span v-if="locale === 'en' && !compact" class="language-notice" role="status">{{ t('language.incomplete') }}</span>
  </div>
</template>
