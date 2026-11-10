import { locale, t, type TranslationKey } from './index'

const knownErrors: Record<string, TranslationKey> = {
  'Invalid username or password': 'api.invalidCredentials',
  'Authentication required': 'api.authRequired',
  'Invalid or expired session': 'api.sessionExpired',
  'Session expired due to inactivity': 'api.inactiveSession',
  'Administrator access required': 'api.adminRequired',
  'Department and account management access required': 'api.accountManagementRequired',
  'Team management access required': 'api.teamManagementRequired',
  'Schedule view permission required': 'api.scheduleViewRequired',
  'Schedule editing permission required': 'api.scheduleEditRequired',
  'Schedule approval permission required': 'api.scheduleApprovalRequired',
  'Employee already has an overlapping shift': 'api.shiftOverlap',
  'Employee is absent during this shift': 'api.shiftAbsent',
  'Shift type not found': 'api.shiftTypeNotFound',
  'Assignment not found': 'api.assignmentNotFound',
  'Account not found': 'api.accountNotFound',
  'User not found': 'api.userNotFound',
  'Username is already in use': 'api.usernameInUse',
  'Department not found': 'api.departmentNotFound',
  'Department already exists': 'api.departmentExists',
  'Department name already exists': 'api.departmentExists',
  'Department is still in use': 'api.departmentInUse',
  "Employee must belong to the account's department": 'api.employeeDepartment',
  'Employee already has an account': 'api.employeeHasAccount',
  'Invitation is invalid or expired': 'api.invitationInvalid',
  'Department cannot be changed while the employee has scheduled shifts': 'api.employeeDepartmentChange',
  'Employee has scheduled shifts': 'api.employeeHasShifts',
  'Employee has a linked login account': 'api.employeeLinkedAccount',
  'Username and email are required': 'api.usernameEmailRequired',
  'Employee or shift type not found': 'api.employeeOrShiftNotFound',
  'Employee and shift must belong to the same department': 'api.shiftDepartment',
  'Employee not found': 'api.employeeNotFound',
  'Absence not found': 'api.absenceNotFound',
  'Absence management permission required': 'api.absencePermission',
  'Setup required': 'api.setupRequired',
  'Archive not found': 'api.archiveNotFound',
  'Date range must be 1–366 days': 'api.archiveDateRange',
  'Date range must be 1–63 days': 'api.planningDateRange',
  'Department is required': 'api.departmentRequired',
  'Current password is incorrect': 'api.currentPasswordIncorrect',
  'Business configuration is missing': 'api.businessConfigurationMissing',
  'Initial setup is already complete': 'api.setupComplete',
  'Licensed user limit reached': 'api.licenseUserLimit',
  'Role is not available for this facility type': 'api.roleUnavailable',
  'Personnel users can create employee accounts only': 'api.personnelCreateOnly',
  'Personnel users can manage employee accounts only': 'api.personnelManageOnly',
  'Only the administrator can add hospital managers': 'api.adminAddManagement',
  'Only the administrator can manage hospital managers': 'api.adminManageManagement',
  'Only management can add personnel users': 'api.managementAddPersonnel',
  'Only management can assign the personnel role': 'api.managementAssignPersonnel',
  'A department is required for this role': 'api.roleDepartmentRequired',
  'Chief physicians are read-only': 'api.chiefPhysicianReadOnly',
  'A password or invitation email is required': 'api.passwordOrInvitationRequired',
  'An invited account must accept its invitation before it can be unlocked': 'api.invitationBeforeUnlock',
  'No invitation email address is stored': 'api.invitationEmailMissing',
  'No active invitation exists': 'api.invitationMissing',
  'You can only plan your own department': 'api.planOwnDepartment',
  'You can only approve for your own department': 'api.approveOwnDepartment',
  'No department access is configured': 'api.departmentAccessMissing',
  'The scheduled break must fit within the shift and start within the first six hours (ArbZG §4)': 'api.invalidBreak',
  'Shift type name already exists': 'api.shiftNameExists',
  'Shift type is in use': 'api.shiftTypeInUse',
  'A valid timezone-aware interval is required': 'api.timezoneInterval',
  'SMTP authentication requires TLS': 'api.smtpTlsRequired',
  'Testmail konnte nicht versendet werden. SMTP-Host, Zugangsdaten und TLS-Einstellungen prüfen.': 'api.smtpTestFailed',
  'Bundesland fehlt': 'api.stateMissing',
  'Einrichtungsart fehlt': 'api.facilityMissing',
  'Lizenzprüfung ist nicht verfügbar': 'api.licenseUnavailable',
  'Lizenzprüfung ist nicht konfiguriert': 'api.licenseNotConfigured',
  'Lizenzserver ist momentan nicht erreichbar': 'api.licenseServerUnreachable',
  'Lizenz-Token oder Status ungültig': 'api.invalidLicense',
  'Lizenz-Token oder signierter Lizenzstatus ist ungültig': 'api.invalidSignedLicense',
  'Lizenz enthält kein ClinicPulse-Kernfeature': 'api.licenseCoreMissing',
  'Diese Lizenz ist gesperrt': 'api.licenseLocked',
  'License installation is not initialized': 'api.licenseNotInitialized',
  'Die Lizenz enthält kein Bundesland. Bitte im License Manager beim Kunden hinterlegen und Token neu ausstellen.': 'api.licenseStateMissing',
  'Die Lizenz enthält keine Einrichtungsart. Bitte im License Manager beim Kunden hinterlegen und Token neu ausstellen.': 'api.licenseFacilityMissing',
  'Angemeldet bleiben ist für Administrationskonten nicht verfügbar': 'api.adminRememberUnavailable',
  'Dieses Konto ist keiner Abteilung zugeordnet': 'api.accountDepartmentMissing',
  'Passwortprüfung momentan nicht verfügbar': 'api.passwordCheckUnavailable',
  'Ungültige Antwort des Passwort-Prüfdienstes': 'api.passwordCheckInvalid',
  'Have I Been Pwned konnte nicht erreicht werden': 'api.passwordCheckUnreachable',
  'Antwort des Passwort-Prüfdienstes ist zu groß': 'api.passwordCheckTooLarge',
  'Dienstpläne sind für den Administrator nicht einsehbar': 'api.adminScheduleUnavailable',
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
  'ClinicPulse ist auf dem aktuellen Release-Stand.': 'updates.current',
  'Der optionale GitHub-Zugriffsschlüssel ist nicht lesbar.': 'updates.tokenUnreadable',
  'Kein öffentlich erreichbares GitHub-Release gefunden.': 'updates.noPublicRelease',
  'GitHub hat die Update-Abfrage begrenzt oder verweigert.': 'updates.rateLimited',
  'GitHub ist für die Update-Prüfung nicht erreichbar.': 'updates.unreachable',
  'GitHub hat eine ungültige Antwort geliefert.': 'updates.invalidResponse',
  'GitHub hat eine ungültige Release-Antwort geliefert.': 'updates.invalidReleaseResponse',
  'Release-Versionen müssen dem Format vX.Y.Z entsprechen.': 'updates.invalidVersion',
}

