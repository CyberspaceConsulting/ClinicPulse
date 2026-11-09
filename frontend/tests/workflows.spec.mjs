import { expect, test } from '@playwright/test'

const employee = { id: 1, name: 'Alex Beispiel', role: 'Pflege', department_id: 1 }
const shift = {
  id: 1, name: 'Frühdienst', start_time: '07:00:00', end_time: '15:00:00',
  color: '#2563eb', position: 'Pflege', required_staff: 1,
  break_minutes: 30, break_start_minutes: 240, department_id: 1,
}

async function mockApi(page, role = 'OBERARZT', initialAbsences = []) {
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
}

async function login(page) {
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Dienstplan', exact: true })).toBeVisible()
  await expect(page.getByText('Frühdienst').first()).toBeVisible()
}

test('Anmeldung zeigt Fehler und erlaubt anschließend Abmeldung', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('planer')
  await page.getByLabel('Passwort', { exact: true }).fill('falsch')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Ungültige Zugangsdaten')).toBeVisible()
  await page.getByLabel('Passwort', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Dienstplan', exact: true })).toBeVisible()
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
