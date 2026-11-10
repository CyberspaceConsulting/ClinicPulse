<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { locale, t } from './i18n'
import { apiErrorDetail } from './i18n/apiErrors'

type Target = { id: number; name: string; kind: string; config: Record<string, string>; enabled: boolean; retention_count: number }
type Settings = { schedule_enabled: boolean; frequency: 'daily' | 'weekly'; weekday: number; time_of_day: string; recipient_count: number; last_slot: string | null; timezone: string }
type Run = { id: number; started_at: string; trigger: string; target_name: string; filename: string | null; size_bytes: number | null; status: string; error: string | null }
type Recipient = { id: number; name: string; public_key: string; created_at: string }
type RemoteFile = { name: string; size: number; modified: string | null }
type Field = { key: string; label: string; secret?: boolean; hint?: string }

const kindLabels = computed<Record<string, string>>(() => ({ local: t('backup.local'), sftp: 'SFTP', webdav: t('backup.webdav'), s3: t('backup.s3') }))
const kindFields = computed<Record<string, Field[]>>(() => ({
  local: [{ key: 'subdir', label: t('backup.subdir'), hint: t('backup.subdirHint') }],
  sftp: [
    { key: 'host', label: t('backup.host') }, { key: 'port', label: t('backup.port') }, { key: 'username', label: t('backup.username') },
    { key: 'password', label: t('backup.password'), secret: true },
    { key: 'private_key', label: t('backup.privateKey'), secret: true },
    { key: 'directory', label: t('backup.directory') },
    { key: 'host_key_fingerprint', label: t('backup.fingerprint'), hint: t('backup.fingerprintHint') },
  ],
  webdav: [
    { key: 'url', label: t('backup.url'), hint: t('backup.urlHint') },
    { key: 'username', label: t('backup.username') }, { key: 'password', label: t('backup.appPassword'), secret: true },
  ],
  s3: [
    { key: 'endpoint_url', label: t('backup.endpoint') }, { key: 'region', label: t('backup.region') }, { key: 'bucket', label: t('backup.bucket') },
    { key: 'prefix', label: t('backup.prefix') }, { key: 'access_key', label: t('backup.accessKey') }, { key: 'secret_key', label: t('backup.secretKey'), secret: true },
  ],
}))
const weekdays = computed(() => Array.from({ length: 7 }, (_, index) =>
  new Intl.DateTimeFormat(locale.value, { weekday: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, 0, index + 1))),
))

const settings = ref<Settings | null>(null)
const recipients = ref<Recipient[]>([])
const recipientName = ref('')
const recipientKey = ref('')
const keyName = ref(t('backup.instance'))
const keyPassphrase = ref('')
const lastPublicKey = ref('')
const oneOffKey = ref('')
const recoveryKeyFile = ref<File | null>(null)
const recoveryKeyText = ref('')
const targets = ref<Target[]>([])
const runs = ref<Run[]>([])
const busy = ref(false)
const message = ref('')
const problem = ref('')
const form = reactive({ id: null as number | null, name: '', kind: 'local', config: {} as Record<string, string>, enabled: true, retention_count: 10 })
const showForm = ref(false)
const restorePassphrase = ref('')  // password of the recovery key file
const restoreConfirm = ref('')
const restoreFile = ref<File | null>(null)
const remoteTargetId = ref<number | null>(null)
const remoteFiles = ref<RemoteFile[]>([])
const remoteFile = ref('')

const currentFields = computed(() => kindFields.value[form.kind] ?? [])

