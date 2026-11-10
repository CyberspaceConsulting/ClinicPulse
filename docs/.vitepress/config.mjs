import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'de-DE',
  title: 'ClinicPulse',
  description: 'Dokumentation zur Dienstplanung für Teams mit Schichtbetrieb',
  base: '/ClinicPulse/',
  lastUpdated: true,
  themeConfig: {
    nav: [{ text: 'GitHub', link: 'https://github.com/CyberspaceConsulting/ClinicPulse' }],
    sidebar: [
      { text: 'Übersicht', link: '/' },
      {
        text: 'Erste Schritte',
        link: '/getting-started/',
        items: [
          { text: 'Installation', link: '/getting-started/installation' },
          { text: 'Docker Compose', link: '/getting-started/docker-compose' },
          { text: 'Umgebungsvariablen', link: '/getting-started/environment-variables' },
          { text: 'Ersteinrichtung', link: '/getting-started/first-setup' },
        ],
      },
      {
        text: 'Funktionen',
        link: '/features/',
        items: [
          { text: 'Rollen und Berechtigungen', link: '/features/roles-and-permissions' },
          { text: 'Abteilungen und Mitarbeitende', link: '/features/departments-and-employees' },
          { text: 'Benutzer und Einladungen', link: '/features/users-and-invitations' },
          { text: 'Dienstplanung', link: '/features/shift-planning' },
          { text: 'Planungsvorschläge', link: '/features/planning-suggestions' },
          { text: 'Arbeitszeitregeln', link: '/features/work-rules' },
          { text: 'Abwesenheiten', link: '/features/absences' },
          { text: 'Plan-Archiv', link: '/features/archives' },
          { text: 'Backup und Wiederherstellung', link: '/features/backup' },
          { text: 'Lizenz', link: '/features/license' },
          { text: 'Sicherheit', link: '/features/security' },
          { text: 'E-Mail', link: '/features/mail' },
          { text: 'Protokoll und Updates', link: '/features/audit-and-updates' },
        ],
      },
      { text: 'Fehlerbehebung', link: '/troubleshooting' },
      { text: 'Architektur', link: '/architecture' },
    ],
    socialLinks: [{ icon: 'github', link: 'https://github.com/CyberspaceConsulting/ClinicPulse' }],
    editLink: {
      pattern: 'https://github.com/CyberspaceConsulting/ClinicPulse/edit/alpha/docs/:path',
      text: 'Diese Seite bearbeiten',
    },
  },
})
