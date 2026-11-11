import { createRequire } from 'node:module'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { expect, test } = require('@playwright/test')

const employee = { id: 1, name: 'Alex Beispiel', role: 'Pflege', department_id: 1 }
const shift = {
  id: 1, name: 'Frühdienst', start_time: '07:00:00', end_time: '15:00:00',
  color: '#2563eb', position: 'Pflege', required_staff: 1,
  break_minutes: 30, break_start_minutes: 240, department_id: 1,
}

async function mockApi(page, role = 'OBERARZT', initialAbsences = [], failures = {}) {
  let signedIn = false
  let assignments = []
  let absences = initialAbsences
  const session = {
    username: role === 'EMPLOYEE' ? 'alex' : 'planer', role_key: role, department_id: 1,
    can_view: true, can_edit: role === 'OBERARZT', can_approve: role === 'OBERARZT',
    can_manage: false, remember_me: false, idle_timeout_minutes: 30,
  }
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (url.hostname !== '127.0.0.1') return route.abort()
    return route.continue()
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const reply = (json, status = 200) => route.fulfill({ status, json })
    if (failures.unavailableAssignments && path === '/api/assignments' && method === 'GET') {
      return route.abort('failed')
    }
    if (failures.expiredAssignments && path === '/api/assignments' && method === 'GET') {
      return reply({ detail: 'Sitzung abgelaufen' }, 401)
    }
    if (failures.forbiddenAssignment && path === '/api/assignments' && method === 'POST') {
      return reply({ detail: 'Keine Berechtigung für diese Aktion' }, 403)
    }
    if (path === '/api/health') return reply({ version: 'test', architecture: 'test' })
    if (path === '/api/setup/status') return reply({ setup_required: false, institution_name: null })
    if (path === '/api/auth/session') return signedIn ? reply(session) : reply({ detail: 'Anmeldung erforderlich (401)' }, 401)
    if (path === '/api/auth/login') {
      if (request.postDataJSON().password !== 'test-password') return reply({ detail: 'Ungültige Zugangsdaten' }, 401)
      signedIn = true
      return reply(session)
    }
    if (path === '/api/auth/logout') {
      signedIn = false
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/account-creation/mail-mode') return reply({ enabled: true })
    if (path === '/api/role-catalog') return reply({ functions: ['Pflege'], access_roles: [] })
    if (path === '/api/license/status') return reply({ status: 'PAID', read_only: false, suppress_warnings: false })
    if (path === '/api/departments') return reply([{ id: 1, name: 'Chirurgie' }])
    if (path === '/api/employees') return reply([employee])
    if (path === '/api/shift-types') return reply([shift])
    if (path === '/api/assignments' && method === 'POST') {
      assignments.push({ ...request.postDataJSON(), id: 1, employee_name: employee.name, shift_name: shift.name })
      return reply(assignments[0], 201)
    }
    if (path === '/api/assignments') return reply(assignments)
    if (path === '/api/planning/preview') return reply({ days: [{
      target_date: '2026-11-16', status: 'FEASIBLE',
      suggestions: [{ employee_id: 1, employee_name: employee.name, employee_role: employee.role, shift_type_id: 1, shift_name: shift.name, role_match: true, starts_at: '2026-11-16T07:00:00', ends_at: '2026-11-16T15:00:00' }],
      unfilled_slots: [{ shift_type_id: 1, shift_name: shift.name, position: shift.position }],
    }] })
    if (path === '/api/planning/approve') return reply({ created: 1 })
    if (path === '/api/absences' && method === 'POST') {
      absences.push({
        ...request.postDataJSON(), id: 1, employee_id: 1, employee_name: employee.name,
        status: 'pending', requested_by: 'alex', created_at: null, decided_by: null, decided_at: null,
      })
      return reply(absences[0], 201)
    }
    if (path === '/api/absences') return reply(absences)
    if (path === '/api/absences/1/decision') {
      absences[0].status = request.postDataJSON().decision
      absences[0].decided_by = 'planer'
      return reply(absences[0])
    }
    return reply({ detail: `Unexpected test request: ${method} ${path}` }, 500)
  })
  return failures
}

async function login(page) {
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Dienstplan', exact: true })).toBeVisible()
  await expect(page.getByText('Frühdienst').first()).toBeVisible()
}

test('password guidance uses the stored locale on the setup screen', async ({ page }) => {
  await mockApi(page)
  await page.route('**/api/setup/status', (route) => route.fulfill({ json: { setup_required: true, institution_name: null } }))
  await page.route('**/api/password/check', (route) => route.fulfill({ json: { compromised_count: 2 } }))
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.getByText('At least 8 characters; a longer and more varied passphrase is safer.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your administrator account' })).toBeVisible()
  await page.getByLabel('Password (at least 8 characters)').fill('test-password-123')
  await expect(page.getByText(/Found in data breaches \(2 times\)/)).toBeVisible()
  await expect(page.getByText(/Strength:/)).toBeVisible()
})

test('English login and navigation use the stored locale', async ({ page }) => {
  await mockApi(page)
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await page.getByLabel('Username').fill('planer')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('nav.mobile-navigation')).toHaveAttribute('aria-label', 'Mobile navigation')
  await expect(page.getByRole('button', { name: 'Open notifications' })).toBeVisible()
  await expect(page).toHaveTitle('ClinicPulse – Schedule')
})

test('mobile administrator toolbar remains usable when an error is displayed', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  await mockApi(page, 'ADMIN')
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.toast-error')).toContainText('Unexpected test request')
  await expect(page.getByLabel('Language')).toBeVisible()
  await expect(page.locator('.mobile-navigation').getByRole('button', { name: 'Team management' })).toBeVisible()
  await page.getByRole('button', { name: 'Settings', exact: true }).click({ timeout: 5000 })
  await expect(page.getByRole('tab', { name: 'Appearance' })).toBeVisible()
  await expect(page.locator('.toast-error')).toBeVisible()
})

