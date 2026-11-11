<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import BackupPanel from './BackupPanel.vue'
import PasswordInput from './PasswordInput.vue'
import LanguageSelector from './LanguageSelector.vue'
import { locale, t, type TranslationKey } from './i18n'
import { ApiError, TranslatedError, apiErrorDetail, errorMessage } from './i18n/apiErrors'

type Employee = { id: number; name: string; first_name?: string | null; last_name?: string | null; role: string; department_id: number | null; profile_image_data?: string | null }
type EmployeeOnboardResult = { employee: Employee; invitation_status: string | null }
type Department = { id: number; name: string; manager_user_id: number | null }
type BusinessConfiguration = {
  federal_state: string
  operational_profile: 'hospital' | 'rescue_service' | 'ils' | 'care_facility' | 'other'
  operational_profile_managed?: boolean
  federal_state_managed?: boolean
  timezone: string
  sunday_work_authorized: boolean
}
type MailSettings = {
  public_url: string
  smtp_host: string
  smtp_port: number
  smtp_username: string
  smtp_password_configured: boolean
  from_address: string
  use_ssl: boolean
  use_starttls: boolean
}
type Absence = {
  id: number
  employee_id: number
  employee_name: string
  kind: 'vacation' | 'sick' | 'other'
  start_date: string
  end_date: string
  status: 'pending' | 'approved' | 'rejected'
  note: string | null
  requested_by: string | null
  created_at: string | null
  decided_by: string | null
  decided_at: string | null
}
type SessionInfo = {
  username: string
  idle_timeout_minutes?: number | null
  role_key: string
  department_id: number | null
  can_view: boolean
  can_edit: boolean
  can_approve: boolean
  can_manage: boolean
  can_manage_department: boolean
  remember_me: boolean
  must_change_password: boolean
}
type AccountUser = {
  id: number
  username: string
  role_key: string
  department_id: number | null
  department_ids: number[]
  employee_id: number | null
  first_name?: string | null
  last_name?: string | null
  birth_date?: string | null
  address?: string | null
  phone?: string | null
  can_view: boolean
  can_edit: boolean
  can_approve: boolean
  is_locked?: boolean
  email?: string | null
  invitation_status?: string
}
type ShiftType = {
  id: number
  name: string
  start_time: string
  end_time: string
  color: string
  position: string
  required_staff: number
  break_minutes: number
  break_start_minutes: number
  department_id: number | null
  staffing_requirements?: { position: string; required_staff: number }[]
}
type Assignment = {
  id: number
  employee_id: number
  shift_type_id: number
  starts_at: string
  ends_at: string
  employee_name: string
  shift_name: string
}
type Candidate = {
  employee_id: number
  employee_name: string
  role: string
  role_match: boolean
  planned_assignments: number
}
type OptimizationSuggestion = {
  employee_id: number
  employee_name: string
  employee_role: string
  shift_type_id: number
  shift_name: string
  role_match: boolean
  starts_at: string
  ends_at: string
}
type PlanningDay = {
  target_date: string
  status: 'OPTIMAL' | 'FEASIBLE' | 'UNKNOWN'
  suggestions: OptimizationSuggestion[]
  unfilled_slots: { shift_type_id: number; shift_name: string; position: string }[]
}
type OptimizationPreview = {
  target_date: string
  status: 'OPTIMAL' | 'FEASIBLE' | 'UNKNOWN'
  suggestions: OptimizationSuggestion[]
  unfilled_slots: { shift_type_id: number; shift_name: string; position: string }[]
}
type Gap = { date: string; shift: ShiftType }
type UpdateInfo = {
  current_version: string
  channel: 'main' | 'test'
  latest_version: string | null
  update_available: boolean
  status: 'up_to_date' | 'update_available' | 'no_release' | 'unavailable'
  message: string
  release_url: string | null
  repository_url: string
  checked_at: string
}
type LicenseInfo = {
  status: 'PAID' | 'GRACE_PERIOD' | 'OVERDUE' | 'BLOCKED' | 'UNVERIFIED'
  checked_at: string | null
  license_expires_at: string | null
  grace_until: string | null
  read_only: boolean
  message: string | null
  vip: boolean
  suppress_warnings: boolean
  last_error: string | null
  next_check_at: string | null
  max_users: number | null
  features: string[]
  institution_name: string | null
  operational_profile?: string | null
  federal_state?: string | null
}
type AuditEvent = {
  id: number
  created_at: string
  actor_username: string
  action: string
  entity_type: string
  entity_id: string
}
type ProfileInfo = {
  username: string
  role_key: string
  department_id: number | null
  profile_image_data: string | null
  profile_photo_visibility: 'private' | 'department'
  first_name?: string | null
  last_name?: string | null
  birth_date?: string | null
  address?: string | null
  phone?: string | null
  remember_me: boolean
}
type TeamProfile = {
  username: string
  role_key: string
  profile_image_data: string | null
  department_id: number | null
}

const authenticated = ref(false)
const mustChangePassword = ref(false)
const requiredPassword = ref('')
const requiredPasswordConfirm = ref('')
const requiredCurrentPassword = ref('')
const theme = ref(localStorage.getItem('clinicpulse-theme') ?? 'light')
const username = ref('')
const roleKey = ref('ADMIN')
const departmentId = ref<number | null>(null)
const canView = ref(true)
const canEdit = ref(true)
const canApprove = ref(true)
const canManage = ref(true)
const canManageDepartment = ref(false)
const canManageTeam = computed(() =>
  ['ADMIN', 'HOSPITAL_MANAGEMENT', 'PERSONNEL', 'OBERARZT'].includes(roleKey.value),
)
const canManageStaff = computed(() =>
  ['ADMIN', 'HOSPITAL_MANAGEMENT', 'PERSONNEL'].includes(roleKey.value)
  || (roleKey.value === 'OBERARZT' && canManageDepartment.value),
)
const loginUsername = ref('admin')
const password = ref('')
const setupUsername = ref('')
const setupFirstName = ref('')
const setupLastName = ref('')
const setupPassword = ref('')
const setupPasswordConfirm = ref('')
const invitationToken = ref(new URLSearchParams(window.location.hash.slice(1)).get('invite') ?? '')
const invitationPassword = ref('')
const invitationPasswordConfirm = ref('')
const invitationMessage = ref(false)
const teamNotice = ref<{ key: TranslationKey; values?: Record<string, string | number> } | null>(null)
const onboardingMailSkipped = ref(localStorage.getItem('clinicpulse-onboarding-mail-skipped') === 'true')
const showMailOnboarding = computed(() =>
  roleKey.value === 'ADMIN' && departments.value.length === 0 && !onboardingMailSkipped.value,
)
const mailSettings = ref<MailSettings>({
  public_url: window.location.origin,
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password_configured: false,
  from_address: '',
  use_ssl: false,
  use_starttls: true,
})
const mailPassword = ref('')
const clearMailPassword = ref(false)
const mailSettingsMessage = ref(false)
const mailTestRecipient = ref('')
const mailTestRecipientSent = ref('')
const mailTestBusy = ref(false)
const mailSettingsLoaded = ref(false)
const mailEnabled = ref(true)
const mailModeDraft = ref(true)
const mailModeSaved = ref(false)
const setupLicenseToken = ref('')
const setupSundayWorkAuthorized = ref(false)
const setupChecked = ref(false)
const setupRequired = ref(false)
const institutionName = ref<string | null>(null)
const error = ref<string | Error>('')
const displayedError = computed(() => errorMessage(error.value))
const confirmDialog = ref<{ message: string; confirmLabel: string; resolve: (value: boolean) => void } | null>(null)

function askConfirmation(message: string, confirmLabel = t('management.delete')) {
  return new Promise<boolean>((resolve) => {
    confirmDialog.value = { message, confirmLabel, resolve }
  })
}

function answerConfirmation(answer: boolean) {
  confirmDialog.value?.resolve(answer)
  confirmDialog.value = null
}

let errorToastTimer: number | undefined
watch(error, (message) => {
  window.clearTimeout(errorToastTimer)
  if (message && authenticated.value) errorToastTimer = window.setTimeout(() => { error.value = '' }, 8000)
})
const busy = ref(false)
const employees = ref<Employee[]>([])
const shiftTypes = ref<ShiftType[]>([])
const departments = ref<Department[]>([])
const selectedPlanId = ref<number | null>(null)
const users = ref<AccountUser[]>([])
const assignments = ref<Assignment[]>([])
const today = new Date()
const weekOffset = ref(0)
const selectedDay = ref<string | null>(null)
const showEmployeeForm = ref(false)
const showShiftForm = ref(false)
const editingShiftId = ref<number | null>(null)
const showAssignmentForm = ref(false)
const showSettings = ref(false)
const settingsTab = ref('appearance')
const settingsTabs = computed(() => roleKey.value === 'ADMIN'
  ? [
      { key: 'appearance', label: t('settings.appearance') },
      { key: 'operations', label: t('settings.operations') },
      { key: 'mail', label: t('settings.mail') },
      { key: 'license', label: t('settings.license') },
      { key: 'backup', label: t('settings.backup') },
      { key: 'archive', label: t('settings.archive') },
      { key: 'security', label: t('settings.security') },
      { key: 'audit', label: t('settings.audit') },
    ]
  : [{ key: 'appearance', label: t('settings.appearance') }])
const showManagement = ref(false)
const sidebarCollapsed = ref(localStorage.getItem('clinicpulse-sidebar-collapsed') === '1')
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('clinicpulse-sidebar-collapsed', sidebarCollapsed.value ? '1' : '0')
}
const showNotifications = ref(false)
const showProfile = ref(false)
const staySignedIn = ref(false)
const profile = ref<ProfileInfo | null>(null)
const teamProfiles = ref<TeamProfile[]>([])
const profileImageData = ref<string | null>(null)
const profilePhotoVisibility = ref<'private' | 'department'>('private')
const updateChannel = ref<'main' | 'test'>('main')
let idleLogoutTimer: ReturnType<typeof setTimeout> | undefined
let lastActivityAt = Date.now()
const idleTimeoutMinutes = ref(5)
const idleTimeoutMs = () => idleTimeoutMinutes.value * 60 * 1000
const IDLE_ACTIVITY_STORAGE_KEY = 'clinicpulse-last-activity'
const employeeId = ref<number | null>(null)
const employeeRole = ref('Pflegefachkraft')
const roleCatalog = ref<{ access_roles: { key: string; label: string }[]; functions: string[] }>({
  access_roles: [
    { key: 'HOSPITAL_MANAGEMENT', label: 'Krankenhausleitung' },
    { key: 'PERSONNEL', label: 'Personaler' },
    { key: 'OBERARZT', label: 'Oberarzt' },
    { key: 'CHEFARZT', label: 'Chefarzt' },
    { key: 'KIOSK', label: 'Kiosk' },
    { key: 'EMPLOYEE', label: 'Mitarbeiter' },
  ],
  functions: ['Pflegefachkraft', 'Arzt', 'Assistenzarzt', 'Oberarzt', 'Pflegeassistenz', 'Hebamme', 'Medizinische Fachangestellte'],
})
const defaultEmployeeRole = computed(() => roleCatalog.value.functions[0] ?? 'Individuell')
const catalogFunctionKeys: Record<string, TranslationKey> = {
  Pflegefachkraft: 'function.nurse', Arzt: 'function.physician', Assistenzarzt: 'function.resident', Oberarzt: 'function.seniorPhysician',
  Pflegeassistenz: 'function.nursingAssistant', Hebamme: 'function.midwife', 'Medizinische Fachangestellte': 'function.medicalAssistant',
  Notfallsanitäter: 'function.paramedic', Rettungssanitäter: 'function.emergencyTechnician',
  Rettungsassistent: 'function.rescueAssistant', Rettungshelfer: 'function.rescueHelper', Notarzt: 'function.emergencyPhysician',
  Disponent: 'function.dispatcher', Schichtführer: 'function.shiftLeader', Auszubildender: 'function.trainee',
  Pflegehelfer: 'function.careHelper', Betreuungskraft: 'function.careWorker', Hauswirtschaft: 'function.housekeeping',
  Mitarbeiter: 'function.employee', Teamleitung: 'function.teamLeader',
}
function catalogFunctionLabel(value: string) {
  const key = Object.hasOwn(catalogFunctionKeys, value) ? catalogFunctionKeys[value] : undefined
  return key ? t(key) : value
}
const employeeDepartmentId = ref('')
const employeeCreateAccount = ref(false)
const employeeLoginUsername = ref('')
const employeeEmail = ref('')
const employeePassword = ref('')
const employeeCustomRole = ref('')
const shiftName = ref('')
const shiftBreak = ref<number | null>(null)
const shiftBreakStart = ref<number | null>(null)
const shiftRequirements = ref<{ position: string; required_staff: number }[]>([
  { position: 'Pflegefachkraft', required_staff: 1 },
])
const workRules = ref({ rest_hours: 11, max_daily_hours: 10, max_weekly_hours: 48 })
const workRulesMessage = ref(false)
const businessConfiguration = ref<BusinessConfiguration>({
  federal_state: '',
  operational_profile: 'hospital',
  timezone: 'Europe/Berlin',
  sunday_work_authorized: false,
})
const businessConfigurationMessage = ref(false)
const shiftStart = ref('07:00')
const shiftEnd = ref('15:00')
const selectedEmployee = ref('')
const selectedShift = ref('')
const selectedAssignmentPosition = ref('')
const selectedDate = ref(today.toLocaleDateString('sv-SE'))
const currentPassword = ref('')
const changedUsername = ref('')
const newPassword = ref('')
const smartGap = ref<Gap | null>(null)
const smartCandidates = ref<Candidate[]>([])
const optimizationPreview = ref<OptimizationPreview | null>(null)
const optimizationBusy = ref(false)
const showPlanning = ref(false)
const planningMode = ref<'week' | 'month'>('week')
const planningAnchor = ref(localDate(new Date()))
const planningDays = ref<PlanningDay[] | null>(null)
const planningBusy = ref(false)
const planningNotice = ref<{ key: TranslationKey; count: number } | null>(null)
const departmentName = ref('')
const editingDepartmentId = ref<number | null>(null)
const userId = ref<number | null>(null)
const userName = ref('')
const userFirstName = ref('')
const userLastName = ref('')
const userBirthDate = ref('')
const userAddress = ref('')
const userPhone = ref('')
const employeeFirstName = ref('')
const employeeLastName = ref('')
const profileFirstName = ref('')
const profileLastName = ref('')
const profileBirthDate = ref('')
const profileAddress = ref('')
const profilePhone = ref('')
const userPassword = ref('')
const userEmail = ref('')
const userRoleKey = ref('OBERARZT')
const userDepartmentIds = ref<number[]>([])
const userCanView = ref(true)
const userCanEdit = ref(false)
const userCanApprove = ref(false)
const userEmployeeId = ref<number | null>(null)
const allEmployees = ref<Employee[]>([])
const showAbsences = ref(false)
const showNextShifts = ref(false)
const showArchive = ref(false)
interface PlanArchiveSummary { id: number; created_at: string; created_by: string; start_date: string; end_date: string; department_id: number | null; department_name: string; note: string | null; entry_count: number; content_sha256: string }
const planArchives = ref<PlanArchiveSummary[]>([])
const archiveStart = ref('')
const archiveEnd = ref('')
const archiveDepartmentId = ref('')
const archiveNote = ref('')
const archiveSettings = ref<{ auto_enabled: boolean; period: string; last_period_end: string | null }>({ auto_enabled: false, period: 'monthly', last_period_end: null })
const archiveSettingsMessage = ref(false)
const idleTimeoutMessage = ref(false)
const canViewArchive = computed(() =>
  ['OBERARZT', 'CHEFARZT'].includes(roleKey.value)
  || (roleKey.value === 'HOSPITAL_MANAGEMENT' && canView.value),
)
const canViewAbsences = computed(() =>
  roleKey.value === 'EMPLOYEE'
  || (canView.value && ['OBERARZT', 'HOSPITAL_MANAGEMENT'].includes(roleKey.value)),
)
const absences = ref<Absence[]>([])
const absenceKind = ref<Absence['kind']>('vacation')
const absenceStart = ref('')
const absenceEnd = ref('')
const absenceNote = ref('')
const absenceEmployeeId = ref('')
const updateInfo = ref<UpdateInfo | null>(null)
const updateCheckBusy = ref(false)
const licenseInfo = ref<LicenseInfo | null>(null)
const licenseCheckBusy = ref(false)
const licenseTokenInput = ref('')
const appVersion = ref('')
const appArchitecture = ref('')
const displayVersion = computed(() => (appArchitecture.value ? `${appVersion.value}-${appArchitecture.value}` : appVersion.value))
const auditEvents = ref<AuditEvent[]>([])
const auditCategory = ref('')
const auditOffset = ref(0)
const auditHasMore = ref(false)
const auditBusy = ref(false)
const federalStates = [
  'Baden-Württemberg', 'Bayern', 'Berlin', 'Brandenburg', 'Bremen', 'Hamburg', 'Hessen',
  'Mecklenburg-Vorpommern', 'Niedersachsen', 'Nordrhein-Westfalen', 'Rheinland-Pfalz',
  'Saarland', 'Sachsen', 'Sachsen-Anhalt', 'Schleswig-Holstein', 'Thüringen',
]
const operationalProfiles = [
  { value: 'hospital', label: 'operations.hospital' },
  { value: 'rescue_service', label: 'operations.rescue' },
  { value: 'ils', label: 'operations.dispatch' },
  { value: 'care_facility', label: 'operations.care' },
  { value: 'other', label: 'operations.other' },
] as const

