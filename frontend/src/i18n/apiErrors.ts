import { locale, t, type TranslationKey } from './index'

const knownErrors: Record<string, TranslationKey> = {
  'Invalid username or password': 'api.invalidCredentials',
  'Authentication required': 'api.authRequired',
  'Invalid or expired session': 'api.sessionExpired',
  'Session expired due to inactivity': 'api.inactiveSession',
  'Employee not found': 'api.employeeNotFound',
  'Absence not found': 'api.absenceNotFound',
  'Absence management permission required': 'api.absencePermission',
  'Absences are not available for kiosk accounts': 'api.absenceKiosk',
  'You can only request your own absences': 'api.ownAbsenceOnly',
  'An absence already exists in this period': 'api.absenceOverlap',
  'Employee has scheduled shifts in this period': 'api.absenceShifts',
  'Sick leave does not require approval': 'api.absenceSickApproval',
  'Absence was already decided': 'api.absenceDecided',
  'Only pending requests can be withdrawn': 'api.absenceWithdraw',
  'Backup-Ziel nicht gefunden': 'api.backupTargetNotFound',
  'Empfänger nicht gefunden': 'api.backupRecipientNotFound',
  'Ein Backup-Ziel mit diesem Namen existiert bereits': 'api.backupDuplicateTarget',
  'Name oder Schlüssel ist bereits als Empfänger hinterlegt': 'api.backupDuplicateRecipient',
  'Ungültiger Dateiname': 'api.backupInvalidFilename',
  'Backup-Datei ist zu groß': 'api.backupTooLarge',
  'Wiederherstellungsschlüssel fehlt oder ist ungültig': 'api.backupInvalidKey',
  'Bitte „WIEDERHERSTELLEN“ zur Bestätigung eingeben': 'api.backupConfirm',
  'Für automatische Backups wird mindestens ein Empfänger-Schlüssel benötigt (zuerst Wiederherstellungsschlüssel erzeugen)': 'api.backupRecipientRequired',
}

export function apiErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    const key = Object.hasOwn(knownErrors, detail) ? knownErrors[detail] : undefined
    if (key) return t(key)
    return locale.value === 'de' ? detail : t('api.serverDetail', { detail })
  }
  if (!Array.isArray(detail)) return null
  const messages = detail.flatMap((item: unknown) => {
    if (typeof item !== 'object' || item === null || !('msg' in item)) return []
    return typeof item.msg === 'string' ? [item.msg] : []
  })
  return messages.length ? [...new Set(messages)].map((message) => apiErrorDetail(message)).join('; ') : null
}