test('notification history switches language without losing shift data or selected period', async ({ page }) => {
  await mockApi(page)
  await page.route('**/api/shift-types', (route) => route.fulfill({ json: [
    shift, { ...shift, id: 2, name: 'Spätdienst', position: 'OP', required_staff: 2 },
  ] }))
  await login(page)
  await page.getByRole('button', { name: 'Meldungen öffnen' }).click()
  await expect(page.getByRole('heading', { name: 'Meldungen' })).toBeVisible()
  await expect(page.locator('.notification-item').first()).toContainText('1 unbesetzte Pflege-Stelle · Frühdienst')
  await expect(page.locator('.notification-item').nth(1)).toContainText('2 unbesetzte OP-Stellen · Spätdienst')
  await page.getByLabel('Zeitraum').selectOption('7')
  await expect(page.locator('.notification-item')).toHaveCount(16)
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByRole('heading', { name: 'Notifications' })).toBeVisible()
  await expect(page.getByLabel('Period')).toHaveValue('7')
  await expect(page.locator('.notification-item').first()).toContainText('1 unfilled Pflege position · Frühdienst')
  await expect(page.locator('.notification-item').nth(1)).toContainText('2 unfilled OP positions · Spätdienst')
  await page.locator('.notification-item').first().click()
  await expect(page.getByRole('heading', { name: 'Day details' })).toBeVisible()
})