const weekStart = computed(() => {
  const date = new Date(today)
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7) + weekOffset.value * 7)
  date.setHours(0, 0, 0, 0)
  return date
})
const days = computed(() => Array.from({ length: 7 }, (_, index) => {
  const date = new Date(weekStart.value)
  date.setDate(date.getDate() + index)
  return date
}))
const weekLabel = computed(() => {
  const start = days.value[0]
  const end = days.value[6]
  return `${start.toLocaleDateString(locale.value, { day: '2-digit', month: 'short' })} – ${end.toLocaleDateString(locale.value, { day: '2-digit', month: 'short', year: 'numeric' })}`
})
const totalHours = computed(() => assignments.value.reduce((total, assignment) => {
  return total + (new Date(assignment.ends_at).getTime() - new Date(assignment.starts_at).getTime()) / 3_600_000
}, 0))
const notifications = computed(() => days.value.flatMap((day) => {
  if (roleKey.value === 'EMPLOYEE') return []
  const date = localDate(day)
  return shiftTypes.value.flatMap((shift) => {
    const open = openStaffingCount(date, shift)
    return open ? [{
      id: `${date}-${shift.id}`,
      date,
      shift,
      count: open,
    }] : []
  })
}))
const notificationDays = ref(14)
const notificationHistory = ref<{ id: string; date: string; count: number; position: string; shiftName: string }[]>([])
const nextAssignments = ref<Assignment[]>([])
const notificationsLoading = ref(false)
const vacationAlertQueue = ref<Absence[]>([])
const vacationAlert = computed(() => vacationAlertQueue.value[0] ?? null)
const pageTitle = computed(() => {
  if (!setupChecked.value) return t('page.starting')
  if (setupRequired.value && !authenticated.value) return t('page.setup')
  if (!authenticated.value) return t('page.login')
  if (showPlanning.value) return t('page.planning')
  if (showAbsences.value) return t('page.absences')
  if (showArchive.value) return t('page.archive')
  if (showManagement.value) return t('page.management')
  if (showSettings.value) return t('page.settings')
  if (showProfile.value) return t('page.profile')
  if (showNotifications.value) return t('page.notifications')
  if (showNextShifts.value) return t('schedule.nextShifts')
  if (selectedDay.value) return dateLabel(selectedDay.value)
  return t('page.schedule')
})
const repositoryUrl = 'https://github.com/CyberspaceConsulting/ClinicPulse'
const documentationUrl = 'https://cyberspaceconsulting.github.io/ClinicPulse/'
const selectedPlanName = computed(() =>
  selectedPlanId.value === null
    ? t('nav.allSchedules')
    : departments.value.find((department) => department.id === selectedPlanId.value)?.name ?? t('page.schedule'),
)
const licenseReadOnly = computed(() => licenseInfo.value?.read_only ?? true)
const canEditPlan = computed(() => roleKey.value === 'OBERARZT' && canEdit.value && !licenseReadOnly.value)
const hasScheduleAccess = computed(() => roleKey.value !== 'ADMIN' && canView.value)

watch(pageTitle, (title) => {
  document.title = `ClinicPulse – ${title}`
}, { immediate: true })

watch([authenticated, roleKey], ([isAuthenticated, role]) => {
  clearTimeout(idleLogoutTimer)
  if (!isAuthenticated || role === 'KIOSK') return
  resetIdleLogoutTimer()
})

watch([selectedDay, selectedPlanId], () => {
  optimizationPreview.value = null
})

watch([selectedPlanId, planningMode, planningAnchor], () => {
  planningDays.value = null
  planningNotice.value = null
})

const planningPeriod = computed(() => {
  const anchor = new Date(`${planningAnchor.value || localDate(new Date())}T12:00:00`)
  if (planningMode.value === 'month') {
    return {
      start: localDate(new Date(anchor.getFullYear(), anchor.getMonth(), 1, 12)),
      end: localDate(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0, 12)),
    }
  }
  const monday = new Date(anchor)
  monday.setDate(anchor.getDate() - ((anchor.getDay() + 6) % 7))
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return { start: localDate(monday), end: localDate(sunday) }
})
const planningSuggestionCount = computed(() =>
  planningDays.value?.reduce((sum, day) => sum + day.suggestions.length, 0) ?? 0,
)
const planningUnfilledCount = computed(() =>
  planningDays.value?.reduce((sum, day) => sum + day.unfilled_slots.length, 0) ?? 0,
)
const planningLoad = computed(() => {
  const counts = new Map<string, number>()
  for (const day of planningDays.value ?? []) {
    for (const item of day.suggestions) {
      counts.set(item.employee_name, (counts.get(item.employee_name) ?? 0) + 1)
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'de'))
})

watch(userRoleKey, (role) => {
  if (role !== 'EMPLOYEE') userEmployeeId.value = null
  if (role === 'HOSPITAL_MANAGEMENT') {
    userCanView.value = false
    userCanEdit.value = false
    userCanApprove.value = false
  } else if (role === 'KIOSK' || role === 'EMPLOYEE') {
    userCanView.value = true
    userCanEdit.value = false
    userCanApprove.value = false
  }
}, { flush: 'sync' })

function localDate(date: Date) {
  return date.toLocaleDateString('sv-SE')
}

function assignmentsFor(date: string, shiftTypeId: number) {
  return assignments.value.filter((item) => {
    return item.shift_type_id === shiftTypeId && localDate(new Date(item.starts_at)) === date
  })
}

function dateAssignments(date: Date) {
  const day = localDate(date)
  return assignments.value.filter((item) => localDate(new Date(item.starts_at)) === day)
}

function shiftCountLabel(count: number) {
  return t(count === 1 ? 'schedule.shiftsOne' : 'schedule.shiftsOther', { count })
}

function openCountLabel(count: number) {
  return t(count === 1 ? 'schedule.openOne' : 'schedule.openOther', { count })
}

function timeLabel(value: string) {
  return new Date(value).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
}

function dateLabel(value: string) {
  return new Date(`${value}T12:00:00`).toLocaleDateString(locale.value, {
    weekday: 'long', day: 'numeric', month: 'long',
  })
}

let apiAbortController = new AbortController()

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    signal: apiAbortController.signal,
    ...options,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  if (response.status === 401 && !path.startsWith('/auth/') && !path.startsWith('/setup')) {
    authenticated.value = false
    username.value = ''
    profile.value = null
    teamProfiles.value = []
    profileImageData.value = null
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const detail = typeof data === 'object' && data !== null && 'detail' in data ? data.detail : null
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function storeSession(result: Partial<SessionInfo> & { username: string }) {
  authenticated.value = true
  mustChangePassword.value = result.must_change_password ?? false
  username.value = result.username
  roleKey.value = result.role_key ?? 'ADMIN'
  departmentId.value = result.department_id ?? null
  canView.value = result.can_view ?? true
  canEdit.value = result.can_edit ?? true
  canApprove.value = result.can_approve ?? true
  canManage.value = result.can_manage ?? roleKey.value === 'ADMIN'
  canManageDepartment.value = result.can_manage_department ?? false
  if (result.idle_timeout_minutes) {
    idleTimeoutMinutes.value = result.idle_timeout_minutes
  } else {
    void api<{ idle_timeout_minutes?: number }>('/auth/session').then((info) => {
      if (info.idle_timeout_minutes) {
        idleTimeoutMinutes.value = info.idle_timeout_minutes
        scheduleIdleLogout()
      }
    }).catch(() => undefined)
  }
}

async function checkSetup(restoreSession = true) {
  try {
    const health = await api<{ version?: string; architecture?: string }>('/health')
    appArchitecture.value = health.architecture ?? ''
    if (health.version) appVersion.value = health.version
    const state = await api<{ setup_required: boolean; institution_name: string | null }>('/setup/status')
    setupRequired.value = state.setup_required
    institutionName.value = state.institution_name
    if (!state.setup_required && restoreSession) {
      try {
        storeSession(await api<SessionInfo>('/auth/session'))
        if (mustChangePassword.value) return
        if (canManageTeam.value) await loadMailMode()
        await loadData()
        if (roleKey.value === 'ADMIN' || (roleKey.value === 'HOSPITAL_MANAGEMENT' && !canView.value)) {
          await openManagement()
        }
        void checkForUpdates()
        void refreshLicenseStatus()
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 401) {
          error.value = err instanceof Error ? err : new TranslatedError('errors.sessionCheck')
        }
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.installationStatus')
  } finally {
    setupChecked.value = true
  }
}

async function loadRoleCatalog() {
  try {
    roleCatalog.value = await api('/role-catalog')
  } catch {
    // Der Standardkatalog bleibt aktiv, falls der Abruf scheitert.
  }
}

async function loadData() {
  void loadRoleCatalog()
  if (!authenticated.value || !hasScheduleAccess.value) return
  busy.value = true
  error.value = ''
  try {
    const from = localDate(days.value[0])
    const to = localDate(days.value[6])
    const [allStaff, allShifts, allAssignments, organization] = await Promise.all([
      api<Employee[]>('/employees'),
      api<ShiftType[]>('/shift-types'),
      api<Assignment[]>(`/assignments?from=${from}&to=${to}&timezone_offset_minutes=${new Date().getTimezoneOffset()}`),
      api<Department[]>('/departments'),
    ])
    departments.value = organization
    allEmployees.value = allStaff
    if (selectedPlanId.value !== null && !organization.some((item) => item.id === selectedPlanId.value)) {
      selectedPlanId.value = null
    }
    if (!canManage.value && selectedPlanId.value === null && organization.length) {
      selectedPlanId.value = organization[0].id
    }
    const inSelectedPlan = (departmentId: number | null) =>
      selectedPlanId.value === null || departmentId === selectedPlanId.value
    employees.value = allStaff.filter((employee) => inSelectedPlan(employee.department_id))
    shiftTypes.value = allShifts.filter((shift) => inSelectedPlan(shift.department_id))
    const shiftIds = new Set(shiftTypes.value.map((shift) => shift.id))
    assignments.value = allAssignments.filter((assignment) => shiftIds.has(assignment.shift_type_id))
    if (!selectedEmployee.value && employees.value.length) selectedEmployee.value = String(employees.value[0].id)
    if (!selectedShift.value && shiftTypes.value.length) selectedShift.value = String(shiftTypes.value[0].id)
    if (!employeeDepartmentId.value && departments.value.length) employeeDepartmentId.value = String(departments.value[0].id)
    if (!userDepartmentIds.value.length && departments.value.length) userDepartmentIds.value = [departments.value[0].id]
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.loadData')
  } finally {
    busy.value = false
  }

}

const kindLabels = computed(() => ({ vacation: t('absence.vacation'), sick: t('absence.sick'), other: t('absence.other') }))
const statusLabels = computed(() => ({ pending: t('absence.pending'), approved: t('absence.approved'), rejected: t('absence.rejected') }))
const canRequestAbsence = computed(() => roleKey.value === 'EMPLOYEE' && !licenseReadOnly.value)
const canRecordAbsence = computed(() => canEditPlan.value)

async function loadAbsences() {
  try {
    absences.value = await api<Absence[]>('/absences')
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('absence.loadFailed')
  }
}

async function loadArchives() {
  try {
    planArchives.value = await api<PlanArchiveSummary[]>('/archives')
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('archive.loadFailed')
  }
}

async function saveIdleTimeout() {
  idleTimeoutMessage.value = false
  try {
    const result = await api<{ idle_timeout_minutes: number }>('/admin/security-settings', {
      method: 'PUT',
      body: JSON.stringify({ idle_timeout_minutes: Number(idleTimeoutMinutes.value) }),
    })
    idleTimeoutMinutes.value = result.idle_timeout_minutes
    scheduleIdleLogout()
    idleTimeoutMessage.value = true
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.saveSecurity')
  }
}

async function loadArchiveSettings() {
  try {
    archiveSettings.value = await api('/admin/archive-settings')
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('archive.settingsLoadFailed')
  }
}

async function saveArchiveSettings() {
  archiveSettingsMessage.value = false
  try {
    archiveSettings.value = await api('/admin/archive-settings', {
      method: 'PUT',
      body: JSON.stringify({ auto_enabled: archiveSettings.value.auto_enabled, period: archiveSettings.value.period }),
    })
    archiveSettingsMessage.value = true
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('archive.settingsSaveFailed')
  }
}

async function openArchive() {
  showArchive.value = true
  const now = new Date()
  archiveStart.value = archiveStart.value || localDate(new Date(now.getFullYear(), now.getMonth(), 1))
  archiveEnd.value = archiveEnd.value || localDate(new Date(now.getFullYear(), now.getMonth() + 1, 0))
  if (!archiveDepartmentId.value) {
    const preferred = selectedPlanId.value ?? departments.value[0]?.id
    archiveDepartmentId.value = preferred ? String(preferred) : ''
  }
  await loadArchives()
}

async function createArchive() {
  try {
    await api('/archives', {
      method: 'POST',
      body: JSON.stringify({
        start_date: archiveStart.value,
        end_date: archiveEnd.value,
        department_id: Number(archiveDepartmentId.value),
        note: archiveNote.value.trim() || null,
      }),
    })
    archiveNote.value = ''
    await loadArchives()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('archive.createFailed')
  }
}

async function openAbsences() {
  if (roleKey.value === 'ADMIN' || !canView.value) return
  vacationAlertQueue.value = []
  showPlanning.value = false
  showNotifications.value = false
  showNextShifts.value = false
  selectedDay.value = null
  showAbsences.value = true
  absenceStart.value = absenceStart.value || localDate(new Date())
  absenceEnd.value = absenceEnd.value || absenceStart.value
  if (!absenceEmployeeId.value && employees.value.length) absenceEmployeeId.value = String(employees.value[0].id)
  await loadAbsences()
}

async function openNextShifts() {
  showPlanning.value = false
  showNotifications.value = false
  showAbsences.value = false
  showNextShifts.value = true
  const start = localDate(new Date())
  const endDate = new Date()
  endDate.setDate(endDate.getDate() + 62)
  try {
    const assignments = await api<Assignment[]>(
      `/assignments?from=${start}&to=${localDate(endDate)}&timezone_offset_minutes=${new Date().getTimezoneOffset()}`,
    )
    nextAssignments.value = assignments.filter((item) => new Date(item.starts_at).getTime() >= Date.now())
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.loadData')
  }
}

async function submitAbsence() {
  error.value = ''
  try {
    await api('/absences', {
      method: 'POST',
      body: JSON.stringify({
        kind: absenceKind.value,
        start_date: absenceStart.value,
        end_date: absenceEnd.value,
        note: absenceNote.value.trim() || null,
        ...(roleKey.value === 'EMPLOYEE' ? {} : { employee_id: Number(absenceEmployeeId.value) }),
      }),
    })
    absenceNote.value = ''
    await loadAbsences()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('absence.saveFailed')
  }
}

async function decideAbsence(absence: Absence, decision: 'approved' | 'rejected') {
  error.value = ''
  try {
    await api(`/absences/${absence.id}/decision`, { method: 'POST', body: JSON.stringify({ decision }) })
    await loadAbsences()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('absence.decisionFailed')
  }
}

async function removeAbsence(absence: Absence) {
  error.value = ''
  try {
    await api(`/absences/${absence.id}`, { method: 'DELETE' })
    await loadAbsences()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('absence.deleteFailed')
  }
}

async function checkForUpdates(refresh = false) {
  if (!authenticated.value || roleKey.value !== 'ADMIN') return
  updateCheckBusy.value = true
  try {
    updateInfo.value = await api<UpdateInfo>(`/admin/updates${refresh ? '?refresh=true' : ''}`)
    updateChannel.value = updateInfo.value.channel
    appVersion.value = updateInfo.value.current_version
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.updateStatus')
  } finally {
    updateCheckBusy.value = false
  }
}

async function refreshLicenseStatus() {
  if (!authenticated.value) return
  try {
    licenseInfo.value = await api<LicenseInfo>('/license/status')
  } catch (err) {
    if (roleKey.value === 'ADMIN') {
      error.value = err instanceof Error ? err : new TranslatedError('errors.licenseStatus')
    }
  }
}

async function loadAuditEvents(reset = false) {
  if (roleKey.value !== 'ADMIN' || auditBusy.value) return
  auditBusy.value = true
  try {
    const offset = reset ? 0 : auditOffset.value
    const result = await api<{ items: AuditEvent[]; limit: number; offset: number }>(
      `/admin/audit?limit=25&offset=${offset}${auditCategory.value ? `&category=${auditCategory.value}` : ''}`,
    )
    auditEvents.value = reset ? result.items : [...auditEvents.value, ...result.items]
    auditOffset.value = offset + result.items.length
    auditHasMore.value = result.items.length === result.limit
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('audit.loadFailed')
  } finally {
    auditBusy.value = false
  }
}

function auditActionLabel(action: string) {
  const keys: Record<string, TranslationKey> = {
    created: 'audit.created', updated: 'audit.updated', deleted: 'audit.deleted',
    login: 'audit.login', locked: 'audit.locked', unlocked: 'audit.unlocked',
    restored: 'audit.restored', login_failed: 'audit.loginFailed', invitation_accepted: 'audit.invitationAccepted',
  }
  const key = Object.hasOwn(keys, action) ? keys[action] : undefined
  return key ? t(key) : action
}

async function loadMailSettings() {
  try {
    mailSettings.value = await api<MailSettings>('/admin/mail-settings')
    mailSettingsLoaded.value = true
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('mail.loadFailed')
  }
}

async function loadMailMode() {
  const mode = await api<{ enabled: boolean }>('/account-creation/mail-mode')
  mailEnabled.value = mode.enabled
  mailModeDraft.value = mode.enabled
}

async function saveMailMode() {
  try {
    const mode = await api<{ enabled: boolean }>('/admin/mail-mode', {
      method: 'PUT',
      body: JSON.stringify({ enabled: mailModeDraft.value }),
    })
    mailEnabled.value = mode.enabled
    mailModeDraft.value = mode.enabled
    mailModeSaved.value = true
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('mail.saveFailed')
  }
}

async function saveMailSettings(): Promise<boolean> {
  mailSettingsMessage.value = false
  try {
    const saved = await api<MailSettings>('/admin/mail-settings', {
      method: 'PUT',
      body: JSON.stringify({
        public_url: mailSettings.value.public_url.trim(),
        smtp_host: mailSettings.value.smtp_host.trim(),
        smtp_port: Number(mailSettings.value.smtp_port),
        smtp_username: mailSettings.value.smtp_username.trim(),
        smtp_password: mailPassword.value || null,
        clear_smtp_password: clearMailPassword.value,
        from_address: mailSettings.value.from_address.trim(),
        use_ssl: mailSettings.value.use_ssl,
        use_starttls: mailSettings.value.use_ssl ? false : mailSettings.value.use_starttls,
      }),
    })
    mailSettings.value = saved
    mailPassword.value = ''
    clearMailPassword.value = false
    mailSettingsMessage.value = true
    return true
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('mail.saveFailed')
    return false
  }
}

async function testMailDelivery() {
  mailTestRecipientSent.value = ''
  mailTestBusy.value = true
  const recipient = mailTestRecipient.value.trim()
  try {
    if (!await saveMailSettings()) return
    await api('/admin/mail-settings/test', {
      method: 'POST',
      body: JSON.stringify({ recipient }),
    })
    mailTestRecipientSent.value = recipient
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('mail.testFailed')
  } finally {
    mailTestBusy.value = false
  }
}

function skipMailOnboarding() {
  onboardingMailSkipped.value = true
  localStorage.setItem('clinicpulse-onboarding-mail-skipped', 'true')
}

function openAppSettings(tab = 'appearance') {
  showManagement.value = false
  showEmployeeForm.value = false
  showShiftForm.value = false
  showAssignmentForm.value = false
  showSettings.value = true
  settingsTab.value = tab
  if (roleKey.value === 'ADMIN') {
    void loadBusinessConfiguration()
    void loadArchiveSettings()
    void loadWorkRules()
    mailSettingsLoaded.value = false
    void loadMailSettings()
    auditEvents.value = []
    auditOffset.value = 0
    void loadAuditEvents(true)
  }
}

async function checkLicenseNow() {
  if (!authenticated.value || roleKey.value !== 'ADMIN') return
  licenseCheckBusy.value = true
  try {
    licenseInfo.value = await api<LicenseInfo>('/admin/license/check', { method: 'POST' })
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('license.checkFailed')
  } finally {
    licenseCheckBusy.value = false
  }
}

async function replaceLicenseToken() {
  if (!licenseTokenInput.value.trim()) return
  licenseCheckBusy.value = true
  try {
    licenseInfo.value = await api<LicenseInfo>('/admin/license/token', {
      method: 'PUT',
      body: JSON.stringify({ license_token: licenseTokenInput.value.trim() }),
    })
    licenseTokenInput.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('license.replaceFailed')
  } finally {
    licenseCheckBusy.value = false
  }
}

const clockNow = ref(Date.now())
let clockTicker: ReturnType<typeof setInterval> | undefined
let vacationNotificationTicker: ReturnType<typeof setInterval> | undefined
const idleRemainingLabel = computed(() => {
  if (roleKey.value === 'KIOSK') return t('auth.noAutomaticLogout')
  const seconds = Math.max(0, Math.ceil((idleTimeoutMs() - (clockNow.value - idleActivityAt.value)) / 1000))
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  return t('auth.logoutCountdown', { clock })
})
const idleWarning = computed(() => roleKey.value !== 'KIOSK' && idleTimeoutMs() - (clockNow.value - idleActivityAt.value) <= 60000)
const idleActivityAt = ref(Date.now())

function resetIdleLogoutTimer() {
  clearTimeout(idleLogoutTimer)
  if (!authenticated.value || roleKey.value === 'KIOSK') return
  lastActivityAt = Date.now()
  idleActivityAt.value = lastActivityAt
  localStorage.setItem(IDLE_ACTIVITY_STORAGE_KEY, String(lastActivityAt))
  scheduleIdleLogout()
}

function scheduleIdleLogout() {
  clearTimeout(idleLogoutTimer)
  if (!authenticated.value || roleKey.value === 'KIOSK') return
  const remaining = idleTimeoutMs() - (Date.now() - lastActivityAt)
  if (remaining <= 0) {
    void logout().then(() => {
      error.value = new TranslatedError('auth.inactiveLogout', { count: idleTimeoutMinutes.value })
    })
    return
  }
  idleLogoutTimer = setTimeout(async () => {
    await logout()
    error.value = new TranslatedError('auth.inactiveLogout', { count: idleTimeoutMinutes.value })
  }, remaining)
}

let lastKeepAliveAt = 0

function onUserActivity() {
  if (!authenticated.value || roleKey.value === 'KIOSK') return
  resetIdleLogoutTimer()
  clockNow.value = Date.now()
  // Nur Klicks zählen als Aktivität; der Server verlängert die Sitzung per Cookie nur bei API-Aufrufen.
  if (Date.now() - lastKeepAliveAt >= 2000) {
    lastKeepAliveAt = Date.now()
    void api('/auth/session').catch(() => undefined)
  }
}

function checkIdleDeadline() {
  if (document.visibilityState !== 'visible') return
  if (
    authenticated.value
    && roleKey.value !== 'KIOSK'
    && Date.now() - lastActivityAt >= idleTimeoutMs()
  ) {
    void logout().then(() => {
      error.value = new TranslatedError('auth.inactiveLogout', { count: idleTimeoutMinutes.value })
    })
    return
  }
  scheduleIdleLogout()
}

function onSharedActivity(event: StorageEvent) {
  if (
    event.key !== IDLE_ACTIVITY_STORAGE_KEY
    || !authenticated.value
    || roleKey.value === 'KIOSK'
    || event.newValue === null
  ) return
  const activityAt = Number(event.newValue)
  if (Number.isFinite(activityAt) && activityAt > lastActivityAt) {
    lastActivityAt = activityAt
    idleActivityAt.value = activityAt
    scheduleIdleLogout()
  }
}

async function openProfile() {
  showProfile.value = true
  changedUsername.value = username.value
  currentPassword.value = ''
  newPassword.value = ''
  try {
    const [ownProfile, colleagues] = await Promise.all([
      api<ProfileInfo>('/profile/me'),
      api<TeamProfile[]>('/profile/department'),
    ])
    profile.value = ownProfile
    profileImageData.value = ownProfile.profile_image_data
    profilePhotoVisibility.value = ownProfile.profile_photo_visibility
    profileFirstName.value = ownProfile.first_name ?? ''
    profileLastName.value = ownProfile.last_name ?? ''
    profileBirthDate.value = ownProfile.birth_date ?? ''
    profileAddress.value = ownProfile.address ?? ''
    profilePhone.value = ownProfile.phone ?? ''
    teamProfiles.value = colleagues
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('profile.loadFailed')
  }
}

function selectProfileImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 256_000) {
    error.value = new TranslatedError('profile.invalidImage')
    input.value = ''
    return
  }
  const reader = new FileReader()
  reader.addEventListener('load', () => {
    if (typeof reader.result === 'string') profileImageData.value = reader.result
  })
  reader.addEventListener('error', () => {
    error.value = new TranslatedError('profile.readImageFailed')
  })
  reader.readAsDataURL(file)
}

