<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

type Target = { id: number; name: string; kind: string; config: Record<string, string>; enabled: boolean; retention_count: number }
type Settings = { schedule_enabled: boolean; frequency: 'daily' | 'weekly'; weekday: number; time_of_day: string; recipient_count: number; last_slot: string | null; timezone: string }
type Run = { id: number; started_at: string; trigger: string; target_name: string; filename: string | null; size_bytes: number | null; status: string; error: string | null }
type Recipient = { id: number; name: string; public_key: string; created_at: string }
type RemoteFile = { name: string; size: number; modified: string | null }
type Field = { key: string; label: string; secret?: boolean; hint?: string }

const kindLabels: Record<string, string> = { local: 'Lokaler Ordner', sftp: 'SFTP', webdav: 'WebDAV (z. B. Nextcloud)', s3: 'S3-kompatibel' }
const kindFields: Record<string, Field[]> = {
  local: [{ key: 'subdir', label: 'Unterordner (optional)', hint: 'Relativ zum Backup-Verzeichnis des Servers (/backups)' }],
  sftp: [
    { key: 'host', label: 'Server' }, { key: 'port', label: 'Port (Standard 22)' }, { key: 'username', label: 'Benutzer' },
    { key: 'password', label: 'Passwort (oder Passphrase des Schlüssels)', secret: true },
    { key: 'private_key', label: 'Privater Schlüssel (optional, PEM)', secret: true },
    { key: 'directory', label: 'Zielordner (optional)' },
    { key: 'host_key_fingerprint', label: 'Host-Key-Fingerabdruck', hint: 'Format SHA256:… (ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub). Bei „Testen“ zeigt ein Fehler den aktuellen Wert des Servers.' },
  ],
  webdav: [
    { key: 'url', label: 'URL des Zielordners', hint: 'Muss mit https:// beginnen, z. B. https://cloud.example.org/remote.php/dav/files/benutzer/ClinicPulse' },
    { key: 'username', label: 'Benutzer' }, { key: 'password', label: 'Passwort / App-Passwort', secret: true },
  ],
  s3: [
    { key: 'endpoint_url', label: 'Endpunkt (https://…, leer für AWS)' }, { key: 'region', label: 'Region (optional)' }, { key: 'bucket', label: 'Bucket' },
    { key: 'prefix', label: 'Präfix (optional)' }, { key: 'access_key', label: 'Access Key' }, { key: 'secret_key', label: 'Secret Key', secret: true },
  ],
}
const weekdays = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

const settings = ref<Settings | null>(null)
const recipients = ref<Recipient[]>([])
const recipientName = ref('')
const recipientKey = ref('')
const keyName = ref('Diese Instanz')
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

const currentFields = computed(() => kindFields[form.kind] ?? [])

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : String(item))).join(', ')
  return 'Anfrage fehlgeschlagen'
}