test('schedule overview and day details switch languages without changing custom names', async ({ page }) => {
  await mockApi(page)
  await login(page)
  await expect(page.locator('.overview-day').first()).toContainText('0 Dienste')
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByRole('heading', { name: 'Schedule', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Week overview' })).toBeVisible()
  await expect(page.locator('.overview-day').first()).toContainText('0 shifts')
  await expect(page.locator('.overview-day').first().locator('.overview-weekday')).toHaveText('Monday')
  await expect(page.locator('.today-panel')).toContainText('Frühdienst')
  await page.getByRole('button', { name: 'Open day details' }).click()
  await expect(page.getByRole('heading', { name: 'Day details' })).toBeVisible()
  await expect(page.getByText('Open position', { exact: true })).toBeVisible()
  await expect(page.locator('.team-roster')).toContainText('Alex Beispiel')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByRole('heading', { name: 'Tagesdetails' })).toBeVisible()
  await expect(page.getByText('Offene Stelle', { exact: true })).toBeVisible()
  await expect(page.locator('.team-roster')).toContainText('Alex Beispiel')
})

test('English shift forms and system role use localized labels while preserving values', async ({ page }) => {
  await mockApi(page)
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('planer')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.profile-text').first()).toContainText('Senior physician')
  await page.getByRole('button', { name: 'Open day details' }).click()
  await page.getByText('Open position', { exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Add shift' })).toBeVisible()
  await expect(dialog.getByLabel('Employee')).toHaveValue('1')
  await expect(dialog.getByLabel('Employee')).toContainText('Alex Beispiel')
  await expect(dialog.getByLabel('Shift type')).toContainText('Frühdienst')
  await dialog.getByRole('button', { name: 'Save shift' }).click()
  await expect(page.locator('.filled-slot')).toContainText('Alex Beispiel')
  await page.getByRole('button', { name: '＋ Shift type' }).click()
  await expect(dialog.getByRole('heading', { name: 'Create shift type' })).toBeVisible()
  await expect(dialog.getByLabel('Name')).toHaveAttribute('placeholder', 'e.g. Morning shift')
  await dialog.getByLabel('Name').fill('Eigene Schicht')
  await expect(dialog.getByLabel('Name')).toHaveValue('Eigene Schicht')
})

test('team management displays translated labels and preserves account and department data', async ({ page }) => {
  await mockApi(page, 'HOSPITAL_MANAGEMENT')
  await page.route('**/api/users', (route) => route.fulfill({ json: [{
    id: 2, username: 'test-user', role_key: 'EMPLOYEE', department_id: 1, department_ids: [1],
    employee_id: 1, can_view: true, can_edit: false, can_approve: false, invitation_status: 'pending',
  }] }))
  await page.route('**/api/role-catalog', (route) => route.fulfill({ json: {
    functions: ['Pflegefachkraft', 'Eigene Funktion'],
    access_roles: [{ key: 'HOSPITAL_MANAGEMENT', label: 'Wachleitung' }, { key: 'OBERARZT', label: 'Oberarzt' }, { key: 'EMPLOYEE', label: 'Mitarbeiter' }],
  } }))
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('planer')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.profile-text').first()).toContainText('Station management')
  await page.getByRole('button', { name: 'Team management', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Team & access' })).toBeVisible()
  await expect(dialog.getByText('test-user', { exact: true })).toBeVisible()
  await expect(dialog.locator('.account-row')).toContainText('Invitation pending')
  await expect(dialog.locator('.account-row')).toContainText('Chirurgie')
  await dialog.getByLabel('First name').fill('Unverändert')
  await dialog.getByLabel('System role').selectOption('EMPLOYEE')
  await expect(dialog.getByLabel('Linked person')).toContainText('Alex Beispiel')
  await expect(dialog.getByLabel('First name')).toHaveValue('Unverändert')
  await page.route('**/api/users/2/invitation', (route) => route.fulfill({ json: {
    id: 2, username: 'test-user', role_key: 'EMPLOYEE', department_id: 1, department_ids: [1],
    employee_id: 1, can_view: true, can_edit: false, can_approve: false,
    invitation_status: 'pending', email: 'person@example.org',
  } }))
  await dialog.getByRole('button', { name: 'Resend invitation' }).click()
  await expect(dialog.getByText('Invitation resent to person@example.org.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByLabel('Language').selectOption('de')
  await page.getByRole('button', { name: 'Teamverwaltung', exact: true }).first().click()
  await expect(dialog.getByText('Einladung an person@example.org erneut versendet.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Schließen', exact: true }).click()
  await page.getByLabel('Sprache').selectOption('en')
  await page.getByRole('button', { name: 'Team management', exact: true }).first().click()
  let deleteRequests = 0
  await page.route('**/api/users/2', (route) => {
    if (route.request().method() === 'DELETE') {
      deleteRequests++
      return route.fulfill({ status: 204 })
    }
    return route.fallback()
  })

  await dialog.locator('.account-row').getByRole('button', { name: 'Delete' }).click()
  const confirmation = page.getByRole('alertdialog', { name: 'Confirmation' })
  await expect(confirmation).toContainText('Delete account “test-user”?')
  await confirmation.getByRole('button', { name: 'Cancel' }).click()
  await expect(confirmation).toBeHidden()
  expect(deleteRequests).toBe(0)
  await dialog.locator('.account-row').getByRole('button', { name: 'Delete' }).click()
  const deleteResponse = page.waitForResponse((response) => response.url().endsWith('/api/users/2') && response.request().method() === 'DELETE')
  await confirmation.getByRole('button', { name: 'Delete' }).click()
  await deleteResponse
  expect(deleteRequests).toBe(1)
})

  test('disabled email offers temporary passwords for both account creation flows', async ({ page }) => {
    await mockApi(page, 'HOSPITAL_MANAGEMENT')
    await page.route('**/api/account-creation/mail-mode', (route) => route.fulfill({ json: { enabled: false } }))
    await page.route('**/api/users', (route) => route.fulfill({ json: route.request().method() === 'POST'
      ? { id: 2, invitation_status: 'active' } : [] }))
    await page.route('**/api/employees/onboard', (route) => route.fulfill({ status: 201, json: { employee, invitation_status: null } }))
    await page.route('**/api/role-catalog', (route) => route.fulfill({ json: {
      functions: ['Pflege'], access_roles: [{ key: 'HOSPITAL_MANAGEMENT', label: 'Leitung' }, { key: 'OBERARZT', label: 'Oberarzt' }],
    } }))
    await page.goto('/')
    await page.getByLabel('Benutzername').fill('planer')
    await page.getByLabel('Passwort', { exact: true }).fill('test-password')
    await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
    await page.getByRole('button', { name: 'Teamverwaltung', exact: true }).first().click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Vorname').fill('Ada')
    await dialog.getByLabel('Nachname').fill('Beispiel')
    await dialog.getByLabel('Benutzername').fill('ada')
    await dialog.locator('label.password-input input').fill('temporary-password')
    const userRequest = page.waitForRequest((req) => req.url().endsWith('/api/users') && req.method() === 'POST')
    await dialog.getByRole('button', { name: 'Konto anlegen' }).click()
    expect((await userRequest).postDataJSON()).toMatchObject({ username: 'ada', email: null, password: 'temporary-password' })
    await dialog.getByRole('button', { name: '＋ Mitarbeiter' }).click()
    await dialog.getByLabel('Vorname').fill('Ada')
    await dialog.getByLabel('Nachname').fill('Beispiel')
    await dialog.getByLabel('ClinicPulse-Zugang einrichten').check()
    await dialog.getByLabel('Benutzername').fill('ada-employee')
    await dialog.locator('label.password-input input').fill('employee-password')
    const onboardRequest = page.waitForRequest((req) => req.url().endsWith('/api/employees/onboard') && req.method() === 'POST')
    await dialog.getByRole('button', { name: 'Mitarbeiter erstellen' }).click()
    expect((await onboardRequest).postDataJSON()).toMatchObject({ username: 'ada-employee', email: null, password: 'employee-password' })
  })

  test('required password change blocks the app across session restore', async ({ page }) => {
    await mockApi(page)
    let required = true
    await page.route('**/api/auth/login', (route) => route.fulfill({ json: {
      username: 'planer', role_key: 'OBERARZT', department_id: 1, can_view: true,
      can_edit: true, can_approve: true, can_manage: false, remember_me: false, must_change_password: required,
    } }))
    await page.route('**/api/auth/session', (route) => route.fulfill({ json: {
      username: 'planer', role_key: 'OBERARZT', department_id: 1, can_view: true,
      can_edit: true, can_approve: true, can_manage: false, remember_me: false, must_change_password: required,
    } }))
    await page.route('**/api/settings/account', (route) => {
      required = false
      return route.fulfill({ json: {
        username: 'planer', role_key: 'OBERARZT', department_id: 1, can_view: true,
        can_edit: true, can_approve: true, can_manage: false, remember_me: false, must_change_password: false,
      } })
    })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Passwort ändern' })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Passwort ändern' })).toBeVisible()
    await page.getByLabel('Aktuelles Passwort zur Bestätigung').fill('test-password')
    await page.locator('label.password-input input').fill('different-password')
    await page.getByLabel('Passwort wiederholen').fill('different-password')
    const request = page.waitForRequest((req) => req.url().endsWith('/api/settings/account') && req.method() === 'PUT')
    await page.getByRole('button', { name: 'Passwort festlegen' }).click()
    expect((await request).postDataJSON()).toMatchObject({ username: 'planer', current_password: 'test-password', new_password: 'different-password' })
    await expect(page.getByRole('heading', { name: 'Dienstplan', exact: true })).toBeVisible()
  })

test('standard schedule functions translate without changing their values', async ({ page }) => {
  await mockApi(page, 'HOSPITAL_MANAGEMENT')
  await page.route('**/api/users', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/role-catalog', (route) => route.fulfill({ json: {
    functions: ['Pflegefachkraft', 'Eigene Funktion'], access_roles: [],
  } }))
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await page.getByRole('button', { name: 'Teamverwaltung', exact: true }).first().click()
  await page.getByRole('dialog').getByRole('button', { name: '＋ Mitarbeiter' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Dienstplanfunktion')).toHaveValue('Pflegefachkraft')
  await page.getByLabel('Sprache').selectOption('en')
  await expect(dialog.getByLabel('Schedule role')).toHaveValue('Pflegefachkraft')
  await expect(dialog.getByLabel('Schedule role')).toContainText('Registered nurse')
  await expect(dialog.getByLabel('Schedule role')).toContainText('Eigene Funktion')
})

test('English profile editing keeps user data and submits unchanged API values', async ({ page }) => {
  await mockApi(page)
  const profile = { username: 'planer', role_key: 'OBERARZT', department_id: 1, profile_image_data: null,
    profile_photo_visibility: 'department', first_name: 'Alex', last_name: 'Beispiel', remember_me: false }
  await page.route('**/api/profile/me', (route) => route.fulfill({ json: profile }))
  await page.route('**/api/profile/department', (route) => route.fulfill({ json: [
    { username: 'Kollege', role_key: 'EMPLOYEE', profile_image_data: null, department_id: 1 },
  ] }))
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('planer')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: 'Open your profile' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'My profile' })).toBeVisible()
  await expect(dialog.getByLabel('First name')).toHaveValue('Alex')
  await expect(dialog.getByText('Kollege', { exact: true })).toBeVisible()
  await dialog.getByLabel('First name').fill('Alex Neu')
  await dialog.getByLabel('Profile image visibility').selectOption('private')
  const request = page.waitForRequest((req) => req.url().endsWith('/api/profile/me') && req.method() === 'PUT')
  await dialog.getByRole('button', { name: 'Save profile' }).click()
  expect((await request).postDataJSON()).toMatchObject({ first_name: 'Alex Neu', last_name: 'Beispiel', profile_photo_visibility: 'private' })
  await dialog.getByLabel('Profile image (PNG, JPEG or WebP, maximum 256 KB)').setInputFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') })
  await expect(page.getByRole('alert').last()).toContainText('Choose a PNG, JPEG or WebP image up to 256 KB.')
})