async function saveProfile() {
  try {
    profile.value = await api<ProfileInfo>('/profile/me', {
      method: 'PUT',
      body: JSON.stringify({
        profile_image_data: profileImageData.value,
        profile_photo_visibility: profilePhotoVisibility.value,
        first_name: profileFirstName.value.trim() || null,
        last_name: profileLastName.value.trim() || null,
        ...(roleKey.value === 'ADMIN' ? {} : {
          birth_date: profileBirthDate.value || null,
          address: profileAddress.value.trim() || null,
          phone: profilePhone.value.trim() || null,
        }),
      }),
    })
    teamProfiles.value = await api<TeamProfile[]>('/profile/department')
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('profile.saveFailed')
  }
}

async function changeUpdateChannel(event: Event) {
  const channel = (event.target as HTMLSelectElement).value as 'main' | 'test'
  try {
    const result = await api<{ channel: 'main' | 'test' }>('/admin/update-channel', {
      method: 'PUT',
      body: JSON.stringify({ channel }),
    })
    updateChannel.value = result.channel
    await checkForUpdates(true)
  } catch (err) {
    updateChannel.value = updateInfo.value?.channel ?? 'main'
    error.value = err instanceof Error ? err : new TranslatedError('errors.updateChannel')
  }
}

async function loadWorkRules() {
  try {
    workRules.value = await api('/admin/work-rules')
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('operations.rulesLoadFailed')
  }
}

async function loadBusinessConfiguration() {
  try {
    businessConfiguration.value = await api<BusinessConfiguration>('/admin/business-configuration')
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('operations.loadFailed')
  }
}

async function saveBusinessConfiguration() {
  businessConfigurationMessage.value = false
  try {
    businessConfiguration.value = await api<BusinessConfiguration>('/admin/business-configuration', {
      method: 'PUT',
      body: JSON.stringify(businessConfiguration.value),
    })
    businessConfigurationMessage.value = true
    void loadRoleCatalog()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('operations.saveFailed')
  }
}

async function saveWorkRules() {
  workRulesMessage.value = false
  try {
    workRules.value = await api('/admin/work-rules', { method: 'PUT', body: JSON.stringify(workRules.value) })
    workRulesMessage.value = true
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('operations.rulesSaveFailed')
  }
}

async function login() {
  busy.value = true
  error.value = ''
  try {
    const result = await api<SessionInfo>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        username: loginUsername.value,
        password: password.value,
        stay_signed_in: staySignedIn.value,
      }),
    })
    storeSession(result)
    staySignedIn.value = result.remember_me
    password.value = ''
    if (mustChangePassword.value) return
    if (canManageTeam.value) await loadMailMode()
    await loadData()
    if (roleKey.value === 'ADMIN' || (roleKey.value === 'HOSPITAL_MANAGEMENT' && !canView.value)) {
      await openManagement()
    }
    void checkForUpdates()
    void refreshLicenseStatus()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.login')
  } finally {
    busy.value = false
  }
}

async function changeRequiredPassword() {
  if (requiredPassword.value !== requiredPasswordConfirm.value) {
    error.value = new TranslatedError('auth.passwordMismatch')
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = await api<SessionInfo>('/settings/account', {
      method: 'PUT',
      body: JSON.stringify({
        username: username.value,
        current_password: requiredCurrentPassword.value,
        new_password: requiredPassword.value,
      }),
    })
    storeSession(result)
    requiredCurrentPassword.value = ''
    requiredPassword.value = ''
    requiredPasswordConfirm.value = ''
    if (canManageTeam.value) await loadMailMode()
    await loadData()
    if (roleKey.value === 'ADMIN' || (roleKey.value === 'HOSPITAL_MANAGEMENT' && !canView.value)) {
      await openManagement()
    }
    void checkForUpdates()
    void refreshLicenseStatus()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.saveSettings')
  } finally {
    busy.value = false
  }
}

async function acceptInvitation() {
  if (invitationPassword.value !== invitationPasswordConfirm.value) {
    error.value = new TranslatedError('auth.passwordMismatch')
    return
  }
  busy.value = true
  error.value = ''
  try {
    await api('/auth/accept-invitation', {
      method: 'POST',
      body: JSON.stringify({ token: invitationToken.value, password: invitationPassword.value }),
    })
    invitationToken.value = ''
    invitationPassword.value = ''
    invitationPasswordConfirm.value = ''
    invitationMessage.value = true
    window.history.replaceState({}, '', window.location.pathname + window.location.search)
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.acceptInvitation')
  } finally {
    busy.value = false
  }
}

async function completeSetup() {
  if (setupPassword.value !== setupPasswordConfirm.value) {
    error.value = new TranslatedError('auth.passwordMismatch')
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = await api<SessionInfo>('/setup', {
      method: 'POST',
      body: JSON.stringify({
        username: setupUsername.value,
        first_name: setupFirstName.value.trim(),
        last_name: setupLastName.value.trim(),
        password: setupPassword.value,
        license_token: setupLicenseToken.value,
        sunday_work_authorized: setupSundayWorkAuthorized.value,
      }),
    })
    storeSession(result)
    setupRequired.value = false
    const installationInfo = await api<{ institution_name: string | null }>('/setup/status')
    institutionName.value = installationInfo.institution_name
    setupPassword.value = ''
    setupPasswordConfirm.value = ''
    setupLicenseToken.value = ''
    await loadData()
    if (roleKey.value === 'ADMIN' || (roleKey.value === 'HOSPITAL_MANAGEMENT' && !canView.value)) {
      await openManagement()
    }
    void checkForUpdates()
    void refreshLicenseStatus()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.setup')
  } finally {
    busy.value = false
  }
}

async function logout() {
  // Laufende Anfragen abbrechen, damit sie das Sitzungs-Cookie nach dem Abmelden nicht erneuern.
  apiAbortController.abort()
  apiAbortController = new AbortController()
  try {
    await api('/auth/logout', { method: 'POST' })
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.logout')
  }
  authenticated.value = false
  mustChangePassword.value = false
  requiredCurrentPassword.value = ''
  requiredPassword.value = ''
  requiredPasswordConfirm.value = ''
  username.value = ''
  assignments.value = []
  employees.value = []
  shiftTypes.value = []
  departments.value = []
  users.value = []
  showSettings.value = false
  showAbsences.value = false
  showProfile.value = false
  showManagement.value = false
  await checkSetup(false)
}

function applyTheme(value: string) {
  theme.value = value
  localStorage.setItem('clinicpulse-theme', value)
  document.documentElement.dataset.theme = value
}

async function submitEmployee() {
  try {
    const body = {
        first_name: employeeFirstName.value.trim(),
        last_name: employeeLastName.value.trim(),
        role: (employeeRole.value === 'Individuell' ? employeeCustomRole.value : employeeRole.value).trim(),
        department_id: Number(employeeDepartmentId.value),
        create_account: employeeCreateAccount.value,
        username: employeeCreateAccount.value ? employeeLoginUsername.value.trim() : null,
        email: employeeCreateAccount.value ? employeeEmail.value.trim() || null : null,
        password: employeeCreateAccount.value && !mailEnabled.value ? employeePassword.value : null,
    }
    const result = employeeId.value
      ? await api<Employee>('/employees/' + employeeId.value, {
          method: 'PUT',
          body: JSON.stringify(body),
        }).then((employee) => ({ employee, invitation_status: null }))
      : await api<EmployeeOnboardResult>('/employees/onboard', {
          method: 'POST',
          body: JSON.stringify(body),
        })
    employeeId.value = null
    employeeFirstName.value = ''
  employeeLastName.value = ''
    employeeRole.value = defaultEmployeeRole.value
    employeeCustomRole.value = ''
    employeeCreateAccount.value = false
    employeeLoginUsername.value = ''
    employeeEmail.value = ''
    employeePassword.value = ''
    showEmployeeForm.value = false
    if (result.invitation_status === 'pending') {
      teamNotice.value = { key: 'management.employeeInvited' }
    } else if (result.invitation_status === 'delivery_failed') {
      teamNotice.value = { key: 'management.employeeInvitationFailed' }
    } else {
      teamNotice.value = { key: 'management.employeeCreated' }
    }
    if (authenticated.value && canView.value) await loadData()
    if (canManageTeam.value) await openManagement()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.createEmployee')
  }
}

function editEmployee(employee: Employee) {
  employeeId.value = employee.id
  employeeFirstName.value = employee.first_name ?? employee.name.split(' ')[0] ?? ''
  employeeLastName.value = employee.last_name ?? employee.name.split(' ').slice(1).join(' ')
  const commonRoles = roleCatalog.value.functions
  employeeRole.value = commonRoles.includes(employee.role) ? employee.role : 'Individuell'
  employeeCustomRole.value = commonRoles.includes(employee.role) ? '' : employee.role
  employeeDepartmentId.value = employee.department_id === null ? '' : String(employee.department_id)
  employeeCreateAccount.value = false
  showEmployeeForm.value = true
}

function newEmployee() {
  employeeId.value = null
  employeeFirstName.value = ''
  employeeLastName.value = ''
  employeeRole.value = defaultEmployeeRole.value
  employeeCustomRole.value = ''
  employeeDepartmentId.value = String(selectedPlanId.value ?? departments.value[0]?.id ?? '')
  employeeCreateAccount.value = false
  employeeLoginUsername.value = ''
  employeeEmail.value = ''
  employeePassword.value = ''
  showEmployeeForm.value = true
}

async function submitShift() {
  try {
    const existing = editingShiftId.value === null
      ? undefined
      : shiftTypes.value.find((item) => item.id === editingShiftId.value)
    await api(editingShiftId.value === null ? '/shift-types' : `/shift-types/${editingShiftId.value}`, {
      method: editingShiftId.value === null ? 'POST' : 'PUT',
      body: JSON.stringify({
        name: shiftName.value.trim(),
        start_time: `${shiftStart.value}:00`,
        end_time: `${shiftEnd.value}:00`,
        color: existing?.color ?? '#287b71',
        position: shiftRequirements.value[0]?.position.trim() ?? 'Pflegefachkraft',
        required_staff: shiftRequirements.value.reduce((sum, item) => sum + item.required_staff, 0),
        staffing_requirements: shiftRequirements.value.map((item) => ({
          position: item.position.trim(),
          required_staff: item.required_staff,
        })),
        break_minutes: shiftBreak.value,
        break_start_minutes: shiftBreakStart.value,
        department_id: existing?.department_id ?? selectedPlanId.value ?? departmentId.value,
      }),
    })
    editingShiftId.value = null
    shiftName.value = ''
    shiftRequirements.value = [{ position: 'Pflegefachkraft', required_staff: 1 }]
    shiftBreak.value = null
    shiftBreakStart.value = null
    showShiftForm.value = false
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.createShift')
  }
}

function startNewShift() {
  editingShiftId.value = null
  shiftName.value = ''
  shiftStart.value = '07:00'
  shiftEnd.value = '15:00'
  shiftRequirements.value = [{ position: defaultEmployeeRole.value, required_staff: 1 }]
  shiftBreak.value = null
  shiftBreakStart.value = null
  showShiftForm.value = true
}

function editShift(shift: ShiftType) {
  editingShiftId.value = shift.id
  shiftName.value = shift.name
  shiftStart.value = shift.start_time.slice(0, 5)
  shiftEnd.value = shift.end_time.slice(0, 5)
  shiftRequirements.value = shift.staffing_requirements?.length
    ? shift.staffing_requirements.map((item) => ({ ...item }))
    : [{ position: shift.position, required_staff: shift.required_staff }]
  shiftBreak.value = shift.break_minutes
  shiftBreakStart.value = shift.break_start_minutes
  showShiftForm.value = true
}

function addShiftRequirement() {
  shiftRequirements.value.push({ position: defaultEmployeeRole.value, required_staff: 1 })
}

function removeShiftRequirement(index: number) {
  if (shiftRequirements.value.length > 1) shiftRequirements.value.splice(index, 1)
}

async function removeShift(shift: ShiftType) {
  if (!window.confirm(t('form.confirmDeleteShift', { name: shift.name }))) return
  try {
    await api(`/shift-types/${shift.id}`, { method: 'DELETE' })
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.deleteShift')
  }
}

function requirementsFor(shift: ShiftType) {
  return shift.staffing_requirements?.length
    ? shift.staffing_requirements
    : [{ position: shift.position, required_staff: shift.required_staff }]
}

function openPositionsFor(date: string, shift: ShiftType) {
  if (roleKey.value === 'EMPLOYEE') return []
  const assigned = assignmentsFor(date, shift.id)
  const requirements = requirementsFor(shift)
  const qualificationRequired = requirements.length > 1
    || requirements.some((requirement) => requirement.position.trim().toLocaleLowerCase() === 'oberarzt')
  if (!qualificationRequired) {
    return Array.from(
      { length: Math.max(0, requirements[0].required_staff - assigned.length) },
      () => requirements[0].position,
    )
  }
  return requirements.flatMap((requirement) => {
    const matching = assigned.filter((assignment) =>
      employees.value.find((employee) => employee.id === assignment.employee_id)?.role.trim().toLocaleLowerCase()
      === requirement.position.trim().toLocaleLowerCase())
    return Array.from(
      { length: Math.max(0, requirement.required_staff - matching.length) },
      () => requirement.position,
    )
  })
}

const selectedAssignmentShift = computed(() =>
  shiftTypes.value.find((shift) => String(shift.id) === selectedShift.value),
)
const assignableEmployees = computed(() => {
  const shift = selectedAssignmentShift.value
  if (!shift) return employees.value
  const requirements = requirementsFor(shift)
  if (
    requirements.length === 1
    && requirements[0].position.trim().toLocaleLowerCase() !== 'oberarzt'
  ) return employees.value
  const openPositions = openPositionsFor(selectedDate.value, shift)
  const position = selectedAssignmentPosition.value && openPositions.includes(selectedAssignmentPosition.value)
    ? selectedAssignmentPosition.value
    : openPositions[0]
  return position
    ? employees.value.filter((employee) =>
        employee.role.trim().toLocaleLowerCase() === position.trim().toLocaleLowerCase())
    : []
})
watch(assignableEmployees, (available) => {
  if (!available.some((employee) => String(employee.id) === selectedEmployee.value)) {
    selectedEmployee.value = available[0] ? String(available[0].id) : ''
  }
})