export function apiErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    const key = Object.hasOwn(knownErrors, detail) ? knownErrors[detail] : undefined
    if (key) return t(key)
    const updateHttpError = /^GitHub-Update-Abfrage fehlgeschlagen \(HTTP (\d+)\)\.$/.exec(detail)
    if (updateHttpError?.[1]) return t('updates.httpError', { status: updateHttpError[1] })
    const noChannelRelease = /^Kein veröffentlichtes Release für den (stable|nightly)-Kanal gefunden\.$/.exec(detail)
    if (noChannelRelease?.[1]) return t('updates.noChannelRelease', { channel: noChannelRelease[1] })
    return locale.value === 'de' ? detail : t('api.serverDetail', { detail })
  }
  if (!Array.isArray(detail)) return null
  const messages = detail.flatMap((item: unknown) => {
    if (typeof item !== 'object' || item === null || !('msg' in item)) return []
    return typeof item.msg === 'string' ? [item.msg] : []
  })
  return messages.length ? [...new Set(messages)].map((message) => apiErrorDetail(message)).join('; ') : null
}

export class ApiError extends Error {
  constructor(readonly detail: unknown, readonly status: number) {
    super(`HTTP ${status}`)
  }

  display(): string {
    return apiErrorDetail(this.detail) ?? t('api.requestFailed', { status: this.status })
  }
}

export class TranslatedError extends Error {
  constructor(readonly key: TranslationKey, readonly values?: Record<string, string | number>) {
    super(key)
  }

  display(): string {
    return t(this.key, this.values)
  }
}

export function errorMessage(error: string | Error): string {
  return error instanceof ApiError || error instanceof TranslatedError ? error.display() : typeof error === 'string' ? error : error.message
}