test('English archive preserves names and archive request values', async ({ page }) => {
  await mockApi(page)
  await page.route('**/api/archives', (route) => {
    if (route.request().method() === 'POST') return route.fulfill({ json: { id: 2 } })
    return route.fulfill({ json: [{ id: 1, created_at: '2026-11-01T10:00:00Z', created_by: 'planer',
      start_date: '2026-10-01', end_date: '2026-10-31', department_id: 1, department_name: 'Chirurgie',
      note: 'Notiz', entry_count: 1, content_sha256: 'abc' }] })
  })
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('planer')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: /Archive/ }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Schedule archive' })).toBeVisible()
  await expect(dialog.locator('.management-row')).toContainText('Chirurgie')
  await expect(dialog.locator('.management-row')).toContainText('1 shift · archived')
  await expect(dialog.locator('.management-row')).toContainText('Notiz')
  await dialog.getByLabel('From', { exact: true }).fill('2026-10-01')
  await dialog.getByLabel('To', { exact: true }).fill('2026-10-31')
  await dialog.getByLabel('Note (optional)').fill('Eigene Notiz')
  const request = page.waitForRequest((req) => req.url().endsWith('/api/archives') && req.method() === 'POST')
  await dialog.getByRole('button', { name: 'Archive period' }).click()
  expect((await request).postDataJSON()).toEqual({ start_date: '2026-10-01', end_date: '2026-10-31', department_id: 1, note: 'Eigene Notiz' })
})

test('English absence request keeps user data and translates labels and status', async ({ page }) => {
  await mockApi(page, 'EMPLOYEE')
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('alex')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: /Absences/ }).click()
  await page.getByLabel('From', { exact: true }).fill('2026-11-16')
  await page.getByLabel('To', { exact: true }).fill('2026-11-17')
  await page.getByRole('button', { name: 'Submit request' }).click()
  await expect(page.getByText('Alex Beispiel · Vacation')).toBeVisible()
  await expect(page.getByText(/Pending/).last()).toBeVisible()
  await expect(page.getByText('Requested by alex')).toBeVisible()
})

test('known API errors are translated and unknown details remain visible', async ({ page }) => {
  await mockApi(page, 'EMPLOYEE')
  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 401, json: { detail: 'Invalid username or password' } }))
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('alex')
  await page.getByLabel('Passwort', { exact: true }).fill('incorrect')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Ungültiger Benutzername oder ungültiges Passwort')).toBeVisible()

  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 409, json: { detail: 'Username is already in use' } }))
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Der Benutzername wird bereits verwendet')).toBeVisible()

  await page.getByLabel('Sprache').selectOption('en')
  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 503, json: { detail: 'Externer Dienst: technische Details' } }))
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Server message: Externer Dienst: technische Details')).toBeVisible()
})

test('schedule API conflict is translated into German', async ({ page }) => {
  await mockApi(page)
  await page.route('**/api/assignments', async (route) => {
    if (route.request().method() === 'POST') return route.fulfill({ status: 409, json: { detail: 'Employee is absent during this shift' } })
    return route.fallback()
  })
  await login(page)
  await page.getByRole('button', { name: 'Tagesdetails öffnen' }).click()
  await page.getByText('Offene Stelle', { exact: true }).click()
  await page.getByRole('button', { name: 'Dienst speichern' }).click()
  await expect(page.locator('.toast.toast-error')).toContainText('Die Person ist während dieses Dienstes abwesend')
  await expect(page.getByRole('dialog')).toBeVisible()
})