function openStaffingCount(date: string, shift: ShiftType) {
  return openPositionsFor(date, shift).length
}

function staffingSummary(shift: ShiftType) {
  return requirementsFor(shift)
    .map((item) => `${item.required_staff} × ${catalogFunctionLabel(item.position)}`)
    .join(' · ')
}

function assignmentPosition(assignment: Assignment, shift: ShiftType) {
  const employeeRole = employees.value.find((employee) => employee.id === assignment.employee_id)?.role
  return requirementsFor(shift).find((item) =>
    item.position.trim().toLocaleLowerCase() === employeeRole?.trim().toLocaleLowerCase())?.position
    ?? employeeRole
    ?? shift.position
}

function shiftInterval(date: string, shift: ShiftType) {
  const start = new Date(`${date}T${shift.start_time}`)
  const end = new Date(`${date}T${shift.end_time}`)
  if (end <= start) end.setDate(end.getDate() + 1)
  return { starts_at: start.toISOString(), ends_at: end.toISOString() }
}

async function addAssignment(employeeId: number, date: string, shift: ShiftType) {
  const interval = shiftInterval(date, shift)
  await api('/assignments', {
    method: 'POST',
    body: JSON.stringify({
      employee_id: employeeId,
      shift_type_id: shift.id,
      ...interval,
    }),
  })
  smartGap.value = null
  smartCandidates.value = []
  await loadData()
}

async function submitAssignment() {
  const shift = shiftTypes.value.find((item) => item.id === Number(selectedShift.value))
  if (!shift) {
    error.value = new TranslatedError('schedule.shiftTypeRequired')
    return
  }
  try {
    await addAssignment(Number(selectedEmployee.value), selectedDate.value, shift)
    showAssignmentForm.value = false
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.planShift')
  }
}

async function removeAssignment(id: number) {
  if (!await askConfirmation(t('management.removeShiftConfirm'), t('management.removeShift'))) return
  try {
    await api(`/assignments/${id}`, { method: 'DELETE' })
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.removeShift')
  }
}

async function suggestFor(date: string, shift: ShiftType) {
  smartGap.value = { date, shift }
  const interval = shiftInterval(date, shift)
  const params = new URLSearchParams({
    shift_type_id: String(shift.id),
    starts_at: interval.starts_at,
    ends_at: interval.ends_at,
  })
  try {
    const result = await api<{ candidates: Candidate[] }>(`/smart-selection?${params}`)
    smartCandidates.value = result.candidates
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.smartSelection')
    smartGap.value = null
  }
}

async function approveCandidate(candidate: Candidate) {
  if (!smartGap.value) return
  try {
    const interval = shiftInterval(smartGap.value.date, smartGap.value.shift)
    await api('/smart-selection/approve', {
      method: 'POST',
      body: JSON.stringify({
        employee_id: candidate.employee_id,
        shift_type_id: smartGap.value.shift.id,
        ...interval,
      }),
    })
    smartGap.value = null
    smartCandidates.value = []
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.applySuggestion')
  }
}

function openPlanning() {
  showAbsences.value = false
  showNotifications.value = false
  showNextShifts.value = false
  showPlanning.value = true
  selectedDay.value = null
}

async function proposePlanning() {
  planningBusy.value = true
  planningDays.value = null
  planningNotice.value = null
  error.value = ''
  try {
    const result = await api<{ days: PlanningDay[] }>('/planning/preview', {
      method: 'POST',
      body: JSON.stringify({
        start_date: planningPeriod.value.start,
        end_date: planningPeriod.value.end,
        ...(selectedPlanId.value === null ? {} : { department_id: selectedPlanId.value }),
      }),
    })
    planningDays.value = result.days
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('planning.calculateFailed')
  } finally {
    planningBusy.value = false
  }
}

async function approvePlanning() {
  if (!planningDays.value || !planningSuggestionCount.value) return
  planningBusy.value = true
  error.value = ''
  try {
    const result = await api<{ created: number }>('/planning/approve', {
      method: 'POST',
      body: JSON.stringify({
        items: planningDays.value.flatMap((day) => day.suggestions.map((item) => ({
          employee_id: item.employee_id,
          shift_type_id: item.shift_type_id,
          target_date: day.target_date,
        }))),
      }),
    })
    planningNotice.value = { key: result.created === 1 ? 'planning.approvedOne' : 'planning.approvedOther', count: result.created }
    planningDays.value = null
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('planning.approveFailed')
  } finally {
    planningBusy.value = false
  }
}

async function optimizeSelectedDay() {
  if (!selectedDay.value) return
  optimizationBusy.value = true
  optimizationPreview.value = null
  error.value = ''
  try {
    optimizationPreview.value = await api<OptimizationPreview>('/optimization/preview', {
      method: 'POST',
      body: JSON.stringify({
        target_date: selectedDay.value,
        ...(selectedPlanId.value === null ? {} : { department_id: selectedPlanId.value }),
      }),
    })
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.calculateOptimization')
  } finally {
    optimizationBusy.value = false
  }
}

async function applyOptimizationSuggestion(suggestion: OptimizationSuggestion) {
  try {
    await api('/assignments', {
      method: 'POST',
      body: JSON.stringify({
        employee_id: suggestion.employee_id,
        shift_type_id: suggestion.shift_type_id,
        starts_at: suggestion.starts_at,
        ends_at: suggestion.ends_at,
      }),
    })
    if (optimizationPreview.value) {
      optimizationPreview.value.suggestions = optimizationPreview.value.suggestions.filter(
        (item) => item.employee_id !== suggestion.employee_id
          || item.shift_type_id !== suggestion.shift_type_id,
      )
    }
    await loadData()
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.applyOptimization')
  }
}

function dragEmployee(event: DragEvent, employee: Employee) {
  event.dataTransfer?.setData('text/plain', String(employee.id))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy'
}

async function dropEmployee(event: DragEvent, date: string, shift: ShiftType) {
  const employeeId = Number(event.dataTransfer?.getData('text/plain'))
  if (!employeeId) return
  try {
    await addAssignment(employeeId, date, shift)
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.assignShift')
  }
}

async function saveSettings() {
  try {
    const result = await api<SessionInfo>('/settings/account', {
      method: 'PUT',
      body: JSON.stringify({
        current_password: currentPassword.value,
        username: changedUsername.value.trim(),
        new_password: newPassword.value || null,
      }),
    })
    storeSession(result)
    currentPassword.value = ''
    newPassword.value = ''
    showProfile.value = false
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.saveSettings')
  }
}

async function openManagement() {
    void loadRoleCatalog()
    showManagement.value = true
    if (!canManageTeam.value) return
    try {
      await loadMailMode()
      const [managedUsers, organization, staff] = await Promise.all([
        api<AccountUser[]>('/users'),
        api<Department[]>('/departments'),
        api<Employee[]>('/employees'),
      ])
      users.value = managedUsers
      departments.value = organization
      allEmployees.value = staff
      if (!employeeDepartmentId.value && organization.length) employeeDepartmentId.value = String(organization[0].id)
      if (['PERSONNEL', 'OBERARZT'].includes(roleKey.value) && userId.value === null) resetUserForm()
    } catch (err) {
      error.value = err instanceof Error ? err : new TranslatedError('errors.loadManagement')
    }
  }

function resetUserForm() {
    userId.value = null
    userName.value = ''
    userFirstName.value = ''
    userLastName.value = ''
    userBirthDate.value = ''
    userAddress.value = ''
    userPhone.value = ''
    userPassword.value = ''
    userEmail.value = ''
    userRoleKey.value = ['PERSONNEL', 'OBERARZT'].includes(roleKey.value) ? 'EMPLOYEE' : 'OBERARZT'
    userDepartmentIds.value = departments.value.length ? [departments.value[0].id] : []
    userEmployeeId.value = null
    userCanView.value = userRoleKey.value !== 'HOSPITAL_MANAGEMENT'
    userCanEdit.value = false
    userCanApprove.value = false
  }

function editUser(user: AccountUser) {
    userId.value = user.id
    userName.value = user.username
    userFirstName.value = user.first_name ?? ''
    userLastName.value = user.last_name ?? ''
    userBirthDate.value = user.birth_date ?? ''
    userAddress.value = user.address ?? ''
    userPhone.value = user.phone ?? ''
    userPassword.value = ''
    userEmail.value = user.email ?? ''
    userRoleKey.value = user.role_key
    userDepartmentIds.value = [...(user.department_ids ?? (user.department_id ? [user.department_id] : []))]
    userCanView.value = user.can_view
    userCanEdit.value = user.can_edit
    userCanApprove.value = user.can_approve
    userEmployeeId.value = user.employee_id ?? null
  }

async function toggleUserLock(user: AccountUser) {
    try {
      const updated = await api<AccountUser>(`/users/${user.id}/lock`, {
        method: 'PUT',
        body: JSON.stringify({ locked: !user.is_locked }),
      })
      users.value = users.value.map((item) => (item.id === updated.id ? updated : item))
    } catch (err) {
      error.value = err instanceof Error ? err : new TranslatedError('errors.changeAccount')
    }
  }

  async function resendInvitation(user: AccountUser) {
      try {
        const updated = await api<AccountUser>(`/users/${user.id}/invitation`, { method: 'POST' })
        users.value = users.value.map((item) => item.id === updated.id ? updated : item)
        teamNotice.value = updated.invitation_status === 'pending'
          ? { key: 'management.invitationResent', values: { email: String(updated.email) } }
          : { key: 'management.invitationResendFailed' }
      } catch (err) {
        error.value = err instanceof Error ? err : new TranslatedError('errors.sendInvitation')
      }
  }

  async function revokeInvitation(user: AccountUser) {
        if (!await askConfirmation(t('management.revokeConfirm', { name: user.username }), t('management.revokeInvitation'))) return
        try {
          await api(`/users/${user.id}/invitation`, { method: 'DELETE' })
          teamNotice.value = { key: 'management.invitationRevokedNotice', values: { name: user.username } }
          await openManagement()
        } catch (err) {
          error.value = err instanceof Error ? err : new TranslatedError('errors.revokeInvitation')
        }
  }

  async function saveUser() {
    try {
      const payload = {
        username: userName.value.trim(),
        first_name: userFirstName.value.trim(),
        last_name: userLastName.value.trim(),
        birth_date: userBirthDate.value || null,
        address: userAddress.value.trim() || null,
        phone: userPhone.value.trim() || null,
        email: userEmail.value.trim() || null,
        role_key: userRoleKey.value,
        department_id: ['ADMIN', 'HOSPITAL_MANAGEMENT', 'PERSONNEL'].includes(userRoleKey.value)
          ? null
          : userDepartmentIds.value[0] ?? null,
        department_ids: ['ADMIN', 'HOSPITAL_MANAGEMENT', 'PERSONNEL'].includes(userRoleKey.value)
          ? []
          : userDepartmentIds.value,
        can_view: userCanView.value,
        can_edit: userRoleKey.value === 'CHEFARZT' || userRoleKey.value === 'EMPLOYEE' ? false : userCanEdit.value,
        can_approve: userRoleKey.value === 'CHEFARZT' || userRoleKey.value === 'EMPLOYEE' ? false : userCanApprove.value,
        employee_id: userRoleKey.value === 'EMPLOYEE' ? userEmployeeId.value : null,
        ...(userId.value ? { new_password: userPassword.value || null } : { password: mailEnabled.value && userEmail.value.trim() ? null : userPassword.value || null }),
      }
      const saved = await api<AccountUser>(userId.value ? `/users/${userId.value}` : '/users', {
        method: userId.value ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      })
      if (saved.invitation_status === 'pending') {
        teamNotice.value = { key: 'management.accountInvited', values: { email: String(saved.email) } }
      } else if (saved.invitation_status === 'delivery_failed') {
        teamNotice.value = { key: 'management.accountInvitationFailed' }
      }
      resetUserForm()
      await openManagement()
    } catch (err) {
      error.value = err instanceof Error ? err : new TranslatedError('errors.saveAccount')
    }
  }

async function removeUser(user: AccountUser) {
    if (!await askConfirmation(t('management.deleteAccountConfirm', { name: user.username }))) return
    try {
      await api(`/users/${user.id}`, { method: 'DELETE' })
      await openManagement()
    } catch (err) {
      error.value = err instanceof Error ? err : new TranslatedError('errors.deleteAccount')
    }
  }

async function setDepartmentLeader(department: Department, value: string) {
  try {
    const updated = await api<Department>(`/departments/${department.id}/leader`, {
      method: 'PUT',
      body: JSON.stringify({ manager_user_id: value ? Number(value) : null }),
    })
    departments.value = departments.value.map((item) => item.id === updated.id ? updated : item)
    storeSession(await api<SessionInfo>('/auth/session'))
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('errors.saveDepartment')
  }
}

async function saveDepartment() {
    try {
      await api(editingDepartmentId.value ? `/departments/${editingDepartmentId.value}` : '/departments', {
        method: editingDepartmentId.value ? 'PUT' : 'POST',
        body: JSON.stringify({ name: departmentName.value.trim() }),
      })
      departmentName.value = ''
      editingDepartmentId.value = null
      await openManagement()
    } catch (err) {
      error.value = err instanceof Error ? err : new TranslatedError('errors.saveDepartment')
    }
  }

function editDepartment(department: Department) {
    editingDepartmentId.value = department.id
    departmentName.value = department.name
  }

async function removeDepartment(department: Department) {
    if (!await askConfirmation(t('management.deleteDepartmentConfirm', { name: department.name }))) return
    try {
      await api(`/departments/${department.id}`, { method: 'DELETE' })
      await openManagement()
    } catch (err) {
      error.value = err instanceof Error ? err : new TranslatedError('errors.deleteDepartment')
    }
  }

function systemRoleSelectable(key: string) {
  if (key === 'ADMIN') return roleKey.value === 'ADMIN'
  if (roleKey.value === 'PERSONNEL') return key === 'EMPLOYEE'
  if (roleKey.value === 'OBERARZT') return key === 'EMPLOYEE'
  if (key === 'HOSPITAL_MANAGEMENT') return roleKey.value === 'ADMIN'
  if (key === 'PERSONNEL') return roleKey.value !== 'EMPLOYEE'
  return true
}

function initialsOf(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase() || '?'
}

function employeePhoto(employeeId: number | null | undefined) {
  return employees.value.find((item) => item.id === employeeId)?.profile_image_data ?? null
}

function roleLabel(key: string) {
  const catalogLabel = roleCatalog.value.access_roles.find((role) => role.key === key)?.label
  const managementLabels: Record<string, TranslationKey> = {
    Krankenhausleitung: 'role.hospitalManagement',
    Wachleitung: 'role.stationManagement',
    Leitstellenleitung: 'role.dispatchManagement',
    Einrichtungsleitung: 'role.facilityManagement',
    Leitung: 'role.management',
  }
  if (key === 'HOSPITAL_MANAGEMENT') {
    const labelKey = catalogLabel ? managementLabels[catalogLabel] : 'role.hospitalManagement'
    return labelKey ? t(labelKey) : catalogLabel ?? key
  }
  const roles: Record<string, TranslationKey> = {
    ADMIN: 'role.admin', PERSONNEL: 'role.personnel', OBERARZT: 'role.seniorPhysician',
    CHEFARZT: 'role.chiefPhysician', KIOSK: 'role.kiosk', EMPLOYEE: 'role.employee',
  }
  return roles[key] ? t(roles[key]) : catalogLabel ?? key
}

function moveWeek(amount: number) {
  weekOffset.value += amount
  void loadData()
}

function selectPlan(departmentId: number | null) {
  showAbsences.value = false
  showNextShifts.value = false
  if (selectedPlanId.value === departmentId) return
  showNotifications.value = false
  selectedPlanId.value = departmentId
  selectedDay.value = null
  smartGap.value = null
  smartCandidates.value = []
  selectedEmployee.value = ''
  selectedShift.value = ''
  void loadData()
}

function openNotification(item: { date: string }) {
  selectedDay.value = item.date
  showNotifications.value = false
  showNextShifts.value = false
}

async function loadNotificationHistory() {
  if (roleKey.value === 'ADMIN') {
    notificationHistory.value = []
    return
  }
  notificationsLoading.value = true
  try {
    if (roleKey.value === 'EMPLOYEE') {
      absences.value = await api<Absence[]>('/absences')
      notificationHistory.value = []
      return
    }
    const today = new Date()
    const start = new Date(today)
    start.setDate(start.getDate() - notificationDays.value)
    const from = localDate(start)
    const to = localDate(today)
    const [shifts, rangeAssignments] = await Promise.all([
      Promise.resolve(shiftTypes.value),
      api<Assignment[]>(`/assignments?from=${from}&to=${to}&timezone_offset_minutes=${new Date().getTimezoneOffset()}`),
    ])
    const shiftIds = new Set(shifts.map((shift) => shift.id))
    const items: typeof notificationHistory.value = []
    for (let offset = 0; offset <= notificationDays.value; offset++) {
      const day = new Date(today)
      day.setDate(day.getDate() - offset)
      const date = localDate(day)
      for (const shift of shifts) {
        const filled = rangeAssignments.filter((item) => shiftIds.has(item.shift_type_id) && item.shift_type_id === shift.id && localDate(new Date(item.starts_at)) === date).length
        const open = Math.max(0, shift.required_staff - filled)
        if (open) items.push({ id: `${date}-${shift.id}`, date, count: open, position: shift.position, shiftName: shift.name })
      }
    }
    notificationHistory.value = items
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('notifications.loadFailed')
  } finally {
    notificationsLoading.value = false
  }
}

function openNotificationsPage() {
  showAbsences.value = false
  showNextShifts.value = false
  showPlanning.value = false
  selectedDay.value = null
  showNotifications.value = true
  void loadNotificationHistory()
}

async function checkPendingVacationRequests() {
  if (!authenticated.value || roleKey.value !== 'OBERARZT' || !canApprove.value) return
  try {
    const pending = await api<Absence[]>('/absences?status=pending')
    const key = `clinicpulse-vacation-alerts:${username.value}`
    const saved = JSON.parse(localStorage.getItem(key) ?? '[]') as unknown
    if (!Array.isArray(saved) || saved.some((id) => !Number.isInteger(id))) {
      throw new Error('Stored vacation notification state is invalid')
    }
    const seen = new Set<number>(saved)
    const newRequests = pending.filter((absence) =>
      absence.kind === 'vacation' && !seen.has(absence.id))
    if (!newRequests.length) return
    for (const absence of newRequests) seen.add(absence.id)
    localStorage.setItem(key, JSON.stringify([...seen].slice(-100)))
    vacationAlertQueue.value.push(...newRequests)
  } catch (err) {
    error.value = err instanceof Error ? err : new TranslatedError('notifications.loadFailed')
  }
}

