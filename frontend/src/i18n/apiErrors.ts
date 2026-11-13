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
  'Vehicle is deactivated': 'api.vehicleDeactivated',
  'Vehicle is in use': 'api.vehicleInUse',
  'Vehicle name already exists': 'api.vehicleExists',
  'Vehicles are not used by this facility type': 'api.vehiclesNotUsed',
  "Vehicle must belong to the shift's department": 'api.vehicleDepartment',
  'Vehicle not found': 'api.vehicleNotFound',
  'Vehicle management permission required': 'api.vehiclePermission',
  'This facility type uses a single organizational unit': 'api.singleUnit',
  'A single organizational unit requires that only one exists': 'api.singleUnitLimit',
  'Unit name, plural, grammatical gender and leadership title are required for this facility type': 'api.unitConfigRequired',
  'The name of the main control center or unit is required': 'api.unitNameRequired',
  "Only the home department can change the employee's name or home department": 'api.employeeCoreEdit',
  'You can only manage qualifications of your own department': 'api.qualificationScope',
  'At least one qualification is required': 'api.qualificationRequired',
  "Qualifications must belong to the employee's departments": 'api.qualificationDepartment',
  'Employee not found': 'api.employeeNotFound',
  'Absence not found': 'api.absenceNotFound',
  'Absence management permission required': 'api.absencePermission',
  'No linked employee for personal absences': 'api.noLinkedEmployee',
  'Use personal absence requests for your own absences': 'api.useOwnAbsences',
  'You cannot decide your own absence request': 'api.noSelfApproval',
  'Setup required': 'api.setupRequired',
  'Archive not found': 'api.archiveNotFound',
  'Date range must be 1–366 days': 'api.archiveDateRange',
  'Date range must be 1–63 days': 'api.planningDateRange',
  'Department is required': 'api.departmentRequired',
  'Current password is incorrect': 'api.currentPasswordIncorrect',
  'A different new password is required': 'api.differentPasswordRequired',
  'Username cannot be changed during the required password change': 'api.usernameChangeBlocked',
  'Password change required': 'api.passwordChangeRequired',
  'Email delivery is disabled': 'api.emailDisabled',
  'An initial password is required when email delivery is disabled': 'api.initialPasswordRequired',
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
  'Lizenz enthält kein Medora-Kernfeature': 'api.licenseCoreMissing',
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
  'Unbekannter Zieltyp': 'api.backupUnknownTarget',
  'Unterordner darf nicht außerhalb des Backup-Verzeichnisses liegen': 'api.backupInvalidSubdir',
  'Ungültiger Port': 'api.backupInvalidPort',
  'Passwort oder privater Schlüssel erforderlich': 'api.backupCredentialsRequired',
  'Host-Key-Fingerabdruck muss im Format SHA256:… angegeben werden': 'api.backupFingerprintFormat',
  'Die WebDAV-URL muss mit https:// beginnen (verschlüsselte Übertragung ist Pflicht)': 'api.backupWebdavHttps',
  'Der S3-Endpunkt muss mit https:// beginnen (verschlüsselte Übertragung ist Pflicht)': 'api.backupS3Https',
  'Backup-Datei nicht gefunden': 'api.backupFileNotFound',
  'Privater Schlüssel konnte nicht gelesen werden': 'api.backupPrivateKeyUnreadable',
  'WebDAV-Antwort konnte nicht gelesen werden': 'api.backupWebdavUnreadable',
  'Ungültiger öffentlicher Schlüssel (erwartet wird ein Wert, der mit CPPUB1: beginnt)': 'api.backupPublicKeyFormat',
  'Ungültiger öffentlicher Schlüssel': 'api.backupPublicKeyInvalid',
  'Das ist keine gültige Wiederherstellungsschlüssel-Datei': 'api.backupRecoveryFileInvalid',
  'Passwort der Schlüsseldatei ist falsch': 'api.backupRecoveryPasswordInvalid',
  'Die Schlüsseldatei ist beschädigt': 'api.backupRecoveryFileDamaged',
  'Binärwerte werden im Backup nicht unterstützt': 'api.backupBinaryUnsupported',
  'Es ist kein Empfänger-Schlüssel hinterlegt – ein Backup wird nie unverschlüsselt erstellt': 'api.backupNoRecipient',
  'Die Datei ist kein Medora-Backup': 'api.backupNotMedora',
  'Die Backup-Datei ist beschädigt': 'api.backupDamaged',
  'Dieses Backup wurde nicht für diese Instanz bzw. diesen Schlüssel verschlüsselt': 'api.backupWrongKey',
  'Backup beschädigt oder manipuliert': 'api.backupTampered',
  'Nicht unterstütztes Backup-Format': 'api.backupFormatUnsupported',
  'Die Wiederherstellung ist fehlgeschlagen; es wurden keine Daten verändert': 'api.backupRestoreFailed',
  'Name must not be empty': 'api.validationName',
  'Birth date is not plausible': 'api.validationBirthDate',
  'Username and email are required when creating an account': 'api.validationAccountDetails',
  'A valid email address is required': 'api.validationEmail',
  'Datetime values must include a timezone offset': 'api.validationTimezone',
  'Shift end must be after shift start': 'api.validationShiftEnd',
  'end_date must not be before start_date': 'api.validationDateOrder',
  'Planning period is limited to 31 days': 'api.validationPlanningPeriod',
  'License token must not be empty': 'api.validationLicenseToken',
  'An email address is required when no password is supplied': 'api.validationEmailOrPassword',
  'Planning permissions require schedule view access': 'api.validationPlanningPermissions',
  'Kiosk accounts must be read-only and have schedule view access': 'api.validationKioskPermissions',
  'At least one department is required for this role': 'api.validationRoleDepartment',
  'Employee accounts must be linked to an employee': 'api.validationEmployeeLink',
  'Employee accounts are read-only and have schedule view access': 'api.validationEmployeePermissions',
  'Only employee accounts can be linked to an employee': 'api.validationEmployeeRole',
  'Choose either a new SMTP password or clearing the saved password': 'api.validationSmtpPassword',
  'Implicit TLS and STARTTLS cannot be enabled together': 'api.validationSmtpTls',
  'The public instance URL must use HTTPS': 'api.validationPublicHttps',
  'Profile image must be a PNG, JPEG, or WebP data URL': 'api.validationImageFormat',
  'Profile image data is invalid': 'api.validationImageData',
  'Profile image must be between 1 byte and 256 KB': 'api.validationImageSize',
  'Profile image does not match its declared format': 'api.validationImageMismatch',
  'Absence must span 1-366 days': 'api.validationAbsencePeriod',
  'Business configuration is required before scheduling': 'api.ruleBusinessConfiguration',
  'Work on Sundays or public holidays is disabled for this facility (ArbZG §§9–10)': 'api.ruleSundayWork',
  'At least 15 Sundays per calendar year must remain free of work (ArbZG §11)': 'api.ruleFreeSundays',
  'Shift does not include the legally required break (ArbZG §4)': 'api.ruleRequiredBreak',
  'Scheduled break does not fit within the shift or starts after six hours (ArbZG §4)': 'api.ruleBreakTiming',
  'A work period longer than six hours without a break would violate ArbZG §4': 'api.ruleSixHours',
  'License has not been activated or checked': 'api.licenseNotActivated',
  'Stored license status could not be verified': 'api.licenseStatusUnverified',
  'License is blocked': 'api.licenseBlocked',
  'License is overdue': 'api.licenseOverdue',
  'License grace period has expired': 'api.licenseGraceExpired',
  'License Manager has been unreachable for more than seven days': 'api.licenseManagerUnreachable',
  'Kulanzzeitraum aktiv': 'api.licenseGraceActive',
  'Limit optimization to a maximum of 150 open positions per day': 'api.optimizationPositions',
  'Select a smaller department for day optimization': 'api.optimizationDepartment',
  'Optimization has too many eligible employee-position combinations': 'api.optimizationCombinations',
  'Medora ist auf dem aktuellen Release-Stand.': 'updates.current',
  'Der optionale GitHub-Zugriffsschlüssel ist nicht lesbar.': 'updates.tokenUnreadable',
  'Kein öffentlich erreichbares GitHub-Release gefunden.': 'updates.noPublicRelease',
  'GitHub hat die Update-Abfrage begrenzt oder verweigert.': 'updates.rateLimited',
  'GitHub ist für die Update-Prüfung nicht erreichbar.': 'updates.unreachable',
  'GitHub hat eine ungültige Antwort geliefert.': 'updates.invalidResponse',
  'GitHub hat eine ungültige Release-Antwort geliefert.': 'updates.invalidReleaseResponse',
  'Release-Versionen müssen dem Format vX.Y.Z entsprechen.': 'updates.invalidVersion',
  'Die installierte Image-Version ist unbekannt oder ungültig.': 'updates.invalidImageVersion',
  'Die GitHub-Container-Registry hat die Update-Abfrage begrenzt oder verweigert.': 'updates.registryRateLimited',
  'Die GitHub-Container-Registry ist für die Update-Prüfung nicht erreichbar.': 'updates.registryUnreachable',
  'Die GitHub-Container-Registry hat eine ungültige Antwort geliefert.': 'updates.registryInvalid',
}