test('English planning preview and approval retain custom names', async ({ page }) => {
  await mockApi(page)
  await page.addInitScript(() => localStorage.setItem('clinicpulse-locale', 'en'))
  await page.goto('/')
  await page.getByLabel('Username').fill('planer')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: /Shift planning/ }).click()
  await expect(page.getByRole('heading', { name: 'Suggest a schedule' })).toBeVisible()
  await page.getByRole('button', { name: /Suggest a schedule/ }).click()
  await expect(page.getByText('1 new shift suggested · 1 position unfilled')).toBeVisible()
  await expect(page.getByText('Unfilled: Frühdienst (Pflege)')).toBeVisible()
  await page.getByRole('button', { name: 'Approve schedule' }).click()
  await expect(page.getByText('1 shift was approved and scheduled.')).toBeVisible()
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByText('1 Dienst wurde genehmigt und eingetragen.')).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByText('1 shift was approved and scheduled.')).toBeVisible()
})

test('update selector shows the installed image and uses main and test channels', async ({ page }) => {
  await mockApi(page, 'ADMIN')
  let channel = 'test'
  await page.route('**/api/admin/updates**', (route) => route.fulfill({ json: {
    current_version: 'v-0.2.1-alpha', channel, latest_version: 'v-0.2.2-alpha',
    update_available: true, status: 'update_available', message: 'Version v-0.2.2-alpha ist verfügbar.',
    release_url: 'https://github.com/orgs/CyberspaceConsulting/packages/container/package/clinicpulse-backend',
    repository_url: 'https://github.com/CyberspaceConsulting/ClinicPulse', checked_at: '',
  } }))
  await page.route('**/api/admin/update-channel', (route) => {
    channel = route.request().postDataJSON().channel
    return route.fulfill({ json: { channel, status: 'no_release' } })
  })
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('admin')
  await page.getByLabel('Passwort', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.locator('.page-footer')).toContainText('Version v-0.2.1-alpha')
  const selector = page.getByLabel('Update-Kanal')
  await expect(selector).toHaveValue('test')
  await expect(selector.locator('option')).toHaveText(['Main', 'Test'])
  await expect(page.getByRole('link', { name: 'Update v-0.2.2-alpha verfügbar' })).toBeVisible()
  const request = page.waitForRequest((req) => req.url().endsWith('/api/admin/update-channel') && req.method() === 'PUT')
  await selector.selectOption('main')
  expect((await request).postDataJSON()).toEqual({ channel: 'main' })
  await expect(selector).toHaveValue('main')
})