function dismissVacationAlert() {
  vacationAlertQueue.value.shift()
}

function reviewVacationRequests() {
  vacationAlertQueue.value = []
  void openAbsences()
}

watch([authenticated, roleKey, canApprove], ([isAuthenticated, role, canApproveAbsences]) => {
  clearInterval(vacationNotificationTicker)
  if (!isAuthenticated || role !== 'OBERARZT' || !canApproveAbsences) return
  void checkPendingVacationRequests()
  vacationNotificationTicker = setInterval(() => void checkPendingVacationRequests(), 60_000)
})

onMounted(() => {
  document.documentElement.dataset.theme = theme.value
  for (const eventName of ['pointerdown']) {
    document.addEventListener(eventName, onUserActivity, { passive: true })
  }
  document.addEventListener('visibilitychange', checkIdleDeadline)
  clockTicker = setInterval(() => { clockNow.value = Date.now() }, 1000)
  window.addEventListener('storage', onSharedActivity)
  void checkSetup()
})

onBeforeUnmount(() => {
  clearInterval(clockTicker)
  clearInterval(vacationNotificationTicker)
  clearTimeout(idleLogoutTimer)
  for (const eventName of ['pointerdown', 'keydown', 'touchstart', 'wheel']) {
    document.removeEventListener(eventName, onUserActivity)
  }
  document.removeEventListener('visibilitychange', checkIdleDeadline)
  window.removeEventListener('storage', onSharedActivity)
})
</script>