export function apiErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    const normalized = detail.startsWith('Value error, ') ? detail.slice('Value error, '.length) : detail
    const key = Object.hasOwn(knownErrors, normalized) ? knownErrors[normalized] : undefined
    if (key) return t(key)
    const requiredField = /^Das Feld „([^“]+)“ ist erforderlich$/.exec(detail)
    if (requiredField?.[1]) return t('api.backupFieldRequired', { field: requiredField[1] })
    const passphraseLength = /^Das Passwort muss mindestens (\d+) Zeichen lang sein$/.exec(detail)
    if (passphraseLength?.[1]) return t('api.backupPassphraseLength', { count: passphraseLength[1] })
    const unknownTable = /^Das Backup enthält die unbekannte Tabelle „([^“]+)“ – wahrscheinlich stammt es aus einer neueren Medora-Version$/.exec(detail)
    if (unknownTable?.[1]) return t('api.backupUnknownTable', { name: unknownTable[1] })
    const unknownColumns = /^Das Backup enthält unbekannte Spalten in „([^“]+)“ – bitte zuerst Medora aktualisieren$/.exec(detail)
    if (unknownColumns?.[1]) return t('api.backupUnknownColumns', { name: unknownColumns[1] })
    const fullyStaffed = /^(.+) on (\d{4}-\d{2}-\d{2}) is already fully staffed$/.exec(detail)
    if (fullyStaffed?.[1] && fullyStaffed[2]) return t('api.shiftFullyStaffed', { name: fullyStaffed[1], date: fullyStaffed[2] })
    const requiredBreak = /^At least (\d+) minutes of break are required for this shift length \(ArbZG §4\)$/.exec(detail)
    if (requiredBreak?.[1]) return t('api.ruleBreakMinutes', { count: requiredBreak[1] })
    const restPeriod = /^Minimum rest period of ([\d.]+) hours between shifts would be violated$/.exec(detail)
    if (restPeriod?.[1]) return t('api.ruleRestHours', { count: restPeriod[1] })
    const dailyHours = /^Daily working time would exceed ([\d.]+) hours \(ArbZG §3\)$/.exec(detail)
    if (dailyHours?.[1]) return t('api.ruleDailyHours', { count: dailyHours[1] })
    const weeklyHours = /^Average working time would exceed ([\d.]+) hours per week over the 24-week reference period \(ArbZG §3\)$/.exec(detail)
    if (weeklyHours?.[1]) return t('api.ruleWeeklyHours', { count: weeklyHours[1] })
    const replacementRest = /^A distinct replacement rest day is required within a (\d+)-day period including (\d{4}-\d{2}-\d{2}) \(ArbZG §11\)$/.exec(detail)
    if (replacementRest?.[1] && replacementRest[2]) return t('api.ruleReplacementRest', { count: replacementRest[1], date: replacementRest[2] })
    const retry = /^Zu viele Anmeldeversuche\. Bitte in (\d+) Sekunden erneut versuchen\.$/.exec(detail)
    if (retry?.[1]) return t('api.loginRetry', { count: retry[1] })
    const licenseRestriction = /^(License is read-only|Diese Lizenz ist nicht aktiv): (.+)$/.exec(detail)
    if (licenseRestriction?.[1] && licenseRestriction[2]) {
      const reason = apiErrorDetail(licenseRestriction[2]) ?? licenseRestriction[2]
      return t(licenseRestriction[1] === 'License is read-only' ? 'api.licenseReadOnlyReason' : 'api.licenseInactiveReason', { reason })
    }
    const fingerprint = /^Host-Key stimmt nicht überein \(Server meldet (.+)\)$/.exec(detail)
    if (fingerprint?.[1]) return t('api.backupFingerprintMismatch', { fingerprint: fingerprint[1] })
    const sftpConnection = /^SFTP-Verbindung fehlgeschlagen: (.+)$/.exec(detail)
    if (sftpConnection?.[1]) return t('api.backupSftpConnection', { detail: sftpConnection[1] })
    const sftpError = /^SFTP-Fehler: (.+)$/.exec(detail)
    if (sftpError?.[1]) return t('api.backupSftpError', { detail: sftpError[1] })
    const webdavConnection = /^WebDAV-Verbindung fehlgeschlagen: (.+)$/.exec(detail)
    if (webdavConnection?.[1]) return t('api.backupWebdavConnection', { detail: webdavConnection[1] })
    const webdavHttp = /^WebDAV-Server antwortete mit HTTP (\d+)$/.exec(detail)
    if (webdavHttp?.[1]) return t('api.backupWebdavHttp', { status: webdavHttp[1] })
    const s3Error = /^S3-Fehler: (.+)$/.exec(detail)
    if (s3Error?.[1]) return t('api.backupS3Error', { detail: s3Error[1] })
    const updateHttpError = /^GitHub-Update-Abfrage fehlgeschlagen \(HTTP (\d+)\)\.$/.exec(detail)
    if (updateHttpError?.[1]) return t('updates.httpError', { status: updateHttpError[1] })
    const noChannelRelease = /^Kein veröffentlichtes Release für den (stable|nightly)-Kanal gefunden\.$/.exec(detail)
    if (noChannelRelease?.[1]) return t('updates.noChannelRelease', { channel: noChannelRelease[1] })
    const registryError = /^Container-Registry-Update-Abfrage fehlgeschlagen \(HTTP (\d+)\)\.$/.exec(detail)
    if (registryError?.[1]) return t('updates.registryHttpError', { status: registryError[1] })
    const noImage = /^Kein Docker-Image-Paar für den (main|test)-Kanal gefunden\.$/.exec(detail)
    if (noImage?.[1]) return t('updates.noImage', { channel: noImage[1] })
    return locale.value === 'de' ? detail : t('api.serverDetail', { detail })
  }
  if (!Array.isArray(detail)) return null
  const messages = detail.flatMap((item: unknown) => {
    if (typeof item !== 'object' || item === null || !('msg' in item)) return []
    if (typeof item.msg !== 'string') return []
    const type = 'type' in item && typeof item.type === 'string' ? item.type : ''
    const context: unknown = 'ctx' in item ? item.ctx : null
    const limitKey = type === 'string_too_short' ? 'min_length'
      : type === 'string_too_long' ? 'max_length'
        : type === 'greater_than_equal' ? 'ge'
          : type === 'less_than_equal' ? 'le' : null
    if (limitKey && typeof context === 'object' && context !== null) {
      const limit: unknown = Object.entries(context).find(([name]) => name === limitKey)?.[1]
      if (typeof limit === 'number' && Number.isFinite(limit)) {
        const key = type === 'string_too_short' ? 'api.validationMinLength'
          : type === 'string_too_long' ? 'api.validationMaxLength'
            : type === 'greater_than_equal' ? 'api.validationMinimum' : 'api.validationMaximum'
        return [t(key, { count: limit })]
      }
    }
    if (type === 'missing' && item.msg === 'Field required') return [t('api.validationRequired')]
    if (type === 'int_parsing' && item.msg === 'Input should be a valid integer, unable to parse string as an integer') return [t('api.validationInteger')]
    return [apiErrorDetail(item.msg) ?? item.msg]
  })
  return messages.length ? [...new Set(messages)].join('; ') : null
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