async function call<T>(path: string, options: RequestInit = {}, json = true): Promise<T> {
  const response = await fetch(`/api/admin/backup${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: { ...(json ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error((data && 'detail' in data ? apiErrorDetail(data.detail) : null) ?? t('api.requestFailed', { status: response.status }))
  }
  if (response.status === 204) return undefined as T
  if (response.headers.get('content-type')?.includes('application/json')) return response.json() as Promise<T>
  return response.blob() as unknown as Promise<T>
}

async function guarded(action: () => Promise<void>, success = '') {
  busy.value = true
  message.value = ''
  problem.value = ''
  try {
    await action()
    if (success) message.value = success
  } catch (err) {
    problem.value = err instanceof Error ? err.message : t('backup.actionFailed')
  } finally {
    busy.value = false
  }
}

async function loadAll() {
  const [loadedSettings, loadedTargets, loadedRuns, loadedRecipients] = await Promise.all([
    call<Settings>('/settings'), call<Target[]>('/targets'), call<Run[]>('/runs?limit=10'), call<Recipient[]>('/recipients'),
  ])
  recipients.value = loadedRecipients
  settings.value = loadedSettings
  targets.value = loadedTargets
  runs.value = loadedRuns
}

async function saveSettings() {
  if (!settings.value) return
  const current = settings.value
  await guarded(async () => {
    settings.value = await call<Settings>('/settings', {
      method: 'PUT',
      body: JSON.stringify({
        schedule_enabled: current.schedule_enabled, frequency: current.frequency, weekday: current.weekday,
        time_of_day: current.time_of_day,
      }),
    })
  }, t('backup.settingsSaved'))
}

function newTarget() {
  Object.assign(form, { id: null, name: '', kind: 'local', config: {}, enabled: true, retention_count: 10 })
  showForm.value = true
}

function editTarget(target: Target) {
  Object.assign(form, { id: target.id, name: target.name, kind: target.kind, config: { ...target.config }, enabled: target.enabled, retention_count: target.retention_count })
  showForm.value = true
}

async function saveTarget() {
  await guarded(async () => {
    const body = JSON.stringify({ name: form.name, kind: form.kind, config: form.config, enabled: form.enabled, retention_count: form.retention_count })
    await call(form.id ? `/targets/${form.id}` : '/targets', { method: form.id ? 'PUT' : 'POST', body })
    showForm.value = false
    await loadAll()
  }, t('backup.targetSaved'))
}

async function removeTarget(target: Target) {
  if (!window.confirm(t('backup.removeTargetConfirm', { name: target.name }))) return
  await guarded(async () => {
    await call(`/targets/${target.id}`, { method: 'DELETE' })
    await loadAll()
  }, t('backup.targetRemoved'))
}

async function testTarget(target: Target) {
  await guarded(async () => { await call(`/targets/${target.id}/test`, { method: 'POST' }) }, t('backup.connectionSuccess', { name: target.name }))
}

async function runNow(target: Target) {
  await guarded(async () => {
    const run = await call<Run>(`/targets/${target.id}/run`, { method: 'POST' })
    await loadAll()
    if (run.status !== 'success') throw new Error(run.error ? apiErrorDetail(run.error) ?? t('backup.runFailed') : t('backup.runFailed'))
  }, t('backup.runSuccess', { name: target.name }))
}

async function downloadBackup() {
  await guarded(async () => {
    const response = await fetch('/api/admin/backup/download', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ public_key: oneOffKey.value.trim() || null }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error((data && 'detail' in data ? apiErrorDetail(data.detail) : null) ?? t('api.requestFailed', { status: response.status }))
    }
    const name = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? 'clinicpulse.cpbak'
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    URL.revokeObjectURL(url)
  }, t('backup.downloaded'))
}

async function addRecipient() {
  await guarded(async () => {
    await call('/recipients', { method: 'POST', body: JSON.stringify({ name: recipientName.value, public_key: recipientKey.value }) })
    recipientName.value = ''
    recipientKey.value = ''
    await loadAll()
  }, t('backup.recipientAdded'))
}

async function removeRecipient(item: Recipient) {
  if (!window.confirm(t('backup.removeRecipientConfirm', { name: item.name }))) return
  await guarded(async () => {
    await call(`/recipients/${item.id}`, { method: 'DELETE' })
    await loadAll()
  }, t('backup.recipientRemoved'))
}

async function createRecoveryKey() {
  await guarded(async () => {
    const response = await fetch('/api/admin/backup/recovery-key', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: keyName.value, passphrase: keyPassphrase.value, add_as_recipient: true }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error((data && 'detail' in data ? apiErrorDetail(data.detail) : null) ?? t('api.requestFailed', { status: response.status }))
    }
    lastPublicKey.value = response.headers.get('x-public-key') ?? ''
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = 'clinicpulse-recovery-key.cpkey'
    link.click()
    URL.revokeObjectURL(url)
    keyPassphrase.value = ''
    await loadAll()
  }, t('backup.keyDownloaded'))
}

async function selectRecoveryKey(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  recoveryKeyFile.value = file
  recoveryKeyText.value = file ? await file.text() : ''
}

function afterRestore() {
  message.value = t('backup.restoreComplete')
  window.setTimeout(() => window.location.reload(), 1500)
}

async function restoreUpload() {
  const file = restoreFile.value
  if (!file || !recoveryKeyText.value) return
  await guarded(async () => {
    await call('/restore', {
      method: 'POST', body: file,
      headers: { 'Content-Type': 'application/octet-stream', 'X-Recovery-Key': btoa(recoveryKeyText.value), 'X-Key-Passphrase': restorePassphrase.value, 'X-Restore-Confirm': restoreConfirm.value },
    }, false)
    afterRestore()
  })
}

async function loadRemoteFiles() {
  if (remoteTargetId.value === null) return
  const id = remoteTargetId.value
  await guarded(async () => {
    remoteFiles.value = await call<RemoteFile[]>(`/targets/${id}/files`)
    remoteFile.value = remoteFiles.value[0]?.name ?? ''
  })
}

async function restoreRemote() {
  if (remoteTargetId.value === null || !remoteFile.value || !recoveryKeyText.value) return
  const id = remoteTargetId.value
  await guarded(async () => {
    await call(`/targets/${id}/restore`, {
      method: 'POST', body: JSON.stringify({ filename: remoteFile.value, recovery_key: recoveryKeyText.value, key_passphrase: restorePassphrase.value, confirm: restoreConfirm.value }),
    })
    afterRestore()
  })
}

function selectRestoreFile(event: Event) {
  restoreFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function size(bytes: number | null) {
  if (bytes === null) return ''
  return bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

onMounted(() => { void guarded(loadAll) })
</script>

<template>
  <section class="backup-settings">
    <h3>{{ t('backup.title') }}</h3>
    <p class="muted">{{ t('backup.description') }}</p>
    <p v-if="message" class="planning-notice" role="status">{{ message }}</p>
    <p v-if="problem" class="error-message" role="alert">{{ problem }}</p>

    <div class="stack">
      <strong>{{ t('backup.recipients') }}</strong>
      <p v-if="!recipients.length" class="muted">{{ t('backup.noRecipients') }}</p>
      <div v-for="item in recipients" :key="item.id" class="management-row">
        <div><strong>{{ item.name }}</strong><small><code>{{ item.public_key }}</code></small></div>
        <button class="text-button danger-text" :disabled="busy" @click="removeRecipient(item)">{{ t('backup.remove') }}</button>
      </div>
      <form class="stack backup-target-form" @submit.prevent="createRecoveryKey">
        <strong>{{ t('backup.createKey') }}</strong>
        <label>{{ t('backup.name') }}<input v-model="keyName" maxlength="80" required /></label>
        <label>{{ t('backup.keyPassword') }}<input v-model="keyPassphrase" type="password" autocomplete="new-password" maxlength="200" required /></label>
        <button class="secondary" :disabled="busy">{{ t('backup.generateKey') }}</button>
        <p class="muted">{{ t('backup.keyWarning') }}</p>
        <p v-if="lastPublicKey" class="muted">{{ t('backup.publicKey') }} <code>{{ lastPublicKey }}</code></p>
      </form>
      <form class="stack backup-target-form" @submit.prevent="addRecipient">
        <strong>{{ t('backup.addOther') }}</strong>
        <label>{{ t('backup.name') }}<input v-model="recipientName" maxlength="80" required /></label>
        <label>{{ t('backup.publicKeyInput') }}<input v-model="recipientKey" required autocomplete="off" /></label>
        <button class="secondary" :disabled="busy">{{ t('backup.addRecipient') }}</button>
        <p class="muted">{{ t('backup.keygenIntro') }} <code>docker compose exec api python -m app.backup_cli keygen /backups/recovery-key.cpkey</code></p>
      </form>
    </div>

    <form v-if="settings" class="stack" @submit.prevent="saveSettings">
      <strong>{{ t('backup.automatic') }}</strong>
      <label class="check-row"><input v-model="settings.schedule_enabled" type="checkbox" :disabled="!settings.recipient_count" /> {{ t('backup.scheduleEnabled') }}</label>
      <div class="form-row">
        <label>{{ t('backup.frequency') }}<select v-model="settings.frequency"><option value="daily">{{ t('backup.daily') }}</option><option value="weekly">{{ t('backup.weekly') }}</option></select></label>
        <label v-if="settings.frequency === 'weekly'">{{ t('backup.weekday') }}<select v-model.number="settings.weekday"><option v-for="(day, index) in weekdays" :key="index" :value="index">{{ day }}</option></select></label>
        <label>{{ t('backup.time', { timezone: settings.timezone }) }}<input v-model="settings.time_of_day" type="time" required /></label>
      </div>
      <button class="secondary" :disabled="busy">{{ t('backup.saveSchedule') }}</button>
    </form>

    <div class="stack">
      <strong>{{ t('backup.targets') }}</strong>
      <p v-if="!targets.length" class="muted">{{ t('backup.noTargets') }}</p>
      <div v-for="target in targets" :key="target.id" class="management-row">
        <div><strong>{{ target.name }}</strong><small>{{ t('backup.targetSummary', { kind: kindLabels[target.kind] ?? target.kind, state: target.enabled ? t('backup.active') : t('backup.paused'), count: target.retention_count || t('backup.all') }) }}</small></div>
        <div>
          <button class="text-button" :disabled="busy || !recipients.length" @click="runNow(target)">{{ t('backup.run') }}</button>
          <button class="text-button" :disabled="busy" @click="testTarget(target)">{{ t('backup.test') }}</button>
          <button class="text-button" :disabled="busy" @click="editTarget(target)">{{ t('backup.edit') }}</button>
          <button class="text-button danger-text" :disabled="busy" @click="removeTarget(target)">{{ t('backup.remove') }}</button>
        </div>
      </div>
      <button v-if="!showForm" class="secondary" @click="newTarget">{{ t('backup.addTarget') }}</button>
      <form v-else class="stack backup-target-form" @submit.prevent="saveTarget">
        <label>{{ t('backup.name') }}<input v-model="form.name" maxlength="80" required /></label>
        <label>{{ t('backup.type') }}<select v-model="form.kind" :disabled="form.id !== null"><option v-for="(label, key) in kindLabels" :key="key" :value="key">{{ label }}</option></select></label>
        <label v-for="field in currentFields" :key="field.key">{{ field.label }}
          <textarea v-if="field.key === 'private_key'" v-model="form.config[field.key]" rows="3" autocomplete="off"></textarea>
          <input v-else v-model="form.config[field.key]" :type="field.secret ? 'password' : 'text'" autocomplete="off" />
          <small v-if="field.hint" class="muted">{{ field.hint }}</small>
        </label>
        <div class="form-row">
          <label>{{ t('backup.retention') }}<input v-model.number="form.retention_count" type="number" min="0" max="1000" required /></label>
          <label class="check-row"><input v-model="form.enabled" type="checkbox" /> {{ t('backup.useAutomatic') }}</label>
        </div>
        <div class="form-row"><button class="primary" :disabled="busy">{{ t('backup.save') }}</button><button type="button" class="text-button" @click="showForm = false">{{ t('backup.cancel') }}</button></div>
      </form>
    </div>

    <div class="stack">
      <strong>{{ t('backup.downloadSection') }}</strong>
      <label>{{ t('backup.oneOffKey') }}<input v-model="oneOffKey" placeholder="CPPUB1:…" autocomplete="off" /></label>
      <button class="secondary" :disabled="busy || (!recipients.length && !oneOffKey.trim())" @click="downloadBackup">{{ t('backup.download') }}</button>
      <p class="muted">{{ t('backup.cli') }} <code>docker compose exec api python -m app.backup_cli export /backups/manuell.cpbak --recipient CPPUB1:…</code></p>
    </div>

    <div class="stack backup-restore">
      <strong>{{ t('backup.restoreSection') }}</strong>
      <p class="muted">{{ t('backup.restoreWarning') }} <code>docker compose exec api python -m app.backup_cli import /backups/datei.cpbak --key /backups/recovery-key.cpkey --yes</code></p>
      <label>{{ t('backup.recoveryKey') }}<input type="file" accept=".cpkey" @change="selectRecoveryKey" /></label>
      <label>{{ t('backup.restorePassword') }}<input v-model="restorePassphrase" type="password" autocomplete="off" maxlength="200" /></label>
      <label>{{ t('backup.confirm') }}<input v-model="restoreConfirm" autocomplete="off" /></label>
      <div class="stack">
        <label>{{ t('backup.upload') }}<input type="file" accept=".cpbak" @change="selectRestoreFile" /></label>
        <button class="secondary danger-text" :disabled="busy || !restoreFile || !recoveryKeyText || !restorePassphrase || restoreConfirm !== 'WIEDERHERSTELLEN'" @click="restoreUpload">{{ t('backup.restoreFile') }}</button>
      </div>
      <div v-if="targets.length" class="stack">
        <label>{{ t('backup.orTarget') }}
          <select v-model.number="remoteTargetId" @change="remoteFiles = []"><option :value="null">{{ t('backup.chooseTarget') }}</option><option v-for="target in targets" :key="target.id" :value="target.id">{{ target.name }}</option></select>
        </label>
        <button v-if="remoteTargetId !== null" class="secondary" :disabled="busy" @click="loadRemoteFiles">{{ t('backup.showBackups') }}</button>
        <label v-if="remoteFiles.length">{{ t('backup.backup') }}<select v-model="remoteFile"><option v-for="file in remoteFiles" :key="file.name" :value="file.name">{{ file.name }} ({{ size(file.size) }})</option></select></label>
        <button v-if="remoteFiles.length" class="secondary danger-text" :disabled="busy || !recoveryKeyText || !restorePassphrase || restoreConfirm !== 'WIEDERHERSTELLEN'" @click="restoreRemote">{{ t('backup.restoreTarget') }}</button>
        <p v-else-if="remoteTargetId !== null" class="muted">{{ t('backup.noFiles') }}</p>
      </div>
    </div>

    <div v-if="runs.length" class="stack">
      <strong>{{ t('backup.recent') }}</strong>
      <div v-for="run in runs" :key="run.id" class="management-row">
        <div>
          <strong>{{ run.status === 'success' ? '✓' : '✗' }} {{ run.target_name }} · {{ run.trigger === 'scheduled' ? t('backup.scheduled') : t('backup.manual') }}</strong>
          <small>{{ new Date(run.started_at).toLocaleString(locale) }}<span v-if="run.filename"> · {{ run.filename }} ({{ size(run.size_bytes) }})</span><span v-if="run.error"> · {{ apiErrorDetail(run.error) }}</span></small>
        </div>
      </div>
    </div>
  </section>
</template>