<template>
  <main v-if="!setupChecked" class="login-shell">
    <section class="login-card"><LanguageSelector /><div class="brand-mark">C</div><h1>{{ t('auth.starting') }}</h1><p class="muted">{{ t('auth.checkingSetup') }}</p><footer class="login-footer"><a :href="repositoryUrl" target="_blank" rel="noopener noreferrer">{{ t('common.github') }}</a> · <a :href="documentationUrl" target="_blank" rel="noopener noreferrer">{{ t('common.documentation') }}</a></footer></section>
  </main>

  <main v-else-if="setupRequired && !authenticated" class="login-shell">
    <section class="login-card setup-card">
      <LanguageSelector />
      <div class="brand-mark">C</div>
      <p class="eyebrow">{{ t('auth.setupEyebrow') }}</p>
      <h1>{{ t('auth.setupTitle') }}</h1>
      <p class="muted">{{ t('auth.setupDescription') }}</p>
      <form class="stack" @submit.prevent="completeSetup">
        <label>{{ t('auth.adminFirstName') }}<input v-model="setupFirstName" maxlength="80" required /></label>
        <label>{{ t('auth.adminLastName') }}<input v-model="setupLastName" maxlength="80" required /></label>
        <label>{{ t('auth.adminUsername') }}<input v-model="setupUsername" autocomplete="username" minlength="3" maxlength="64" required /></label>
        <PasswordInput v-model="setupPassword" :label="t('auth.passwordMinimum')" required />
        <label>{{ t('auth.repeatPassword') }}<input v-model="setupPasswordConfirm" type="password" autocomplete="new-password" minlength="8" maxlength="256" required /></label>
        <label>{{ t('auth.licenseToken') }}<input v-model="setupLicenseToken" type="password" autocomplete="off" maxlength="4096" required /></label>
        <label class="permission-toggle"><input v-model="setupSundayWorkAuthorized" type="checkbox" /> {{ t('auth.sundayAuthorization') }}</label>
        <p class="muted">{{ t('auth.sundayWarning') }}</p>
        <p class="muted">{{ t('auth.licenseDescription') }}</p>
        <button class="primary full" :disabled="busy">{{ busy ? t('auth.settingUp') : t('auth.createAdmin') }}</button>
      </form>
      <p v-if="error" class="error-message">{{ displayedError }}</p>
      <footer class="login-footer"><a :href="repositoryUrl" target="_blank" rel="noopener noreferrer">{{ t('common.github') }}</a> · <a :href="documentationUrl" target="_blank" rel="noopener noreferrer">{{ t('common.documentation') }}</a> · Version {{ displayVersion }}</footer>
    </section>
  </main>

  <main v-else-if="invitationToken && !authenticated" class="login-shell">
    <section class="login-card setup-card">
      <LanguageSelector />
      <div class="brand-mark">C</div>
      <p class="eyebrow">{{ t('auth.invitationEyebrow') }}</p>
      <h1>{{ t('auth.invitationTitle') }}</h1>
      <p class="muted">{{ t('auth.invitationDescription') }}</p>
      <form class="stack" @submit.prevent="acceptInvitation">
        <PasswordInput v-model="invitationPassword" :label="t('auth.newPassword')" required />
        <label>{{ t('auth.repeatPassword') }}<input v-model="invitationPasswordConfirm" type="password" autocomplete="new-password" minlength="8" maxlength="256" required /></label>
        <button class="primary full" :disabled="busy">{{ busy ? t('auth.savingPassword') : t('auth.setPassword') }}</button>
      </form>
      <p v-if="error" class="error-message">{{ displayedError }}</p>
      <footer class="login-footer"><a :href="repositoryUrl" target="_blank" rel="noopener noreferrer">{{ t('common.github') }}</a> · <a :href="documentationUrl" target="_blank" rel="noopener noreferrer">{{ t('common.documentation') }}</a> · Version {{ displayVersion }}</footer>
    </section>
  </main>

  <main v-else-if="!authenticated" class="login-shell">
    <section class="login-card">
      <LanguageSelector />
      <div class="brand-mark">C</div>
      <p class="eyebrow">{{ t('auth.loginEyebrow') }}</p>
      <p v-if="institutionName" class="institution-label">{{ t('auth.licensedTo') }} <strong>{{ institutionName }}</strong></p>
      <h1>{{ t('auth.welcome') }}</h1>
      <p class="muted">{{ t('auth.loginDescription') }}</p>
      <p v-if="invitationMessage" class="success-message" role="status">{{ t('auth.invitationAccepted') }}</p>
      <form class="stack" @submit.prevent="login">
        <label>{{ t('auth.username') }}<input v-model="loginUsername" autocomplete="username" required /></label>
        <label>{{ t('auth.password') }}<input v-model="password" type="password" autocomplete="current-password" required /></label>
        <label class="permission-toggle"><input v-model="staySignedIn" type="checkbox" /> {{ t('auth.rememberMe') }}</label>
        <p class="muted">{{ t('auth.adminRememberWarning') }}</p>
        <button class="primary full" :disabled="busy">{{ busy ? t('auth.signingIn') : t('auth.signIn') }}</button>
      </form>
      <p v-if="error" class="error-message">{{ displayedError }}</p>
      <footer class="login-footer"><a :href="repositoryUrl" target="_blank" rel="noopener noreferrer">{{ t('common.github') }}</a> · <a :href="documentationUrl" target="_blank" rel="noopener noreferrer">{{ t('common.documentation') }}</a> · Version {{ displayVersion }}</footer>
    </section>
  </main>

  <main v-else-if="mustChangePassword" class="login-shell">
    <section class="login-card">
      <LanguageSelector />
      <div class="brand-mark">C</div>
      <h1>{{ t('auth.requiredPasswordTitle') }}</h1>
      <p class="muted">{{ t('auth.requiredPasswordDescription') }}</p>
      <form class="stack" @submit.prevent="changeRequiredPassword">
        <label>{{ t('profile.currentPassword') }}<input v-model="requiredCurrentPassword" type="password" autocomplete="current-password" required /></label>
        <PasswordInput v-model="requiredPassword" :label="t('auth.newPassword')" required />
        <label>{{ t('auth.repeatPassword') }}<input v-model="requiredPasswordConfirm" type="password" autocomplete="new-password" minlength="8" maxlength="256" required /></label>
        <button class="primary full" :disabled="busy">{{ t('auth.setPassword') }}</button>
      </form>
      <p v-if="error" class="error-message">{{ displayedError }}</p>
      <button class="text-button" @click="logout">{{ t('nav.signOut') }}</button>
    </section>
  </main>

  <div v-else class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <aside class="sidebar">
      <a class="brand" href="#"><span class="brand-mark small">C</span><span class="brand-text">Clinic<span class="brand-light">Pulse</span></span></a>
      <button class="sidebar-toggle" type="button" :aria-label="sidebarCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')" :title="sidebarCollapsed ? t('nav.expand') : t('nav.collapse')" @click="toggleSidebar">{{ sidebarCollapsed ? '»' : '«' }}</button>
      <div v-if="hasScheduleAccess && canManage && roleKey !== 'PERSONNEL'" class="plan-nav-list">
        <p class="nav-caption">{{ t('nav.schedules') }}</p>
        <button v-if="canManage" class="nav-item plan-nav-item" :title="t('nav.allSchedules')" :class="{ active: selectedPlanId === null }" @click="selectPlan(null)"><span>▦</span> {{ t('nav.allSchedules') }}</button>
        <button v-for="department in departments" :key="department.id" class="nav-item plan-nav-item" :title="department.name" :class="{ active: selectedPlanId === department.id }" @click="selectPlan(department.id)"><span>▦</span><span class="plan-nav-name">{{ department.name }}</span></button>
      </div>
      <p class="nav-caption nav-caption-spaced">{{ t('nav.workspace') }}</p>
      <button v-if="hasScheduleAccess && roleKey !== 'PERSONNEL'" class="nav-item" :title="t('page.schedule')" :class="{ active: !showPlanning }" @click="showPlanning = false; showNotifications = false; showAbsences = false; showNextShifts = false; selectedDay = null"><span>▦</span> {{ t('page.schedule') }}</button>
      <button v-if="roleKey === 'EMPLOYEE'" class="nav-item" :title="t('schedule.nextShifts')" :class="{ active: showNextShifts }" @click="void openNextShifts()"><span>◷</span> {{ t('schedule.nextShifts') }}</button>
      <button v-if="canEditPlan" class="nav-item" :title="t('page.planning')" :class="{ active: showPlanning }" @click="openPlanning()"><span>✧</span> {{ t('page.planning') }}</button>
      <button v-if="canViewAbsences" class="nav-item" :title="t('page.absences')" @click="void openAbsences()"><span>☾</span> {{ t('page.absences') }}</button>
      <button v-if="canViewArchive" class="nav-item" :title="t('page.archive')" @click="void openArchive()"><span>▤</span> {{ t('page.archive') }}</button>
      <button v-if="hasScheduleAccess && roleKey !== 'PERSONNEL'" class="nav-item" :title="t('page.notifications')" :class="{ active: showNotifications }" @click="openNotificationsPage()"><span>♧</span> {{ t('page.notifications') }} <b v-if="notifications.length" class="nav-count">{{ notifications.length }}</b></button>
      <button v-if="canManageTeam" class="nav-item" :title="t('nav.teamManagement')" :class="{ active: showManagement }" @click="void openManagement()"><span>♙</span> {{ t('nav.teamManagement') }}</button>
      <div class="sidebar-bottom">
        <button class="profile profile-button" :title="t('nav.myProfile')" @click="void openProfile()">
          <img v-if="profile?.profile_image_data" class="avatar profile-avatar" :src="profile.profile_image_data" alt="" />
          <div v-else class="avatar">{{ username.slice(0, 1).toUpperCase() }}</div>
          <span class="profile-text"><strong>{{ username }}</strong><small>{{ roleLabel(roleKey) }} · {{ t('nav.myProfile') }}</small></span>
        </button>
        <p class="idle-hint" :class="{ warning: idleWarning }" role="status" :title="idleRemainingLabel">⏱ {{ idleRemainingLabel }}</p>
        <button class="logout" :title="t('nav.signOut')" @click="logout"><span class="logout-icon">⏻</span><span class="logout-text">{{ t('nav.signOut') }}</span></button>
      </div>
    </aside>

    <section class="workspace">
      <nav class="mobile-navigation" :aria-label="t('nav.mobileNavigation')">
        <button v-if="hasScheduleAccess && roleKey !== 'PERSONNEL'" @click="showPlanning = false; showNotifications = false; showAbsences = false; showNextShifts = false; selectedDay = null">{{ t('page.schedule') }}</button>
        <button v-if="roleKey === 'EMPLOYEE'" @click="void openNextShifts()">{{ t('schedule.nextShifts') }}</button>
        <button v-if="canEditPlan" @click="openPlanning()">{{ t('page.planning') }}</button>
        <button v-if="canViewAbsences" @click="void openAbsences()">{{ t('page.absences') }}</button>
        <button v-if="canViewArchive" @click="void openArchive()">{{ t('page.archive') }}</button>
        <button v-if="hasScheduleAccess && roleKey !== 'PERSONNEL'" @click="openNotificationsPage()">{{ t('page.notifications') }}</button>
        <button v-if="canManageTeam" @click="void openManagement()">{{ t('nav.teamManagement') }}</button>
        <button @click="logout()">{{ t('nav.signOut') }}</button>
      </nav>
      <header class="topbar">
        <div class="breadcrumb">{{ t('nav.workspaceLabel') }} <span>/</span> <strong>{{ selectedPlanName }}</strong><span>/</span>{{ selectedDay ? t('nav.dayView') : t('nav.weekView') }}</div>
        <div class="topbar-right">
          <LanguageSelector compact />
          <select v-if="hasScheduleAccess" class="mobile-plan-selector" :value="selectedPlanId ?? (canManage ? 'all' : (departments[0]?.id ?? 'all'))" :aria-label="t('nav.selectSchedule')" @change="selectPlan(($event.target as HTMLSelectElement).value === 'all' ? null : Number(($event.target as HTMLSelectElement).value))">
            <option v-if="canManage" value="all">{{ t('nav.allSchedules') }}</option>
            <option v-for="department in departments" :key="department.id" :value="department.id">{{ department.name }}</option>
          </select>
          <span class="status-dot"></span> {{ t('nav.connected') }}
          <div class="notification-wrap">
            <button v-if="hasScheduleAccess" class="icon-button notification-button" :aria-label="t('nav.openNotifications')" @click="openNotificationsPage()">♧<span v-if="notifications.length" class="notification-count">{{ notifications.length }}</span></button>
          </div>
          <button v-if="canManageTeam" class="secondary management-button" @click="void openManagement()">{{ t('nav.teamManagement') }}</button>
          <button class="icon-button" :aria-label="t('page.settings')" @click="openAppSettings()">⚙</button>
          <button class="profile-avatar-button" :aria-label="t('nav.openProfile')" @click="void openProfile()">
            <img v-if="profile?.profile_image_data" class="avatar profile-avatar" :src="profile.profile_image_data" alt="" />
            <span v-else class="avatar">{{ username.slice(0, 1).toUpperCase() }}</span>
          </button>
        </div>
      </header>
      <p v-if="locale === 'en'" class="language-banner" role="status">{{ t('language.incomplete') }}</p>
      <main v-if="showPlanning" class="content">
        <div class="page-heading">
          <div>
            <p class="eyebrow">{{ t('planning.eyebrow') }}</p>
            <h1>{{ t('planning.title') }}</h1>
            <p class="muted">{{ t('planning.description') }}</p>
          </div>
        </div>
        <div v-if="error" class="alert" role="alert"><span>{{ displayedError }}</span><button @click="error = ''" :aria-label="t('planning.closeAlert')">×</button></div>
        <p v-if="planningNotice" class="planning-notice" role="status">{{ t(planningNotice.key, { count: planningNotice.count }) }}</p>
        <section class="planning-controls">
          <label>{{ t('planning.period') }}
            <select v-model="planningMode">
              <option value="week">{{ t('planning.week') }}</option>
              <option value="month">{{ t('planning.month') }}</option>
            </select>
          </label>
          <label>{{ t('planning.date') }}
            <input v-model="planningAnchor" type="date" />
          </label>
          <p class="muted">{{ new Date(`${planningPeriod.start}T12:00:00`).toLocaleDateString(locale) }} – {{ new Date(`${planningPeriod.end}T12:00:00`).toLocaleDateString(locale) }} · {{ selectedPlanName }}</p>
          <button class="primary" :disabled="planningBusy || !shiftTypes.length" @click="void proposePlanning()">
            {{ planningBusy ? t('planning.calculating') : t('planning.propose') }}
          </button>
        </section>
        <section v-if="planningDays" class="optimization-panel smart-panel" aria-live="polite">
          <header class="smart-heading">
            <strong>{{ t('planning.summary', { suggestions: t(planningSuggestionCount === 1 ? 'planning.suggestionOne' : 'planning.suggestionOther', { count: planningSuggestionCount }), unfilled: t(planningUnfilledCount === 1 ? 'planning.unfilledOne' : 'planning.unfilledOther', { count: planningUnfilledCount }) }) }}</strong>
            <span>{{ t('planning.review') }}</span>
            <button class="primary approve-button" :disabled="planningBusy || !planningSuggestionCount" @click="void approvePlanning()">{{ t('planning.approve') }}</button>
          </header>
          <p v-if="planningLoad.length" class="muted">
            {{ t('planning.distribution') }} <span v-for="([name, count], index) in planningLoad" :key="name">{{ index ? ' · ' : '' }}{{ name }} {{ count }}</span>
          </p>
          <article v-for="day in planningDays.filter((entry) => entry.suggestions.length || entry.unfilled_slots.length)" :key="day.target_date" class="planning-day">
            <h3>{{ dateLabel(day.target_date) }}</h3>
            <p v-for="suggestion in day.suggestions" :key="`${suggestion.shift_type_id}-${suggestion.employee_id}`" class="planning-line">
              <strong>{{ suggestion.employee_name }}</strong> · {{ suggestion.shift_name }}
              <small>{{ timeLabel(suggestion.starts_at) }}–{{ timeLabel(suggestion.ends_at) }}{{ suggestion.role_match ? '' : t('planning.roleMismatch') }}</small>
            </p>
            <p v-for="(slot, index) in day.unfilled_slots" :key="`gap-${slot.shift_type_id}-${index}`" class="planning-line planning-gap">
              {{ t('planning.unfilled', { shift: slot.shift_name, position: slot.position }) }}
            </p>
          </article>
          <p v-if="!planningSuggestionCount && !planningUnfilledCount" class="muted">{{ t('planning.empty') }}</p>
        </section>
      </main>
      <main v-else-if="showAbsences" class="content">
        <div class="page-heading">
          <div>
            <p class="eyebrow">{{ t('absence.personnel') }}</p>
            <h1>{{ t('page.absences') }}</h1>
            <p class="muted">{{ t('absence.description') }}</p>
          </div>
        </div>
        <div class="absence-layout">
          <section v-if="canRequestAbsence || canRecordAbsence" class="panel absence-panel">
          <form class="stack absence-form" @submit.prevent="submitAbsence">
              <label v-if="!canRequestAbsence">{{ t('absence.employee') }}<select v-model="absenceEmployeeId" required><option v-for="employee in employees" :key="employee.id" :value="String(employee.id)">{{ employee.name }}</option></select></label>
              <label>{{ t('absence.kind') }}<select v-model="absenceKind"><option value="vacation">{{ t('absence.vacation') }}</option><option value="sick">{{ t('absence.sick') }}</option><option value="other">{{ t('absence.other') }}</option></select></label>
              <div class="form-row"><label>{{ t('absence.from') }}<input v-model="absenceStart" type="date" required /></label><label>{{ t('absence.to') }}<input v-model="absenceEnd" type="date" :min="absenceStart" required /></label></div>
              <label>{{ t('absence.optionalNote') }}<input v-model="absenceNote" maxlength="500" /></label>
              <p v-if="absenceKind === 'sick'" class="muted">{{ t('absence.sickNotice') }}</p>
            <button class="primary full">{{ canRequestAbsence && absenceKind !== 'sick' ? t('absence.submit') : absenceKind === 'sick' && canRequestAbsence ? t('absence.reportSick') : t('absence.record') }}</button>
            </form>
          </section>
          <section class="panel absence-panel absence-list">
          <div v-for="absence in absences" :key="absence.id" class="management-row absence-row">
            <div>
              <strong>{{ absence.employee_name }} · {{ kindLabels[absence.kind] }}</strong>
              <small>{{ dateLabel(absence.start_date) }} – {{ dateLabel(absence.end_date) }} · {{ absence.kind === 'sick' ? t('absence.noApproval') : statusLabels[absence.status] }}</small>
              <small v-if="absence.requested_by">{{ t(absence.kind === 'sick' ? 'absence.reportedBy' : 'absence.requestedBy', { name: absence.requested_by }) }}<span v-if="absence.created_at">{{ t('absence.onDate', { date: new Date(absence.created_at).toLocaleString(locale) }) }}</span></small>
              <small v-if="absence.kind !== 'sick' && absence.decided_by">{{ t(absence.status === 'rejected' ? 'absence.rejectedBy' : 'absence.approvedBy', { name: absence.decided_by }) }}<span v-if="absence.decided_at">{{ t('absence.onDate', { date: new Date(absence.decided_at).toLocaleString(locale) }) }}</span></small>
              <small v-if="absence.note">{{ t('absence.note', { note: absence.note }) }}</small>
            </div>
            <div v-if="!licenseReadOnly">
              <template v-if="absence.status === 'pending' && absence.kind !== 'sick' && roleKey === 'OBERARZT' && canApprove"><button class="text-button" @click="decideAbsence(absence, 'approved')">{{ t('absence.approve') }}</button><button class="text-button danger-text" @click="decideAbsence(absence, 'rejected')">{{ t('absence.reject') }}</button></template>
              <button v-if="(roleKey === 'EMPLOYEE' && absence.status === 'pending') || canRecordAbsence" class="text-button danger-text" @click="removeAbsence(absence)">{{ roleKey === 'EMPLOYEE' ? t('absence.withdraw') : t('absence.delete') }}</button>
            </div>
          </div>
          <p v-if="!absences.length" class="notification-empty">{{ t('absence.empty') }}</p>
          </section>
        </div>
      </main>
      <main v-else-if="showNotifications" class="content">
        <div class="page-heading">
          <div>
            <p class="eyebrow">{{ t('notifications.eyebrow') }}</p>
            <h1>{{ t('page.notifications') }}</h1>
            <p class="muted">{{ t(roleKey === 'EMPLOYEE' ? 'notifications.employeeDescription' : 'notifications.description') }}</p>
          </div>
          <label v-if="roleKey !== 'EMPLOYEE'" class="notification-range">{{ t('notifications.period') }}
            <select v-model.number="notificationDays" @change="void loadNotificationHistory()">
              <option v-for="days in [7, 14, 30, 90]" :key="days" :value="days">{{ t('notifications.lastDays', { count: days }) }}</option>
            </select>
          </label>
        </div>
        <section class="notification-page">
          <p v-if="notificationsLoading" class="notification-empty">{{ t('notifications.loading') }}</p>
          <template v-if="roleKey === 'EMPLOYEE'">
            <article v-for="absence in absences" :key="`absence-${absence.id}`" class="notification-item">
              <span class="notification-warning">{{ absence.kind === 'sick' ? 'i' : absence.status === 'approved' ? '✓' : absence.status === 'rejected' ? '×' : '…' }}</span>
              <span><strong>{{ t('notifications.absenceStatus', { kind: kindLabels[absence.kind], status: absence.kind === 'sick' ? t('notifications.sickReported') : statusLabels[absence.status] }) }}</strong><small>{{ dateLabel(absence.start_date) }} – {{ dateLabel(absence.end_date) }}</small></span>
            </article>
          </template>
          <button v-for="item in notificationHistory" :key="item.id" class="notification-item" @click="openNotification(item)">
            <span class="notification-warning">!</span><span><strong>{{ t(item.count === 1 ? 'notifications.gapOne' : 'notifications.gapOther', { count: item.count, position: item.position, shift: item.shiftName }) }}</strong><small>{{ dateLabel(item.date) }}</small></span>
          </button>
          <p v-if="!notificationsLoading && (roleKey === 'EMPLOYEE' ? !absences.length : !notificationHistory.length)" class="notification-empty">{{ t('notifications.empty') }}</p>
        </section>
      </main>
      <main v-else-if="showNextShifts" class="content">
        <div class="page-heading">
          <div><p class="eyebrow">{{ t('planning.eyebrow') }}</p><h1>{{ t('schedule.nextShifts') }}</h1><p class="muted">{{ t('schedule.nextShiftsDescription') }}</p></div>
        </div>
        <section class="panel next-shifts-list">
          <article v-for="assignment in nextAssignments" :key="assignment.id" class="management-row">
            <div><strong>{{ assignment.shift_name }}</strong><small>{{ dateLabel(localDate(new Date(assignment.starts_at))) }} · {{ timeLabel(assignment.starts_at) }}–{{ timeLabel(assignment.ends_at) }}</small></div>
          </article>
          <p v-if="!nextAssignments.length" class="notification-empty">{{ t('schedule.noNextShifts') }}</p>
        </section>
      </main>
      <main v-else-if="!hasScheduleAccess" class="content">
        <div class="page-heading">
          <div><p class="eyebrow">{{ t('management.title') }}</p><h1>{{ t('management.accessRestrictedTitle') }}</h1><p class="muted">{{ t('management.accessRestrictedDescription') }}</p></div>
          <button v-if="canManageTeam" class="primary" @click="void openManagement()">{{ t('nav.teamManagement') }}</button>
        </div>
      </main>
      <main v-else class="content">
        <div class="page-heading">
          <div>
            <p class="eyebrow">{{ t('schedule.eyebrow') }}</p>
            <h1>{{ selectedDay ? dateLabel(selectedDay) : t('page.schedule') }}</h1>
            <p class="muted">{{ selectedDay ? t('schedule.dayDescription') : t('schedule.weekDescription') }}</p>
          </div>
          <div class="heading-actions">
            <button v-if="selectedDay" class="secondary" @click="selectedDay = null; smartGap = null">{{ t('schedule.backToWeek') }}</button>
            <button v-if="canEditPlan" class="primary" :disabled="!employees.length || !shiftTypes.length" @click="selectedDate = selectedDay ?? localDate(today); selectedAssignmentPosition = ''; showAssignmentForm = true">{{ t('schedule.addAssignment') }}</button>
          </div>
        </div>

        <div v-if="error" class="alert" role="alert"><span>{{ displayedError }}</span><button @click="error = ''" :aria-label="t('planning.closeAlert')">×</button></div>
        <section
          v-if="roleKey === 'ADMIN' && licenseInfo && !licenseInfo.suppress_warnings && (licenseInfo.status !== 'PAID' || licenseInfo.read_only || licenseInfo.last_error)"
          class="license-banner"
          :class="{ 'license-blocked': licenseInfo.read_only || licenseInfo.status === 'BLOCKED' }"
          role="status"
        >
          <div>
            <strong v-if="licenseInfo.read_only || licenseInfo.status === 'BLOCKED'">{{ t('license.restricted') }}</strong>
            <strong v-else-if="licenseInfo.status === 'GRACE_PERIOD'">{{ t('license.renew') }}</strong>
            <strong v-else>{{ t('license.unavailable') }}</strong>
            <p>{{ apiErrorDetail(licenseInfo.message ?? licenseInfo.last_error) ?? t('license.status', { status: licenseInfo.status }) }}<span v-if="licenseInfo.grace_until">{{ t('license.graceUntil', { date: new Date(licenseInfo.grace_until).toLocaleString(locale) }) }}</span></p>
          </div>
          <button class="secondary" :disabled="licenseCheckBusy" @click="void checkLicenseNow()">{{ licenseCheckBusy ? t('license.checking') : t('license.checkNow') }}</button>
        </section>

        <template v-if="hasScheduleAccess">
        <section class="stats">
          <article class="stat-card"><span class="stat-icon teal">▦</span><div><span class="stat-label">{{ t('schedule.plannedShifts') }}</span><strong>{{ assignments.length }}</strong></div><small>{{ t('schedule.thisWeek') }}</small></article>
          <article class="stat-card"><span class="stat-icon blue">◷</span><div><span class="stat-label">{{ t('schedule.plannedHours') }}</span><strong>{{ totalHours.toLocaleString(locale, { maximumFractionDigits: 0 }) }}</strong></div><small>{{ t('schedule.thisWeek') }}</small></article>
          <article v-if="roleKey !== 'EMPLOYEE'" class="stat-card"><span class="stat-icon" :class="notifications.length ? 'amber' : 'teal'">!</span><div><span class="stat-label">{{ t('schedule.openPositions') }}</span><strong>{{ notifications.reduce((sum, item) => sum + item.count, 0) }}</strong></div><small>{{ t('schedule.thisWeek') }}</small></article>
        </section>

        <section v-if="!selectedDay" class="today-panel panel">
          <header class="today-heading">
            <div><p class="eyebrow">{{ t('schedule.today').toLocaleUpperCase(locale) }}</p><h2>{{ dateLabel(localDate(today)) }}</h2><p class="muted">{{ shiftCountLabel(dateAssignments(today).length) }}<template v-if="roleKey !== 'EMPLOYEE'"> · {{ openCountLabel(shiftTypes.reduce((sum, shift) => sum + openStaffingCount(localDate(today), shift), 0)) }}</template></p></div>
            <button class="secondary" @click="selectedDay = localDate(today)">{{ t('schedule.openDay') }}</button>
          </header>
          <div v-if="shiftTypes.length" class="today-shifts">
            <article v-for="shift in (roleKey === 'EMPLOYEE' ? shiftTypes.filter((item) => assignmentsFor(localDate(today), item.id).length) : shiftTypes)" :key="shift.id" class="today-shift">
              <span class="shift-color" :style="{ background: shift.color }"></span>
              <div><strong>{{ shift.name }}</strong><small>{{ shift.start_time.slice(0, 5) }}–{{ shift.end_time.slice(0, 5) }}<template v-if="roleKey !== 'EMPLOYEE'"> · {{ staffingSummary(shift) }}</template></small><p>{{ assignmentsFor(localDate(today), shift.id).map((item) => item.employee_name).join(', ') || t('schedule.noAssignments') }}</p></div>
              <span v-if="roleKey !== 'EMPLOYEE' && openStaffingCount(localDate(today), shift)" class="overview-gap">{{ t('schedule.openCount', { count: openStaffingCount(localDate(today), shift) }) }}</span>
              <span v-else-if="roleKey !== 'EMPLOYEE'" class="overview-filled">{{ t('schedule.filled') }}</span>
              <div v-if="canEditPlan" class="shift-actions">
                <button class="text-button" @click="editShift(shift)">{{ t('management.edit') }}</button>
                <button class="text-button danger-text" @click="void removeShift(shift)">{{ t('management.delete') }}</button>
              </div>
            </article>
          </div>
          <p v-else class="muted today-empty">{{ t('schedule.noShifts') }}</p>
        </section>

        <section class="panel">
          <div class="planner-toolbar">
            <div><h2>{{ selectedDay ? t('schedule.dayDetails') : t('schedule.weekOverview') }}</h2><p class="muted">{{ selectedDay ? dateLabel(selectedDay) : weekLabel }}</p></div>
            <div class="toolbar-actions">
              <template v-if="!selectedDay">
                <div class="week-nav"><button :aria-label="t('schedule.previousWeek')" @click="moveWeek(-1)">‹</button><button @click="weekOffset = 0; void loadData()">{{ t('schedule.today') }}</button><button :aria-label="t('schedule.nextWeek')" @click="moveWeek(1)">›</button></div>
                <button v-if="canManageStaff && !licenseReadOnly" class="secondary" @click="newEmployee()">{{ t('schedule.addEmployee') }}</button>
                <button v-if="canEditPlan" class="secondary" @click="startNewShift">{{ t('schedule.addShiftType') }}</button>
              </template>
              <template v-else>
                <button v-if="canEditPlan" class="secondary" :disabled="optimizationBusy" @click="void optimizeSelectedDay()">
                  {{ optimizationBusy ? t('planning.calculating') : t('schedule.optimize') }}
                </button>
                <button v-if="canManageStaff && !licenseReadOnly" class="secondary" @click="newEmployee()">{{ t('schedule.addEmployee') }}</button>
                <button v-if="canEditPlan" class="secondary" @click="startNewShift">{{ t('schedule.addShiftType') }}</button>
              </template>
            </div>
          </div>

          <div v-if="!employees.length || !shiftTypes.length" class="empty-state">
            <div class="empty-icon">▦</div><h3>{{ t('schedule.emptyTitle') }}</h3>
            <p>{{ t('schedule.emptyDescription') }}</p>
            <div class="empty-actions">
              <button v-if="canManageTeam" class="secondary" @click="void openManagement()">{{ t('schedule.openManagement') }}</button>
              <button v-if="canEditPlan" class="secondary" @click="startNewShift">{{ t('schedule.createShiftType') }}</button>
            </div>
          </div>

          <div v-else-if="!selectedDay" class="week-overview">
            <button v-for="day in days" :key="day.toISOString()" class="overview-day" :class="{ 'today-column': localDate(day) === localDate(today) }" @click="selectedDay = localDate(day)">
              <span class="overview-weekday">{{ day.toLocaleDateString(locale, { weekday: 'long' }) }}</span>
              <strong class="overview-date">{{ day.toLocaleDateString(locale, { day: '2-digit', month: 'short' }) }}</strong>
              <span class="overview-shifts">{{ shiftCountLabel(dateAssignments(day).length) }}</span>
              <span v-if="roleKey !== 'EMPLOYEE' && shiftTypes.reduce((sum, shift) => sum + openStaffingCount(localDate(day), shift), 0)" class="overview-gap">
                {{ t('schedule.openCount', { count: shiftTypes.reduce((sum, shift) => sum + openStaffingCount(localDate(day), shift), 0) }) }}
              </span>
              <span v-else-if="roleKey !== 'EMPLOYEE'" class="overview-filled">{{ t('schedule.fullyStaffed') }}</span>
              <span class="overview-link">{{ t('schedule.viewDay') }}</span>
            </button>
          </div>

          <div v-else class="day-detail">
            <section v-if="optimizationPreview" class="optimization-panel smart-panel" aria-live="polite">
              <header class="smart-heading">
                <strong>{{ t('schedule.optimizationTitle') }}</strong>
                <span>{{ t('schedule.optimizationDescription') }}</span>
                <button class="text-button" @click="optimizationPreview = null">{{ t('schedule.close') }}</button>
              </header>
              <p v-if="optimizationPreview.status === 'UNKNOWN'" class="muted">
                {{ t('schedule.optimizationUnknown') }}
              </p>
              <template v-else>
                <article v-for="suggestion in optimizationPreview.suggestions" :key="`${suggestion.shift_type_id}-${suggestion.employee_id}`" class="smart-candidate">
                  <span class="candidate-avatar"><img v-if="employeePhoto(suggestion.employee_id)" :src="employeePhoto(suggestion.employee_id) ?? undefined" alt="" /><template v-else>{{ initialsOf(suggestion.employee_name) }}</template></span>
                  <div>
                    <strong>{{ suggestion.employee_name }} · {{ suggestion.shift_name }}</strong>
                    <small>{{ suggestion.employee_role }} · {{ suggestion.role_match ? t('schedule.roleMatch') : t('schedule.roleMismatch') }}</small>
                  </div>
                  <button v-if="canEditPlan" class="primary approve-button" @click="applyOptimizationSuggestion(suggestion)">{{ t('schedule.accept') }}</button>
                </article>
                <p v-if="!optimizationPreview.suggestions.length && !optimizationPreview.unfilled_slots.length" class="muted">
                  {{ t('schedule.noOpenSlots') }}
                </p>
                <p v-if="optimizationPreview.unfilled_slots.length" class="muted">
                  {{ t(optimizationPreview.unfilled_slots.length === 1 ? 'schedule.unfilledOne' : 'schedule.unfilledOther', { count: optimizationPreview.unfilled_slots.length }) }}
                </p>
              </template>
            </section>
            <div v-for="shift in (roleKey === 'EMPLOYEE' ? shiftTypes.filter((item) => assignmentsFor(selectedDay!, item.id).length) : shiftTypes)" :key="shift.id" class="shift-section">
              <header class="shift-section-heading">
                <div class="shift-color" :style="{ background: shift.color }"></div>
                <div><h3>{{ shift.name }}</h3><p>{{ shift.start_time.slice(0, 5) }}–{{ shift.end_time.slice(0, 5) }}<template v-if="roleKey !== 'EMPLOYEE'"> · {{ staffingSummary(shift) }}</template></p></div>
                <span v-if="roleKey !== 'EMPLOYEE'" class="coverage-count">{{ assignmentsFor(selectedDay, shift.id).length }}/{{ shift.required_staff }}</span>
                <button v-if="canEditPlan" class="text-button" @click="editShift(shift)">{{ t('management.edit') }}</button>
                <button v-if="canEditPlan" class="text-button danger-text" @click="void removeShift(shift)">{{ t('management.delete') }}</button>
                <button v-if="canEditPlan" class="secondary smart-button" @click="suggestFor(selectedDay, shift)">{{ t('schedule.smartSelection') }}</button>
              </header>
              <div class="position-slots">
                <article v-for="(assignment, index) in assignmentsFor(selectedDay, shift.id)" :key="assignment.id" class="position-slot filled-slot">
                  <span class="slot-index">{{ index + 1 }}</span>
                  <div class="slot-person"><span class="candidate-avatar"><img v-if="employeePhoto(assignment.employee_id)" :src="employeePhoto(assignment.employee_id) ?? undefined" alt="" /><template v-else>{{ initialsOf(assignment.employee_name) }}</template></span><div class="slot-employee"><strong>{{ assignment.employee_name }}</strong><small>{{ catalogFunctionLabel(assignmentPosition(assignment, shift)) }} · {{ timeLabel(assignment.starts_at) }}–{{ timeLabel(assignment.ends_at) }}</small></div></div>
                  <button v-if="canEditPlan" class="remove-assignment" :aria-label="t('schedule.removeAssignment', { name: assignment.employee_name })" @click="removeAssignment(assignment.id)">×</button>
                </article>
                <article
                  v-for="(position, slot) in openPositionsFor(selectedDay, shift)"
                  :key="`gap-${shift.id}-${slot}`"
                  class="position-slot vacancy-slot"
                  :class="{ droppable: canEditPlan }"
                  @dragover.prevent
                  @drop.prevent="canEditPlan && dropEmployee($event, selectedDay!, shift)"
                  @click="canEditPlan && (selectedDate = selectedDay!); canEditPlan && (selectedShift = String(shift.id)); canEditPlan && (selectedAssignmentPosition = position); canEditPlan && (showAssignmentForm = true)"
                >
                  <span class="slot-index">{{ assignmentsFor(selectedDay, shift.id).length + slot }}</span>
                  <div class="slot-employee"><strong>{{ t('schedule.openPosition') }}</strong><small>{{ catalogFunctionLabel(position) }} · {{ shift.start_time.slice(0, 5) }}–{{ shift.end_time.slice(0, 5) }}</small></div>
                  <span class="drag-hint">{{ t('schedule.dropOrSelect') }}</span>
                </article>
                <div v-if="smartGap?.date === selectedDay && smartGap.shift.id === shift.id" class="smart-panel">
                  <div class="smart-heading"><strong>{{ t('schedule.smartTitle') }}</strong><span>{{ t('schedule.smartDescription') }}</span></div>
                  <article v-if="smartCandidates[0]" class="smart-candidate">
                    <span class="candidate-avatar"><img v-if="employeePhoto(smartCandidates[0].employee_id)" :src="employeePhoto(smartCandidates[0].employee_id) ?? undefined" alt="" /><template v-else>{{ initialsOf(smartCandidates[0].employee_name) }}</template></span>
                    <div><strong>{{ smartCandidates[0].employee_name }}</strong><small>{{ smartCandidates[0].role }} · {{ smartCandidates[0].role_match ? t('schedule.roleMatch') : t('schedule.otherRole') }} · {{ t(smartCandidates[0].planned_assignments === 1 ? 'schedule.plannedOne' : 'schedule.plannedOther', { count: smartCandidates[0].planned_assignments }) }}</small></div>
                    <button v-if="canApprove && !licenseReadOnly" class="primary approve-button" @click="approveCandidate(smartCandidates[0])">{{ t('schedule.approve') }}</button>
                    <span v-else class="approval-needed">{{ licenseReadOnly ? t('schedule.licenseBlocked') : t('schedule.approvalRequired') }}</span>
                  </article>
                  <p v-else class="muted">{{ t('schedule.noCandidate') }}</p>
                  <button v-if="smartCandidates.length > 1" class="text-button" @click="smartCandidates.shift()">{{ t('schedule.otherCandidate') }}</button>
                </div>
              </div>
            </div>
            <aside v-if="canEditPlan" class="team-roster"><strong>{{ t('schedule.roster') }}</strong><div><button v-for="employee in employees" :key="employee.id" class="roster-person" draggable="true" @dragstart="dragEmployee($event, employee)"><span class="candidate-avatar"><img v-if="employeePhoto(employee.id)" :src="employeePhoto(employee.id) ?? undefined" alt="" /><template v-else>{{ initialsOf(employee.name) }}</template></span><span><b>{{ employee.name }}</b><small>{{ employee.role }}</small></span><span class="drag-grip">⠿</span></button></div></aside>
            <p v-if="!shiftTypes.length" class="empty-state">{{ t('schedule.noDayShiftTypes') }}</p>
          </div>
          <div v-if="busy" class="loading">{{ t('schedule.loading') }}</div>
        </section>

        </template>
        <section v-else class="panel restricted-panel"><h2>{{ t('schedule.noAccess') }}</h2><p>{{ t('schedule.noAccessDescription') }}</p></section>
      </main>
      <footer v-if="hasScheduleAccess || roleKey === 'ADMIN'" class="page-footer">
        <span>ClinicPulse · Version {{ displayVersion }}</span>
        <span>·</span>
        <a :href="repositoryUrl" target="_blank" rel="noopener noreferrer">{{ t('common.github') }}</a>
        <span>·</span>
        <a :href="documentationUrl" target="_blank" rel="noopener noreferrer">{{ t('common.documentation') }}</a>
        <template v-if="roleKey === 'ADMIN'">
          <span>·</span>
          <button class="footer-update-button" :disabled="updateCheckBusy" @click="void checkForUpdates(true)">
            {{ updateCheckBusy ? t('updates.checking') : t('updates.check') }}
          </button>
          <label class="update-channel-control">{{ t('updates.channel') }}
            <select v-model="updateChannel" :aria-label="t('updates.channelLabel')" @change="changeUpdateChannel">
              <option value="main">Main</option>
              <option value="test">Test</option>
            </select>
          </label>
          <span>·</span>
          <span v-if="updateInfo" class="update-channel-label">{{ updateInfo.channel }}</span>
          <span v-if="updateInfo" class="update-status" :class="`update-${updateInfo.status}`" role="status">
            <template v-if="updateInfo.update_available">
              <a :href="updateInfo.release_url ?? repositoryUrl" target="_blank" rel="noopener noreferrer">{{ t('updates.available', { version: updateInfo.latest_version ?? '' }) }}</a>
            </template>
            <template v-else>{{ apiErrorDetail(updateInfo.message) }}</template>
          </span>
        </template>
      </footer>
    </section>

    <div v-if="authenticated && error" class="toast toast-error" role="alert">
      <span>{{ displayedError }}</span><button type="button" :aria-label="t('planning.closeAlert')" @click="error = ''">×</button>
    </div>
    <div v-if="confirmDialog" class="modal-backdrop confirm-backdrop" @click.self="answerConfirmation(false)" @keydown.esc="answerConfirmation(false)">
      <section class="modal confirm-modal" role="alertdialog" aria-modal="true" :aria-label="t('management.confirmation')">
        <p>{{ confirmDialog.message }}</p>
        <div class="form-row"><button class="secondary" autofocus @click="answerConfirmation(false)">{{ t('management.cancel') }}</button><button class="primary danger-action" @click="answerConfirmation(true)">{{ confirmDialog.confirmLabel }}</button></div>
      </section>
    </div>
    <div v-if="showEmployeeForm || showShiftForm || showAssignmentForm || showSettings || showManagement || showProfile || showArchive" class="modal-backdrop" @click.self="showEmployeeForm = false; showShiftForm = false; showAssignmentForm = false; showSettings = false; showManagement = false; showProfile = false; showArchive = false">
      <section class="modal" :class="{ 'modal-wide': showSettings && !showProfile && !showEmployeeForm && !showShiftForm && !showAssignmentForm && !showManagement }" role="dialog" aria-modal="true">
        <button class="modal-close" :aria-label="t('form.close')" @click="showEmployeeForm = false; showShiftForm = false; showAssignmentForm = false; showSettings = false; showManagement = false; showProfile = false; showArchive = false">×</button>
        <template v-if="showArchive">
          <p class="eyebrow">{{ t('archive.eyebrow') }}</p><h2>{{ t('archive.title') }}</h2>
          <p class="muted">{{ t('archive.description') }}</p>
          <form v-if="canEditPlan" class="stack" @submit.prevent="createArchive">
            <label>{{ t('form.department') }}<select v-model="archiveDepartmentId" required><option v-for="department in departments" :key="department.id" :value="String(department.id)">{{ department.name }}</option></select></label>
            <div class="form-row"><label>{{ t('absence.from') }}<input v-model="archiveStart" type="date" required /></label><label>{{ t('absence.to') }}<input v-model="archiveEnd" type="date" :min="archiveStart" required /></label></div>
            <label>{{ t('absence.optionalNote') }}<input v-model="archiveNote" maxlength="200" /></label>
            <button class="primary full">{{ t('archive.create') }}</button>
          </form>
          <div v-for="archive in planArchives" :key="archive.id" class="management-row">
            <div><strong>{{ archive.department_name }} · {{ dateLabel(archive.start_date) }} – {{ dateLabel(archive.end_date) }}</strong><small>{{ t(archive.entry_count === 1 ? 'archive.entryOne' : 'archive.entryOther', { count: archive.entry_count, date: new Date(archive.created_at).toLocaleString(locale), user: archive.created_by }) }}<span v-if="archive.note"> · {{ archive.note }}</span></small></div>
            <div><a class="text-button" :href="`/api/archives/${archive.id}/pdf`" download>PDF</a></div>
          </div>
          <p v-if="!planArchives.length" class="notification-empty">{{ t('archive.empty') }}</p>
        </template>
        <template v-else-if="showProfile">
          <p class="eyebrow">{{ t('profile.eyebrow') }}</p><h2>{{ t('profile.title') }}</h2>
          <div class="profile-editor">
            <img v-if="profileImageData" class="profile-editor-image" :src="profileImageData" :alt="t('profile.imagePreview')" />
            <div v-else class="profile-editor-placeholder">{{ username.slice(0, 1).toUpperCase() }}</div>
            <strong>{{ username }}</strong><span class="muted">{{ roleLabel(roleKey) }}</span>
          </div>
          <form class="stack" @submit.prevent="saveProfile">
            <label>{{ t('form.firstName') }}<input v-model="profileFirstName" maxlength="80" required /></label>
            <label>{{ t('form.lastName') }}<input v-model="profileLastName" maxlength="80" required /></label>
            <template v-if="roleKey !== 'ADMIN'">
              <label>{{ t('management.birthDate') }}<input v-model="profileBirthDate" type="date" /></label>
              <label>{{ t('management.address') }}<input v-model="profileAddress" maxlength="300" autocomplete="street-address" /></label>
              <label>{{ t('management.phone') }}<input v-model="profilePhone" type="tel" maxlength="50" /></label>
            </template>
            <label>{{ t('profile.image') }}<input type="file" accept="image/png,image/jpeg,image/webp" @change="selectProfileImage" /></label>
            <button v-if="profileImageData" type="button" class="text-button danger-text" @click="profileImageData = null">{{ t('profile.removeImage') }}</button>
            <label>{{ t('profile.visibility') }}<select v-model="profilePhotoVisibility" :disabled="roleKey === 'ADMIN' || departmentId === null"><option value="private">{{ t('profile.private') }}</option><option value="department">{{ t('profile.department') }}</option></select></label>
            <p class="muted">{{ t('profile.visibilityDescription') }}</p>
            <button class="primary full">{{ t('profile.save') }}</button>
          </form>
          <form class="stack account-settings-form" @submit.prevent="saveSettings">
            <strong>{{ t('profile.accountSettings') }}</strong>
            <label>{{ t('auth.username') }}<input v-model="changedUsername" autocomplete="username" minlength="3" maxlength="64" required /></label>
            <PasswordInput v-model="newPassword" :label="t('auth.newPassword')" optional />
            <label>{{ t('profile.currentPassword') }}<input v-model="currentPassword" type="password" autocomplete="current-password" required /></label>
            <button class="secondary full">{{ t('profile.saveAccount') }}</button>
            <p class="settings-note">{{ t('profile.tokenNotice') }}</p>
          </form>
          <section v-if="teamProfiles.length" class="team-profiles">
            <h3>{{ t('profile.teamProfiles') }}</h3>
            <article v-for="teammate in teamProfiles" :key="teammate.username" class="team-profile-card">
              <img v-if="teammate.profile_image_data" :src="teammate.profile_image_data" alt="" />
              <span v-else class="avatar">{{ teammate.username.slice(0, 1).toUpperCase() }}</span>
              <span><strong>{{ teammate.username }}</strong><small>{{ roleLabel(teammate.role_key) }}</small></span>
            </article>
          </section>
        </template>
        <template v-else-if="showEmployeeForm">
          <p class="eyebrow">{{ t('form.teamManagement') }}</p><h2>{{ employeeId ? t('form.editEmployee') : t('form.createEmployee') }}</h2>
          <form class="stack" @submit.prevent="submitEmployee">
            <label>{{ t('form.firstName') }}<input v-model="employeeFirstName" maxlength="80" required autofocus /></label>
            <label>{{ t('form.lastName') }}<input v-model="employeeLastName" maxlength="80" required /></label>
            <label>{{ t('form.scheduleRole') }}<select v-model="employeeRole"><option v-for="fn in roleCatalog.functions" :key="fn" :value="fn">{{ catalogFunctionLabel(fn) }}</option><option value="Individuell">{{ t('form.custom') }}</option></select></label>
            <label v-if="employeeRole === 'Individuell'">{{ t('form.customRole') }}<input v-model="employeeCustomRole" maxlength="80" required /></label>
            <label>{{ t('form.department') }}<select v-model="employeeDepartmentId" required><option v-for="department in departments" :key="department.id" :value="String(department.id)">{{ department.name }}</option></select></label>
            <label v-if="!employeeId" class="permission-toggle"><input v-model="employeeCreateAccount" type="checkbox" /> {{ t('form.createAccess') }}</label>
            <template v-if="employeeCreateAccount && !employeeId">
              <label>{{ t('auth.username') }}<input v-model="employeeLoginUsername" minlength="3" maxlength="64" required /></label>
              <template v-if="mailEnabled">
                <label>{{ t('form.invitationEmail') }}<input v-model="employeeEmail" type="email" maxlength="254" autocomplete="email" required /></label>
                <p class="muted">{{ t('form.invitationExplanation') }}</p>
              </template>
              <template v-else>
                <PasswordInput v-model="employeePassword" :label="t('management.temporaryPassword')" required />
                <p class="muted">{{ t('management.temporaryPasswordNotice') }}</p>
              </template>
            </template>
            <button class="primary full">{{ employeeId ? t('form.saveChanges') : t('form.createEmployee') }}</button>
          </form>
        </template>
        <template v-else-if="showShiftForm">
          <p class="eyebrow">{{ t('form.shiftManagement') }}</p><h2>{{ t(editingShiftId === null ? 'form.createShiftType' : 'form.editShiftType') }}</h2>
          <form class="stack" @submit.prevent="submitShift">
            <label>{{ t('form.name') }}<input v-model="shiftName" maxlength="80" :placeholder="t('form.shiftExample')" required autofocus /></label>
            <fieldset class="staffing-requirements">
              <legend>{{ t('form.staffingRequirements') }}</legend>
              <div v-for="(requirement, index) in shiftRequirements" :key="index" class="staffing-requirement">
                <label>{{ t('form.requiredPosition') }}<input v-model="requirement.position" maxlength="80" :placeholder="t('form.positionExample')" required /></label>
                <label>{{ t('form.requiredEmployees') }}<input v-model.number="requirement.required_staff" type="number" min="1" max="100" required /></label>
                <button type="button" class="text-button danger-text" :aria-label="t('form.removeRequirement')" :disabled="shiftRequirements.length === 1" @click="removeShiftRequirement(index)">×</button>
              </div>
              <button type="button" class="text-button" @click="addShiftRequirement">{{ t('form.addRequirement') }}</button>
            </fieldset>
            <div class="form-row"><label>{{ t('form.start') }}<input v-model="shiftStart" type="time" required /></label><label>{{ t('form.end') }}<input v-model="shiftEnd" type="time" required /></label></div>
            <label>{{ t('form.breakMinutes') }}<input v-model.number="shiftBreak" type="number" min="0" max="240" :placeholder="t('form.automatic')" /></label>
            <label>{{ t('form.breakStart') }}<input v-model.number="shiftBreakStart" type="number" min="0" max="360" :placeholder="t('form.automatic')" /></label>
            <button class="primary full">{{ t(editingShiftId === null ? 'form.saveShiftType' : 'form.saveChanges') }}</button>
          </form>
        </template>
        <template v-else-if="showAssignmentForm">
          <p class="eyebrow">{{ t('planning.eyebrow') }}</p><h2>{{ t('form.addAssignment') }}</h2>
          <form class="stack" @submit.prevent="submitAssignment">
            <label>{{ t('form.employee') }}<select v-model="selectedEmployee" required><option v-for="employee in assignableEmployees" :key="employee.id" :value="String(employee.id)">{{ employee.name }} · {{ employee.role }}</option></select></label>
            <label>{{ t('form.shiftType') }}<select v-model="selectedShift" required><option v-for="shift in shiftTypes" :key="shift.id" :value="String(shift.id)">{{ shift.name }} · {{ staffingSummary(shift) }} ({{ shift.start_time.slice(0, 5) }}–{{ shift.end_time.slice(0, 5) }})</option></select></label>
            <label>{{ t('form.date') }}<input v-model="selectedDate" type="date" required /></label>
            <p v-if="!assignableEmployees.length" class="muted">{{ t('form.noQualifiedEmployees') }}</p>
            <button class="primary full" :disabled="!assignableEmployees.length">{{ t('form.saveAssignment') }}</button>
          </form>
        </template>
        <template v-else-if="showManagement">
          <p class="eyebrow">{{ t('form.teamManagement') }}</p><h2>{{ t('management.title') }}</h2>
          <section v-if="canManageTeam" class="management-section">
            <p v-if="teamNotice" class="success-message" role="status">{{ t(teamNotice.key, teamNotice.values) }}</p>
            <section v-if="!departments.length && roleKey !== 'PERSONNEL'" class="empty-state">
              <h3>{{ t('management.setupTitle') }}</h3>
              <p>{{ t('management.setupDescription') }}</p>
            </section>
            <section v-if="showMailOnboarding" class="settings-section">
              <h3>{{ t('management.mailTitle') }}</h3>
              <p class="muted">{{ t('management.mailDescription') }}</p>
              <div class="form-row">
                <button class="primary" @click="skipMailOnboarding(); openAppSettings('mail')">{{ t('management.configureMail') }}</button>
                <button class="secondary" @click="skipMailOnboarding()">{{ t('management.skip') }}</button>
              </div>
            </section>
            <p v-if="licenseReadOnly" class="muted">{{ t('management.licenseBlocked') }}</p>
            <form v-if="(canManage || editingDepartmentId !== null) && !licenseReadOnly" class="inline-form" @submit.prevent="saveDepartment">
              <input v-model="departmentName" maxlength="100" :placeholder="t('management.departmentName')" required />
              <button class="secondary">{{ editingDepartmentId ? t('management.saveChange') : t('management.createDepartment') }}</button>
              <button v-if="editingDepartmentId" type="button" class="text-button" @click="editingDepartmentId = null; departmentName = ''">{{ t('management.cancel') }}</button>
            </form>
            <template v-if="canManage || canManageDepartment">
              <div v-for="department in departments" :key="department.id" class="management-row">
                <strong>{{ department.name }}</strong><div v-if="!licenseReadOnly"><label v-if="roleKey === 'ADMIN'">{{ t('management.departmentLead') }}<select :value="department.manager_user_id ?? ''" @change="void setDepartmentLeader(department, ($event.target as HTMLSelectElement).value)"><option value="">{{ t('management.noDepartmentLead') }}</option><option v-for="user in users.filter((item) => item.role_key === 'OBERARZT' && (item.department_ids ?? []).includes(department.id))" :key="user.id" :value="user.id">{{ user.first_name }} {{ user.last_name }} · {{ user.username }}</option></select></label><button class="text-button" @click="editDepartment(department)">{{ t('management.edit') }}</button><button class="text-button danger-text" @click="removeDepartment(department)">{{ t('management.delete') }}</button></div>
              </div>
            </template>
            <section v-if="canManageStaff">
              <h3>{{ t('management.employees') }}</h3>
              <button v-if="!licenseReadOnly" class="secondary" @click="newEmployee()">{{ t('schedule.addEmployee') }}</button>
              <div v-for="employee in allEmployees" :key="employee.id" class="management-row">
                <div><strong>{{ employee.name }}</strong><small>{{ employee.role }} · {{ departments.find((item) => item.id === employee.department_id)?.name ?? t('management.noDepartment') }}</small></div>
                <button v-if="!licenseReadOnly" class="text-button" @click="editEmployee(employee)">{{ t('management.edit') }}</button>
              </div>
            </section>
            <h3>{{ t('management.accounts') }}</h3>
            <form v-if="!licenseReadOnly" class="stack user-form" @submit.prevent="saveUser">
              <strong>{{ userId ? t('management.editAccount') : t('management.createAccount') }}</strong>
              <label>{{ t('form.firstName') }}<input v-model="userFirstName" maxlength="80" required /></label>
              <label>{{ t('form.lastName') }}<input v-model="userLastName" maxlength="80" required /></label>
              <label>{{ t('auth.username') }}<input v-model="userName" minlength="3" maxlength="64" required /></label>
              <details class="optional-details"><summary>{{ t('management.optionalDetails') }}</summary>
                <label>{{ t('management.birthDate') }}<input v-model="userBirthDate" type="date" /></label>
                <label>{{ t('management.address') }}<input v-model="userAddress" maxlength="300" autocomplete="street-address" /></label>
                <label>{{ t('management.phone') }}<input v-model="userPhone" type="tel" maxlength="50" /></label>
              </details>
              <label v-if="mailEnabled || userId">{{ t('management.passwordEmail') }}<input v-model="userEmail" type="email" maxlength="254" :required="mailEnabled && !userId && !userPassword" /></label>
              <PasswordInput v-model="userPassword" :label="userId ? t('management.newPassword') : mailEnabled ? t('management.initialPassword') : t('management.temporaryPassword')" :optional="!!userId || mailEnabled" :required="!userId && !mailEnabled" />
              <p v-if="mailEnabled && userEmail && !userId" class="muted">{{ t('management.invitationNotice') }}</p>
              <p v-if="!mailEnabled" class="muted">{{ t('management.temporaryPasswordNotice') }}</p>
              <label>{{ t('management.systemRole') }}<select v-model="userRoleKey"><option v-if="systemRoleSelectable('ADMIN')" value="ADMIN">{{ t('role.admin') }}</option><template v-for="option in roleCatalog.access_roles" :key="option.key"><option v-if="systemRoleSelectable(option.key)" :value="option.key">{{ option.key === 'KIOSK' ? t('role.kioskDescription') : option.key === 'EMPLOYEE' ? t('role.employeeDescription') : roleLabel(option.key) }}</option></template></select></label>
              <fieldset v-if="!['ADMIN', 'HOSPITAL_MANAGEMENT', 'PERSONNEL'].includes(userRoleKey)" class="department-picker"><legend>{{ t('management.accessibleSchedules') }}</legend><label v-for="department in departments" :key="department.id"><input v-model="userDepartmentIds" type="checkbox" :value="department.id" />{{ department.name }}</label></fieldset>
              <label v-if="userRoleKey === 'EMPLOYEE'">{{ t('management.linkedPerson') }}<select v-model="userEmployeeId" required><option :value="null" disabled>{{ t('management.choose') }}</option><option v-for="person in allEmployees.filter((item) => userDepartmentIds.includes(item.department_id ?? -1))" :key="person.id" :value="person.id">{{ person.name }} · {{ person.role }}</option></select></label>
              <template v-if="userRoleKey !== 'PERSONNEL'">
                <label class="permission-toggle"><input v-model="userCanView" type="checkbox" :disabled="userRoleKey === 'KIOSK' || userRoleKey === 'EMPLOYEE'" /> {{ t('management.viewSchedule') }}</label>
                <label class="permission-toggle"><input v-model="userCanEdit" type="checkbox" :disabled="userRoleKey === 'HOSPITAL_MANAGEMENT' || userRoleKey === 'CHEFARZT' || userRoleKey === 'KIOSK' || userRoleKey === 'EMPLOYEE'" /> {{ t('management.editShifts') }} <span class="permission-note">{{ t('management.seniorOnly') }}</span></label>
                <label class="permission-toggle"><input v-model="userCanApprove" type="checkbox" :disabled="userRoleKey === 'HOSPITAL_MANAGEMENT' || userRoleKey === 'CHEFARZT' || userRoleKey === 'KIOSK' || userRoleKey === 'EMPLOYEE'" /> {{ t('management.approveSuggestions') }} <span class="permission-note">{{ t('management.seniorOnly') }}</span></label>
              </template>
              <div class="form-row"><button class="primary">{{ userId ? t('management.saveAccount') : t('management.createAccount') }}</button><button v-if="userId" type="button" class="secondary" @click="resetUserForm">{{ t('management.cancel') }}</button></div>
            </form>
            <div v-for="user in users" :key="user.id" class="management-row account-row">
              <div><strong>{{ user.username }}</strong><small>{{ roleLabel(user.role_key) }} · {{ user.email || t('management.noEmail') }} · {{ user.invitation_status === 'pending' ? t('management.invitationPending') : user.invitation_status === 'delivery_failed' ? t('management.invitationFailed') : user.invitation_status === 'revoked' ? t('management.invitationRevoked') : user.is_locked ? t('management.locked') : t('management.active') }} · {{ user.department_ids?.map((id) => departments.find((item) => item.id === id)?.name).filter(Boolean).join(', ') || t('management.allDepartments') }}</small></div>
              <div><button class="text-button" @click="editUser(user)">{{ t('management.edit') }}</button><button v-if="mailEnabled && ['pending', 'delivery_failed', 'revoked'].includes(user.invitation_status ?? '') && !licenseReadOnly" class="text-button" @click="void resendInvitation(user)">{{ t('management.resendInvitation') }}</button><button v-if="['pending', 'delivery_failed'].includes(user.invitation_status ?? '') && !licenseReadOnly" class="text-button danger-text" @click="void revokeInvitation(user)">{{ t('management.revoke') }}</button><button v-else-if="user.invitation_status !== 'pending' && user.invitation_status !== 'delivery_failed' && user.invitation_status !== 'revoked'" class="text-button" @click="toggleUserLock(user)">{{ user.is_locked ? t('management.unlock') : t('management.lock') }}</button><button class="text-button danger-text" @click="removeUser(user)">{{ t('management.delete') }}</button></div>
            </div>
          </section>
        </template>
        <template v-else-if="showSettings">
          <p class="eyebrow">{{ t('settings.eyebrow') }}</p><h2>{{ t('page.settings') }}</h2>
          <nav class="settings-tabs" role="tablist">
            <button v-for="tab in settingsTabs" :key="tab.key" role="tab" type="button" :aria-selected="settingsTab === tab.key" :class="{ active: settingsTab === tab.key }" @click="settingsTab = tab.key">{{ tab.label }}</button>
          </nav>
          <section v-show="settingsTab === 'appearance'" class="settings-section"><strong>{{ t('settings.appearance') }}</strong><p class="muted">{{ t('settings.appearanceDescription') }}</p><div class="theme-options"><button :class="{ selected: theme === 'light' }" @click="applyTheme('light')">{{ t('settings.light') }}</button><button :class="{ selected: theme === 'dark' }" @click="applyTheme('dark')">{{ t('settings.dark') }}</button></div></section>
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'operations'" class="settings-section">
            <h3>{{ t('operations.title') }}</h3>
            <p class="muted">{{ t('operations.description') }}</p>
            <form class="stack" @submit.prevent="saveBusinessConfiguration">
              <label>{{ t('operations.state') }}<select v-model="businessConfiguration.federal_state" :disabled="businessConfiguration.federal_state_managed" required><option v-for="state in federalStates" :key="state" :value="state">{{ state }}</option></select></label>
              <label>{{ t('operations.facilityType') }}<select v-model="businessConfiguration.operational_profile" :disabled="businessConfiguration.operational_profile_managed" required><option v-for="profileOption in operationalProfiles" :key="profileOption.value" :value="profileOption.value">{{ t(profileOption.label) }}</option></select></label>
              <label class="permission-toggle"><input v-model="businessConfiguration.sunday_work_authorized" type="checkbox" /> {{ t('operations.sunday') }}</label>
              <p class="muted">{{ t('operations.timezone', { timezone: businessConfiguration.timezone }) }}</p>
              <div class="form-row"><button class="secondary">{{ t('operations.save') }}</button><span v-if="businessConfigurationMessage" class="muted">{{ t('settings.saved') }}</span></div>
            </form>
          </section>
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'operations'" class="settings-section">
            <h3>{{ t('operations.rulesTitle') }}</h3>
            <p class="muted">{{ t('operations.rulesDescription') }}</p>
            <form class="stack" @submit.prevent="saveWorkRules">
              <label>{{ t('operations.rest') }}<input v-model.number="workRules.rest_hours" type="number" min="11" max="24" required /></label>
              <label>{{ t('operations.daily') }}<input v-model.number="workRules.max_daily_hours" type="number" min="1" max="10" required /></label>
              <label>{{ t('operations.weekly') }}<input v-model.number="workRules.max_weekly_hours" type="number" min="1" max="48" required /></label>
              <div class="form-row"><button class="secondary">{{ t('operations.saveRules') }}</button><span v-if="workRulesMessage" class="muted">{{ t('settings.saved') }}</span></div>
            </form>
          </section>
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'mail'" class="settings-section">
            <h3>{{ t('mail.title') }}</h3>
            <p class="muted">{{ t('mail.description') }}</p>
            <form class="stack" @submit.prevent="void saveMailMode()">
              <label class="permission-toggle"><input v-model="mailModeDraft" type="checkbox" @change="mailModeSaved = false" /> {{ t('mail.enableDelivery') }}</label>
              <p class="muted">{{ t('mail.disabledDescription') }}</p>
              <div class="form-row"><button class="secondary">{{ t('mail.saveMode') }}</button><span v-if="mailModeSaved" class="muted">{{ t('settings.saved') }}</span></div>
            </form>
            <p v-if="mailSettingsLoaded" class="muted">SMTP: <strong>{{ mailSettings.smtp_host ? t('mail.configured') : t('mail.notConfigured') }}</strong> · {{ t('mail.password') }}: <strong>{{ mailSettings.smtp_password_configured ? t('mail.saved') : t('mail.notSaved') }}</strong></p>
            <form v-if="mailEnabled" class="stack" @submit.prevent="void saveMailSettings()">
              <label>{{ t('mail.publicUrl') }}<input v-model="mailSettings.public_url" type="url" placeholder="https://dienstplan.klinik.example" required /></label>
              <div class="form-row">
                <label>{{ t('mail.server') }}<input v-model="mailSettings.smtp_host" maxlength="255" autocomplete="off" required /></label>
                <label>{{ t('mail.port') }}<input v-model.number="mailSettings.smtp_port" type="number" min="1" max="65535" required /></label>
              </div>
              <label>{{ t('mail.username') }}<input v-model="mailSettings.smtp_username" maxlength="255" autocomplete="username" /></label>
              <label>{{ t('mail.smtpPassword') }}<input v-model="mailPassword" type="password" maxlength="512" autocomplete="new-password" :disabled="clearMailPassword" :placeholder="mailSettings.smtp_password_configured ? t('mail.keepPassword') : t('mail.enterPassword')" /></label>
              <label v-if="mailSettings.smtp_password_configured" class="permission-toggle"><input v-model="clearMailPassword" type="checkbox" /> {{ t('mail.clearPassword') }}</label>
              <label>{{ t('mail.sender') }}<input v-model="mailSettings.from_address" type="email" maxlength="255" required /></label>
              <label class="permission-toggle"><input v-model="mailSettings.use_ssl" type="checkbox" /> {{ t('mail.ssl') }}</label>
              <label v-if="!mailSettings.use_ssl" class="permission-toggle"><input v-model="mailSettings.use_starttls" type="checkbox" /> {{ t('mail.starttls') }}</label>
              <div class="form-row"><button class="primary">{{ t('mail.save') }}</button><span v-if="mailSettingsMessage" class="muted">{{ t('mail.settingsSaved') }}</span></div>
            </form>
            <form v-if="mailEnabled" class="stack" @submit.prevent="void testMailDelivery()">
              <h4>{{ t('mail.test') }}</h4>
              <label>{{ t('mail.testAddress') }}<input v-model="mailTestRecipient" type="email" maxlength="254" required /></label>
              <div class="form-row"><button class="secondary" :disabled="mailTestBusy">{{ mailTestBusy ? t('mail.sending') : t('mail.saveAndTest') }}</button><span v-if="mailTestRecipientSent" class="muted" role="status">{{ t('mail.testSent', { recipient: mailTestRecipientSent }) }}</span></div>
            </form>
          </section>
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'license'" class="license-settings">
            <h3>{{ t('settings.license') }}</h3>
            <p v-if="licenseInfo?.institution_name" class="muted">{{ t('license.institution') }} <strong>{{ licenseInfo.institution_name }}</strong></p>
            <p class="muted">{{ t('license.statusLabel') }} <strong>{{ licenseInfo?.status ?? t('license.unchecked') }}</strong><span v-if="licenseInfo?.max_users">{{ t('license.userLimit', { count: licenseInfo.max_users }) }}</span><span v-if="licenseInfo?.license_expires_at">{{ t('license.expires', { date: new Date(licenseInfo.license_expires_at).toLocaleDateString(locale) }) }}</span></p>
            <p class="muted">{{ t('license.features', { features: licenseInfo?.features?.join(', ') || t('license.unlimited') }) }}</p>
            <form class="stack" @submit.prevent="replaceLicenseToken">
              <label>{{ t('license.token') }}<input v-model="licenseTokenInput" type="password" autocomplete="off" maxlength="4096" required /></label>
              <button class="secondary" :disabled="licenseCheckBusy">{{ licenseCheckBusy ? t('license.checking') : t('license.replace') }}</button>
            </form>
            <p class="muted">{{ t('license.tokenDescription') }}</p>
          </section>
          <BackupPanel v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'backup'" />
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'archive'" class="settings-section">
            <h3>{{ t('archive.autoTitle') }}</h3>
            <p class="muted">{{ t('archive.autoDescription') }}</p>
            <form class="stack" @submit.prevent="saveArchiveSettings">
              <label class="permission-toggle"><input v-model="archiveSettings.auto_enabled" type="checkbox" /> {{ t('archive.autoEnabled') }}</label>
              <label>{{ t('archive.period') }}<select v-model="archiveSettings.period" :disabled="!archiveSettings.auto_enabled"><option value="monthly">{{ t('archive.monthly') }}</option><option value="weekly">{{ t('archive.weekly') }}</option></select></label>
              <p v-if="archiveSettings.last_period_end" class="muted">{{ t('archive.lastPeriod', { date: dateLabel(archiveSettings.last_period_end) }) }}</p>
              <div class="form-row"><button class="secondary">{{ t('settings.save') }}</button><span v-if="archiveSettingsMessage" class="muted">{{ t('settings.saved') }}</span></div>
            </form>
          </section>
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'security'" class="settings-section">
            <h3>{{ t('settings.idleTitle') }}</h3>
            <p class="muted">{{ t('settings.idleDescription') }}</p>
            <form class="stack" @submit.prevent="saveIdleTimeout">
              <label>{{ t('settings.idleMinutes') }}<input v-model.number="idleTimeoutMinutes" type="number" min="1" max="120" required /></label>
              <div class="form-row"><button class="secondary">{{ t('settings.save') }}</button><span v-if="idleTimeoutMessage" class="muted">{{ t('settings.saved') }}</span></div>
            </form>
          </section>
          <section v-if="roleKey === 'ADMIN'" v-show="settingsTab === 'audit'" class="audit-settings">
            <h3>{{ t('audit.title') }}</h3>
            <p class="muted">{{ t('audit.description') }}</p>
            <label>{{ t('audit.filter') }}
              <select v-model="auditCategory" @change="auditEvents = []; auditOffset = 0; void loadAuditEvents(true)">
                <option value="">{{ t('audit.all') }}</option>
                <option value="logins">{{ t('audit.logins') }}</option>
                <option value="accounts">{{ t('audit.accounts') }}</option>
                <option value="backups">{{ t('audit.backups') }}</option>
              </select>
            </label>
            <div v-if="auditEvents.length" class="audit-list">
              <article v-for="event in auditEvents" :key="event.id" class="audit-row">
                <time :datetime="event.created_at">{{ new Date(event.created_at).toLocaleString(locale) }}</time>
                <strong>{{ event.actor_username }}</strong>
                <span>{{ auditActionLabel(event.action) }}</span>
                <code>{{ event.entity_type }} · {{ event.entity_id }}</code>
              </article>
            </div>
            <p v-else-if="!auditBusy" class="muted">{{ t('audit.empty') }}</p>
            <button v-if="auditHasMore" class="secondary audit-more" :disabled="auditBusy" @click="void loadAuditEvents()">{{ auditBusy ? t('audit.loading') : t('audit.more') }}</button>
            <span v-else-if="auditBusy" class="muted">{{ t('audit.loading') }}</span>
          </section>
        </template>
      </section>
    </div>
    <div v-if="authenticated && vacationAlert" class="modal-backdrop" @click.self="dismissVacationAlert">
      <section class="modal confirm-modal" role="alertdialog" aria-modal="true" :aria-label="t('notifications.vacationRequestTitle')">
        <p class="eyebrow">{{ t('notifications.vacationRequestTitle') }}</p>
        <h2>{{ t('notifications.vacationRequest', { name: vacationAlert.employee_name }) }}</h2>
        <p>{{ dateLabel(vacationAlert.start_date) }} – {{ dateLabel(vacationAlert.end_date) }}</p>
        <div class="form-row">
          <button class="secondary" @click="dismissVacationAlert">{{ t('management.cancel') }}</button>
          <button class="primary" @click="reviewVacationRequests">{{ t('notifications.reviewRequest') }}</button>
        </div>
      </section>
    </div>
  </div>
</template>