test('backup interface translates without changing the restore confirmation contract', async ({ page }) => {
  await mockApi(page, 'ADMIN')
  await page.route('**/api/admin/updates**', (route) => route.fulfill({ json: {
    current_version: 'test', channel: 'main', latest_version: null, update_available: false,
    status: 'up_to_date', message: 'ClinicPulse ist auf dem aktuellen Release-Stand.', release_url: null, repository_url: '', checked_at: '',
  } }))
  await page.route('**/api/admin/business-configuration', (route) => route.fulfill({ json: {
    federal_state: 'Berlin', operational_profile: 'hospital', timezone: 'Europe/Berlin', sunday_work_authorized: false,
  } }))
  await page.route('**/api/admin/archive-settings', (route) => route.fulfill({ json: {
    auto_enabled: false, period: 'monthly', last_period_end: null,
  } }))
  await page.route('**/api/admin/work-rules', (route) => route.fulfill({ json: {
    rest_hours: 11, max_daily_hours: 10, max_weekly_hours: 48,
  } }))
  await page.route('**/api/admin/audit**', (route) => route.fulfill({ json: { items: [
    { id: 1, created_at: '2026-11-01T10:00:00Z', actor_username: 'admin', action: 'updated', entity_type: 'settings', entity_id: '1' },
    { id: 2, created_at: '2026-11-01T10:00:00Z', actor_username: 'admin', action: 'custom_action', entity_type: 'custom', entity_id: '2' },
    { id: 3, created_at: '2026-11-01T10:00:00Z', actor_username: 'admin', action: 'invitation_accepted', entity_type: 'user', entity_id: '3' },
  ], limit: 25, offset: 0 } }))
  await page.route('**/api/admin/mail-settings', (route) => route.fulfill({ json: {
    public_url: 'https://clinic.example', smtp_host: 'smtp.example', smtp_port: 587, smtp_username: 'user',
    smtp_password_configured: true, from_address: 'sender@example.org', use_ssl: false, use_starttls: true,
  } }))
  let backupSettingsFail = false
  let restoreFails = true
  await page.route('**/api/admin/backup/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/settings') && route.request().method() === 'PUT' && backupSettingsFail) {
      return route.fulfill({ status: 404, json: { detail: 'Backup-Ziel nicht gefunden' } })
    }
    if (path.endsWith('/settings')) return route.fulfill({ json: { schedule_enabled: false, frequency: 'weekly', weekday: 0, time_of_day: '12:00', recipient_count: 1, timezone: 'Europe/Berlin' } })
    if (path.endsWith('/recipients')) return route.fulfill({ json: [{ id: 1, name: 'Team A', public_key: 'CPPUB1:test' }] })
    if (path.endsWith('/targets') || path.endsWith('/runs')) return route.fulfill({ json: [] })
    if (path.endsWith('/restore')) return restoreFails
      ? route.fulfill({ status: 422, json: { detail: 'Passwort der Schlüsseldatei ist falsch' } })
      : route.fulfill({ json: { ok: true } })
    return route.fulfill({ status: 404, json: { detail: 'Unexpected backup request' } })
  })
  await page.goto('/')
  await page.getByLabel('Sprache').selectOption('en')
  await page.getByLabel('Username').fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.toast-error')).toHaveCount(0)
  await expect(page.getByText('ClinicPulse is up to date.')).toBeVisible()
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(page.locator('.toast-error')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '☼ Light' })).toBeVisible()
  await page.getByRole('tab', { name: 'Operations & working time' }).click()
  await expect(page.getByRole('heading', { name: 'Operating configuration' })).toBeVisible()
  await expect(page.getByLabel('Facility type')).toHaveValue('hospital')
  await expect(page.getByLabel('Facility type')).toContainText('Hospital')
  await expect(page.getByLabel('Minimum rest between shifts (hours)')).toHaveValue('11')
  await page.getByLabel('Maximum daily working time, net (hours)').fill('9')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByRole('heading', { name: 'Betriebskonfiguration' })).toBeVisible()
  await expect(page.getByLabel('Höchstarbeitszeit pro Tag, netto (Stunden)')).toHaveValue('9')
  await page.getByLabel('Sprache').selectOption('en')
  const rulesRequest = page.waitForRequest((req) => req.url().endsWith('/api/admin/work-rules') && req.method() === 'PUT')
  await page.getByRole('button', { name: 'Save rules' }).click()
  expect((await rulesRequest).postDataJSON()).toMatchObject({ rest_hours: 11, max_daily_hours: 9, max_weekly_hours: 48 })
  await expect(page.locator('span.muted').getByText('Saved', { exact: true })).toBeVisible()
  await page.getByLabel('Language').selectOption('de')
  await expect(page.locator('span.muted').getByText('Gespeichert', { exact: true })).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  await page.getByRole('tab', { name: 'Audit log' }).click()
  await expect(page.locator('.audit-row').first()).toContainText('updated')
  await expect(page.locator('.audit-row').nth(1)).toContainText('custom_action')
  await expect(page.locator('.audit-row').nth(2)).toContainText('invitation accepted')
  await page.getByRole('tab', { name: 'License' }).click()
  await expect(page.getByLabel('Updated license token')).toBeVisible()
  await expect(page.getByText('The token is not displayed or returned. The license server links it idempotently to this installation.')).toBeVisible()
  await page.getByRole('tab', { name: 'Email delivery' }).click()
  await expect(page.getByRole('heading', { name: 'Email delivery (SMTP)' })).toBeVisible()
  await expect(page.getByLabel('SMTP password', { exact: true })).toHaveAttribute('placeholder', 'Keep saved password')
  await page.getByLabel('SMTP server').fill('custom.example')
  await page.getByLabel('Delete saved SMTP password').check()
  await expect(page.getByLabel('SMTP password', { exact: true })).toBeDisabled()
  await page.getByLabel('Delete saved SMTP password').uncheck()
  const mailRequest = page.waitForRequest((req) => req.url().endsWith('/api/admin/mail-settings') && req.method() === 'PUT')
  await page.getByRole('button', { name: 'Save email settings' }).click()
  expect((await mailRequest).postDataJSON()).toMatchObject({ smtp_host: 'custom.example', smtp_password: null, clear_smtp_password: false, use_ssl: false, use_starttls: true })
  await expect(page.getByText('Email settings saved.')).toBeVisible()
  await page.route('**/api/admin/mail-mode', (route) => route.fulfill({ json: route.request().postDataJSON() }))
  await page.getByLabel('Enable email delivery').uncheck()
  const modeRequest = page.waitForRequest((req) => req.url().endsWith('/api/admin/mail-mode') && req.method() === 'PUT')
  await page.getByRole('button', { name: 'Save delivery setting' }).click()
  expect((await modeRequest).postDataJSON()).toEqual({ enabled: false })
  await expect(page.getByLabel('SMTP server')).toHaveCount(0)
  await page.getByRole('tab', { name: 'Security' }).click()
  await expect(page.getByRole('heading', { name: 'Automatic sign-out' })).toBeVisible()
  await expect(page.getByLabel('Inactivity before sign-out (minutes)')).toBeVisible()
  await page.getByRole('tab', { name: 'Archiving' }).click()
  await expect(page.getByRole('heading', { name: 'Automatic archiving' })).toBeVisible()
  await expect(page.getByLabel('Archive automatically')).toBeVisible()
  await expect(page.getByLabel('Period')).toHaveValue('monthly')
  await page.getByRole('tab', { name: 'Backup' }).click()
  await expect(page.getByRole('heading', { name: 'Data backup' })).toBeVisible()
  await expect(page.locator('.backup-settings option').getByText('Monday', { exact: true })).toBeAttached()
  await expect(page.getByText('Team A', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Save schedule' }).click()
  await expect(page.locator('.backup-settings [role="status"]')).toHaveText('Settings saved.')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.locator('.backup-settings [role="status"]')).toHaveText('Einstellungen gespeichert.')
  await page.getByLabel('Sprache').selectOption('en')
  backupSettingsFail = true
  await page.getByRole('button', { name: 'Save schedule' }).click()
  await expect(page.locator('.backup-settings [role="alert"]')).toHaveText('Backup destination not found')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.locator('.backup-settings [role="alert"]')).toHaveText('Backup-Ziel nicht gefunden')
  await page.getByLabel('Sprache').selectOption('en')
  backupSettingsFail = false
  const restore = page.getByRole('button', { name: 'Restore from file' })
  await page.getByLabel('Recovery key (.cpkey)').setInputFiles({ name: 'test.cpkey', mimeType: 'text/plain', buffer: Buffer.from('test-key') })
  await page.getByLabel('Upload backup file (.cpbak)').setInputFiles({ name: 'test.cpbak', mimeType: 'application/octet-stream', buffer: Buffer.from('test-backup') })
  await page.getByLabel('Key file password', { exact: true }).fill('test-password')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByRole('heading', { name: 'Datensicherung' })).toBeVisible()
  await expect(page.locator('.backup-settings option').getByText('Montag', { exact: true })).toBeAttached()
  await expect(page.getByText('Team A', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Passwort der Schlüsseldatei', { exact: true })).toHaveValue('test-password')
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByRole('heading', { name: 'Data backup' })).toBeVisible()
  await expect(page.getByLabel('Key file password', { exact: true })).toHaveValue('test-password')
  await page.getByLabel('Enter “WIEDERHERSTELLEN” to confirm').fill('RESTORE')
  await expect(restore).toBeDisabled()
  await page.getByLabel('Enter “WIEDERHERSTELLEN” to confirm').fill('WIEDERHERSTELLEN')
  await expect(restore).toBeEnabled()
  await restore.click()
  await expect(page.locator('.backup-settings [role="alert"]')).toHaveText('The key file password is incorrect')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.locator('.backup-settings [role="alert"]')).toHaveText('Passwort der Schlüsseldatei ist falsch')
  await page.getByLabel('Sprache').selectOption('en')
  restoreFails = false
  const request = page.waitForRequest((req) => req.url().endsWith('/api/admin/backup/restore') && req.method() === 'POST')
  await restore.click()
  expect((await request).headers()['x-restore-confirm']).toBe('WIEDERHERSTELLEN')
  await expect(page.getByText('Restore complete. The page will reload …')).toBeVisible()
})

