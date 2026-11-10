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

  await page.getByLabel('Sprache').selectOption('en')
  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 503, json: { detail: 'Externer Dienst: technische Details' } }))
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Server message: Externer Dienst: technische Details')).toBeVisible()
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
