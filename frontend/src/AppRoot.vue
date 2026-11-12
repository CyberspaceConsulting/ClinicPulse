<script setup lang="ts">
import { onErrorCaptured, ref, watchEffect } from 'vue'
import App from './App.vue'
import LanguageSelector from './LanguageSelector.vue'
import { t } from './i18n'

const notFound = !['/', '/index.html'].includes(window.location.pathname)
const failed = ref(false)

watchEffect(() => {
  if (notFound || failed.value) {
    document.title = `ClinicPulse - ${t(notFound ? 'errorPage.notFoundTitle' : 'errorPage.failureTitle')}`
  }
})

onErrorCaptured(() => {
  failed.value = true
  return false
})
</script>

<template>
  <main v-if="notFound || failed" class="login-shell">
    <section class="login-card error-page" aria-labelledby="error-title">
      <LanguageSelector />
      <div class="brand-mark">C</div>
      <p class="eyebrow">{{ notFound ? '404' : 'ClinicPulse' }}</p>
      <h1 id="error-title">{{ t(notFound ? 'errorPage.notFoundTitle' : 'errorPage.failureTitle') }}</h1>
      <p class="muted">{{ t(notFound ? 'errorPage.notFoundDescription' : 'errorPage.failureDescription') }}</p>
      <a class="primary error-page-action" href="/">{{ t(notFound ? 'errorPage.home' : 'errorPage.reload') }}</a>
    </section>
  </main>
  <App v-else />
</template>