test('language selector works before and after login and persists across reload', async ({ page }) => {
  await mockApi(page, 'EMPLOYEE')
  await page.goto('/')
  const selector = page.getByLabel('Sprache')
  await expect(selector).toBeVisible()
  await selector.focus()
  await selector.selectOption('en')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByText('English translation is incomplete; some text may still appear in German.')).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await page.reload()
  await expect(page.getByLabel('Language')).toHaveValue('en')
  await page.getByLabel('Username').fill('alex')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByLabel('Language')).toBeVisible()
  await expect(page.getByText('English translation is incomplete; some text may still appear in German.')).toBeVisible()
  await page.getByRole('button', { name: /Absences/ }).click()
  await expect(page.getByRole('heading', { name: 'Absences' })).toBeVisible()
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByRole('heading', { name: 'Abwesenheiten' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'de')
  await page.reload()
  await expect(page.getByLabel('Sprache')).toHaveValue('de')
})

test('Anmeldung zeigt Fehler und erlaubt anschließend Abmeldung', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Dokumentation' })).toHaveAttribute('href', 'https://cyberspaceconsulting.github.io/ClinicPulse/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('falsch')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Ungültige Zugangsdaten')).toBeVisible()
  await page.getByLabel('Passwort', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Dienstplan', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Dokumentation' })).toHaveAttribute('href', 'https://cyberspaceconsulting.github.io/ClinicPulse/')
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Willkommen zurück' })).toBeVisible()
})

test('API errors are retranslated when the language changes', async ({ page }) => {
  await mockApi(page)
  let detail = 'Invalid username or password'
  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 401, json: { detail } }))
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('incorrect')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Ungültiger Benutzername oder ungültiges Passwort')).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByText('Invalid username or password')).toBeVisible()
  await expect(page.getByLabel('Username')).toHaveValue('planer')
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByText('Ungültiger Benutzername oder ungültiges Passwort')).toBeVisible()
  detail = 'Unbekannter externer Fehler'
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText(detail)).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByText(/Unbekannter externer Fehler/)).toBeVisible()
})

test('validation and parameterized API errors retain details across language changes', async ({ page }) => {
  await mockApi(page)
  let detail = [{ type: 'value_error', msg: 'Value error, Planning permissions require schedule view access' }]
  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 422, json: { detail } }))
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('incorrect')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Planungsberechtigungen erfordern Zugriff auf die Dienstplanansicht')).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByText('Planning permissions require schedule view access')).toBeVisible()
  detail = [
    { type: 'string_too_short', msg: 'String should have at least 3 characters', ctx: { min_length: 3 } },
    { type: 'greater_than_equal', msg: 'Input should be greater than or equal to 1', ctx: { ge: 1 } },
  ]
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Enter at least 3 characters; The value must be at least 1')).toBeVisible()
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByText('Mindestens 3 Zeichen eingeben; Der Wert muss mindestens 1 betragen')).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  detail = 'Das Feld „host_key_fingerprint“ ist erforderlich'
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('The field “host_key_fingerprint” is required')).toBeVisible()
  await page.getByLabel('Language').selectOption('de')
  await expect(page.getByText('Das Feld „host_key_fingerprint“ ist erforderlich')).toBeVisible()
  detail = 'Frühdienst Team A on 2026-11-16 is already fully staffed'
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Frühdienst Team A am 2026-11-16 ist bereits vollständig besetzt')).toBeVisible()
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByText('Frühdienst Team A on 2026-11-16 is already fully staffed')).toBeVisible()
  for (const [serverDetail, expected] of [
    ['Das Passwort muss mindestens 12 Zeichen lang sein', 'The password must be at least 12 characters long'],
    ['Das Backup enthält die unbekannte Tabelle „events“ – wahrscheinlich stammt es aus einer neueren ClinicPulse-Version', 'The backup contains the unknown table “events”; it may be from a newer ClinicPulse version'],
    ['Das Backup enthält unbekannte Spalten in „events“ – bitte zuerst ClinicPulse aktualisieren', 'The backup contains unknown columns in “events”; update ClinicPulse first'],
    ['Host-Key stimmt nicht überein (Server meldet SHA256:abc)', 'Host key does not match (server reports SHA256:abc)'],
    ['SFTP-Verbindung fehlgeschlagen: TimeoutError', 'SFTP connection failed: TimeoutError'],
    ['SFTP-Fehler: OSError', 'SFTP error: OSError'],
    ['WebDAV-Verbindung fehlgeschlagen: TimeoutError', 'WebDAV connection failed: TimeoutError'],
    ['WebDAV-Server antwortete mit HTTP 503', 'WebDAV server responded with HTTP 503'],
    ['S3-Fehler: AccessDenied', 'S3 error: AccessDenied'],
  ]) {
    detail = serverDetail
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByText(expected, { exact: true })).toBeVisible()
  }
  detail = [{ msg: 'Value error, External validation detail' }]
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText(/Value error, External validation detail/)).toBeVisible()
  await page.getByLabel('Language').selectOption('de')
  for (const [serverDetail, expected] of [
    ['Minimum rest period of 11 hours between shifts would be violated', 'Die Mindestruhezeit von 11 Stunden zwischen Schichten würde unterschritten'],
    ['Daily working time would exceed 10 hours (ArbZG §3)', 'Die tägliche Arbeitszeit würde 10 Stunden überschreiten (ArbZG §3)'],
    ['Average working time would exceed 48 hours per week over the 24-week reference period (ArbZG §3)', 'Die durchschnittliche Arbeitszeit würde im 24-Wochen-Ausgleichszeitraum 48 Stunden pro Woche überschreiten (ArbZG §3)'],
    ['At least 30 minutes of break are required for this shift length (ArbZG §4)', 'Für diese Schichtdauer sind mindestens 30 Minuten Pause erforderlich (ArbZG §4)'],
    ['A distinct replacement rest day is required within a 14-day period including 2026-11-16 (ArbZG §11)', 'Ein eigener Ersatzruhetag ist innerhalb eines Zeitraums von 14 Tagen einschließlich 2026-11-16 erforderlich (ArbZG §11)'],
    ['License is read-only: License is blocked', 'Die Lizenz erlaubt nur Lesezugriff: Die Lizenz ist gesperrt'],
    ['Limit optimization to a maximum of 150 open positions per day', 'Die Optimierung ist auf höchstens 150 offene Stellen pro Tag begrenzt'],
    ['Select a smaller department for day optimization', 'Für die Tagesoptimierung eine kleinere Abteilung auswählen'],
    ['Optimization has too many eligible employee-position combinations', 'Die Optimierung enthält zu viele geeignete Kombinationen aus Mitarbeitenden und Stellen'],
  ]) {
    detail = serverDetail
    await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
    await expect(page.getByText(expected, { exact: true })).toBeVisible()
  }
  detail = 'Zu viele Anmeldeversuche. Bitte in 60 Sekunden erneut versuchen.'
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await page.getByLabel('Sprache').selectOption('en')
  await expect(page.getByText('Too many sign-in attempts. Please try again in 60 seconds.')).toBeVisible()
})