async function call<T>(path: string, options: RequestInit = {}, json = true): Promise<T> {
  const response = await fetch(`/api/admin/backup${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: { ...(json ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data && 'detail' in data ? detailText(data.detail) : `Anfrage fehlgeschlagen (${response.status})`)
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
    message.value = success
  } catch (err) {
    problem.value = err instanceof Error ? err.message : 'Aktion fehlgeschlagen'
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
  }, 'Einstellungen gespeichert.')
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
  }, 'Backup-Ziel gespeichert.')
}

async function removeTarget(target: Target) {
  if (!window.confirm(`Backup-Ziel „${target.name}“ entfernen? Bereits gespeicherte Backups bleiben am Ziel erhalten.`)) return
  await guarded(async () => {
    await call(`/targets/${target.id}`, { method: 'DELETE' })
    await loadAll()
  }, 'Backup-Ziel entfernt.')
}

async function testTarget(target: Target) {
  await guarded(async () => { await call(`/targets/${target.id}/test`, { method: 'POST' }) }, `Verbindung zu „${target.name}“ erfolgreich.`)
}

async function runNow(target: Target) {
  await guarded(async () => {
    const run = await call<Run>(`/targets/${target.id}/run`, { method: 'POST' })
    await loadAll()
    if (run.status !== 'success') throw new Error(run.error ?? 'Backup fehlgeschlagen')
  }, `Backup auf „${target.name}“ erstellt.`)
}

async function downloadBackup() {
  await guarded(async () => {
    const response = await fetch('/api/admin/backup/download', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ public_key: oneOffKey.value.trim() || null }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data && 'detail' in data ? detailText(data.detail) : `Anfrage fehlgeschlagen (${response.status})`)
    }
    const name = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? 'clinicpulse.cpbak'
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    URL.revokeObjectURL(url)
  }, 'Backup heruntergeladen.')
}

async function addRecipient() {
  await guarded(async () => {
    await call('/recipients', { method: 'POST', body: JSON.stringify({ name: recipientName.value, public_key: recipientKey.value }) })
    recipientName.value = ''
    recipientKey.value = ''
    await loadAll()
  }, 'Empfänger hinzugefügt. Neue Backups sind auch für ihn lesbar.')
}

async function removeRecipient(item: Recipient) {
  if (!window.confirm(`Empfänger „${item.name}“ entfernen? Künftige Backups sind für diesen Schlüssel nicht mehr lesbar; bestehende bleiben es.`)) return
  await guarded(async () => {
    await call(`/recipients/${item.id}`, { method: 'DELETE' })
    await loadAll()
  }, 'Empfänger entfernt.')
}

async function createRecoveryKey() {
  await guarded(async () => {
    const response = await fetch('/api/admin/backup/recovery-key', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: keyName.value, passphrase: keyPassphrase.value, add_as_recipient: true }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data && 'detail' in data ? detailText(data.detail) : `Anfrage fehlgeschlagen (${response.status})`)
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
  }, 'Schlüsseldatei heruntergeladen. Bewahre sie und ihr Passwort getrennt vom Server auf – sie wird nicht gespeichert.')
}

async function selectRecoveryKey(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  recoveryKeyFile.value = file
  recoveryKeyText.value = file ? await file.text() : ''
}

function afterRestore() {
  message.value = 'Wiederherstellung abgeschlossen. Die Seite wird neu geladen …'
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
    <h3>Datensicherung</h3>
    <p class="muted">Backups sind immer verschlüsselt und können nur mit dem passenden <strong>privaten Wiederherstellungsschlüssel</strong> gelesen werden – der Server speichert keinen Schlüssel zum Entschlüsseln. Sie sind unabhängig von der Architektur (PC, Server, Raspberry Pi) und lassen sich auf einer neuen Instanz einspielen. Übertragung zu Zielen erfolgt nur verschlüsselt (SFTP/SSH oder HTTPS).</p>
    <p v-if="message" class="planning-notice" role="status">{{ message }}</p>
    <p v-if="problem" class="error-message" role="alert">{{ problem }}</p>

    <div class="stack">
      <strong>1. Wiederherstellungsschlüssel und Empfänger</strong>
      <p v-if="!recipients.length" class="muted">Noch kein Empfänger vorhanden – ohne Empfänger werden keine Backups erstellt.</p>
      <div v-for="item in recipients" :key="item.id" class="management-row">
        <div><strong>{{ item.name }}</strong><small><code>{{ item.public_key }}</code></small></div>
        <button class="text-button danger-text" :disabled="busy" @click="removeRecipient(item)">Entfernen</button>
      </div>
      <form class="stack backup-target-form" @submit.prevent="createRecoveryKey">
        <strong>Neuen Schlüssel für diese Instanz erzeugen</strong>
        <label>Name<input v-model="keyName" maxlength="80" required /></label>
        <label>Passwort für die Schlüsseldatei (mindestens 12 Zeichen)<input v-model="keyPassphrase" type="password" autocomplete="new-password" maxlength="200" required /></label>
        <button class="secondary" :disabled="busy">Schlüssel erzeugen und Datei herunterladen</button>
        <p class="muted">Die Datei (.cpkey) ist die einzige Möglichkeit, Backups zu entschlüsseln. Geht sie verloren, sind die Backups unbrauchbar.</p>
        <p v-if="lastPublicKey" class="muted">Öffentlicher Schlüssel: <code>{{ lastPublicKey }}</code></p>
      </form>
      <form class="stack backup-target-form" @submit.prevent="addRecipient">
        <strong>Schlüssel einer anderen (neuen) Instanz als Empfänger hinzufügen</strong>
        <label>Name<input v-model="recipientName" maxlength="80" required /></label>
        <label>Öffentlicher Schlüssel (CPPUB1:…)<input v-model="recipientKey" required autocomplete="off" /></label>
        <button class="secondary" :disabled="busy">Empfänger hinzufügen</button>
        <p class="muted">Auf der neuen Instanz: <code>docker compose exec api python -m app.backup_cli keygen /backups/recovery-key.cpkey</code> gibt den öffentlichen Schlüssel aus.</p>
      </form>
    </div>

    <form v-if="settings" class="stack" @submit.prevent="saveSettings">
      <strong>2. Automatische Backups</strong>
      <label class="check-row"><input v-model="settings.schedule_enabled" type="checkbox" :disabled="!settings.recipient_count" /> Regelmäßig sichern</label>
      <div class="form-row">
        <label>Rhythmus<select v-model="settings.frequency"><option value="daily">Täglich</option><option value="weekly">Wöchentlich</option></select></label>
        <label v-if="settings.frequency === 'weekly'">Wochentag<select v-model.number="settings.weekday"><option v-for="(day, index) in weekdays" :key="day" :value="index">{{ day }}</option></select></label>
        <label>Uhrzeit ({{ settings.timezone }})<input v-model="settings.time_of_day" type="time" required /></label>
      </div>
      <button class="secondary" :disabled="busy">Zeitplan speichern</button>
    </form>

    <div class="stack">
      <strong>3. Backup-Ziele</strong>
      <p v-if="!targets.length" class="muted">Noch kein Ziel angelegt. Ohne Ziel können Backups nur heruntergeladen werden.</p>
      <div v-for="target in targets" :key="target.id" class="management-row">
        <div><strong>{{ target.name }}</strong><small>{{ kindLabels[target.kind] }} · {{ target.enabled ? 'aktiv' : 'pausiert' }} · behält {{ target.retention_count || 'alle' }} Backups</small></div>
        <div>
          <button class="text-button" :disabled="busy || !recipients.length" @click="runNow(target)">Jetzt sichern</button>
          <button class="text-button" :disabled="busy" @click="testTarget(target)">Testen</button>
          <button class="text-button" :disabled="busy" @click="editTarget(target)">Bearbeiten</button>
          <button class="text-button danger-text" :disabled="busy" @click="removeTarget(target)">Entfernen</button>
        </div>
      </div>
      <button v-if="!showForm" class="secondary" @click="newTarget">Backup-Ziel hinzufügen</button>
      <form v-else class="stack backup-target-form" @submit.prevent="saveTarget">
        <label>Name<input v-model="form.name" maxlength="80" required /></label>
        <label>Typ<select v-model="form.kind" :disabled="form.id !== null"><option v-for="(label, key) in kindLabels" :key="key" :value="key">{{ label }}</option></select></label>
        <label v-for="field in currentFields" :key="field.key">{{ field.label }}
          <textarea v-if="field.key === 'private_key'" v-model="form.config[field.key]" rows="3" autocomplete="off"></textarea>
          <input v-else v-model="form.config[field.key]" :type="field.secret ? 'password' : 'text'" autocomplete="off" />
          <small v-if="field.hint" class="muted">{{ field.hint }}</small>
        </label>
        <div class="form-row">
          <label>Backups behalten (0 = alle)<input v-model.number="form.retention_count" type="number" min="0" max="1000" required /></label>
          <label class="check-row"><input v-model="form.enabled" type="checkbox" /> Für automatische Backups verwenden</label>
        </div>
        <div class="form-row"><button class="primary" :disabled="busy">Speichern</button><button type="button" class="text-button" @click="showForm = false">Abbrechen</button></div>
      </form>
    </div>

    <div class="stack">
      <strong>4. Backup herunterladen</strong>
      <label>Nur für diesen öffentlichen Schlüssel verschlüsseln (optional, z. B. neue Instanz; leer = alle Empfänger)<input v-model="oneOffKey" placeholder="CPPUB1:…" autocomplete="off" /></label>
      <button class="secondary" :disabled="busy || (!recipients.length && !oneOffKey.trim())" @click="downloadBackup">Backup herunterladen</button>
      <p class="muted">Per Kommandozeile: <code>docker compose exec api python -m app.backup_cli export /backups/manuell.cpbak --recipient CPPUB1:…</code></p>
    </div>

    <div class="stack backup-restore">
      <strong>5. Wiederherstellen</strong>
      <p class="muted">Ersetzt <strong>alle</strong> vorhandenen Daten durch den Stand des Backups. Erstelle vorher ein aktuelles Backup. Auf einer ganz neuen Instanz geht das auch per CLI: <code>docker compose exec api python -m app.backup_cli import /backups/datei.cpbak --key /backups/recovery-key.cpkey --yes</code></p>
      <label>Wiederherstellungsschlüssel (.cpkey)<input type="file" accept=".cpkey" @change="selectRecoveryKey" /></label>
      <label>Passwort der Schlüsseldatei<input v-model="restorePassphrase" type="password" autocomplete="off" maxlength="200" /></label>
      <label>Zur Bestätigung „WIEDERHERSTELLEN“ eingeben<input v-model="restoreConfirm" autocomplete="off" /></label>
      <div class="stack">
        <label>Backup-Datei hochladen (.cpbak)<input type="file" accept=".cpbak" @change="selectRestoreFile" /></label>
        <button class="secondary danger-text" :disabled="busy || !restoreFile || !recoveryKeyText || !restorePassphrase || restoreConfirm !== 'WIEDERHERSTELLEN'" @click="restoreUpload">Aus Datei wiederherstellen</button>
      </div>
      <div v-if="targets.length" class="stack">
        <label>Oder von einem Ziel
          <select v-model.number="remoteTargetId" @change="remoteFiles = []"><option :value="null">Ziel wählen …</option><option v-for="target in targets" :key="target.id" :value="target.id">{{ target.name }}</option></select>
        </label>
        <button v-if="remoteTargetId !== null" class="secondary" :disabled="busy" @click="loadRemoteFiles">Backups anzeigen</button>
        <label v-if="remoteFiles.length">Backup<select v-model="remoteFile"><option v-for="file in remoteFiles" :key="file.name" :value="file.name">{{ file.name }} ({{ size(file.size) }})</option></select></label>
        <button v-if="remoteFiles.length" class="secondary danger-text" :disabled="busy || !recoveryKeyText || !restorePassphrase || restoreConfirm !== 'WIEDERHERSTELLEN'" @click="restoreRemote">Von Ziel wiederherstellen</button>
        <p v-else-if="remoteTargetId !== null" class="muted">Keine Backups geladen oder vorhanden.</p>
      </div>
    </div>

    <div v-if="runs.length" class="stack">
      <strong>Letzte Backups</strong>
      <div v-for="run in runs" :key="run.id" class="management-row">
        <div>
          <strong>{{ run.status === 'success' ? '✓' : '✗' }} {{ run.target_name }} · {{ run.trigger === 'scheduled' ? 'automatisch' : 'manuell' }}</strong>
          <small>{{ new Date(run.started_at).toLocaleString('de-DE') }}<span v-if="run.filename"> · {{ run.filename }} ({{ size(run.size_bytes) }})</span><span v-if="run.error"> · {{ run.error }}</span></small>
        </div>
      </div>
    </div>
  </section>
</template>