test('offene Stelle kann im Tagesplan besetzt werden', async ({ page }) => {
  await mockApi(page)
  await login(page)
  await page.getByRole('button', { name: 'Tagesdetails öffnen' }).click()
  await page.getByText('Offene Stelle', { exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Dienst speichern' }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page.locator('.filled-slot').getByText('Alex Beispiel')).toBeVisible()
  await expect(page.getByText('Offene Stelle', { exact: true })).toHaveCount(0)
})

test('Mitarbeitende können eine Abwesenheit beantragen', async ({ page }) => {
  await mockApi(page, 'EMPLOYEE')
  await login(page)
  await page.getByRole('button', { name: /Abwesenheiten/ }).click()
  await page.getByLabel('Von', { exact: true }).fill('2026-11-16')
  await page.getByLabel('Bis', { exact: true }).fill('2026-11-17')
  await page.getByRole('button', { name: 'Antrag stellen' }).click()
  await expect(page.getByText('Alex Beispiel · Urlaub')).toBeVisible()
  await expect(page.getByText(/Offen/).last()).toBeVisible()
})

test('berechtigte Planer können einen Antrag genehmigen', async ({ page }) => {
  await mockApi(page, 'OBERARZT', [{
    id: 1, employee_id: 1, employee_name: employee.name, kind: 'vacation',
    start_date: '2026-11-16', end_date: '2026-11-17', status: 'pending',
    note: null, requested_by: 'alex', created_at: null, decided_by: null, decided_at: null,
  }])
  await login(page)
  await page.getByRole('button', { name: /Abwesenheiten/ }).click()
  await page.getByRole('button', { name: 'Genehmigen' }).click()
  await expect(page.getByText(/Genehmigt von planer/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Genehmigen' })).toHaveCount(0)
})

test('nur erlaubte Abteilung und Aktionen werden angezeigt', async ({ page }) => {
  await mockApi(page, 'CHEFARZT')
  await login(page)
  await expect(page.locator('button[title="Chirurgie"]')).toHaveCount(1)
  await expect(page.locator('button[title="Radiologie"]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Dienst eintragen/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Tagesdetails öffnen' }).click()
  await expect(page.getByText('Offene Stelle', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Dienst speichern' })).toHaveCount(0)
})

test('abgelaufene Sitzung während eines API-Aufrufs führt zurück zur Anmeldung', async ({ page }) => {
  const failures = await mockApi(page)
  await login(page)
  failures.expiredAssignments = true

  await page.reload()

  await expect(page.getByRole('heading', { name: 'Willkommen zurück' })).toBeVisible()
  await expect(page.getByLabel('Benutzername')).toBeVisible()
})

test('verbotene Planänderung wird sichtbar gemeldet', async ({ page }) => {
  const failures = await mockApi(page)
  await login(page)
  failures.forbiddenAssignment = true
  await page.getByRole('button', { name: 'Tagesdetails öffnen' }).click()
  await page.getByText('Offene Stelle', { exact: true }).click()
  await page.getByRole('button', { name: 'Dienst speichern' }).click()

  await expect(page.locator('.toast.toast-error')).toContainText('Keine Berechtigung für diese Aktion')
  await expect(page.getByRole('dialog')).toBeVisible()
})

test('nicht erreichbare API zeigt eine Fehlermeldung statt leerer Plan-Daten', async ({ page }) => {
  const failures = await mockApi(page)
  await login(page)
  failures.unavailableAssignments = true

  await page.reload()

  await expect(page.locator('.toast.toast-error')).toContainText('Failed to fetch')
  await expect(page.getByRole('heading', { name: 'Dienstplan', exact: true })).toBeVisible()
})
