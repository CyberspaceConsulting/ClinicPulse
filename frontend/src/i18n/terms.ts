import { ref } from 'vue'

export type Gender = 'f' | 'm' | 'n'
type Unit = { singular: string; plural: string; gender: Gender; compound: string }
type UnitLocale = 'de' | 'en'

export type FacilityStructure = {
  single_unit: boolean
  uses_vehicles: boolean
  unit_label: string | null
  unit_label_plural: string | null
  unit_gender: Gender | null
  lead_label: string | null
}

const builtIn: Record<string, Record<UnitLocale, Unit>> = {
  hospital: {
    de: { singular: 'Abteilung', plural: 'Abteilungen', gender: 'f', compound: 'Abteilungs' },
    en: { singular: 'Department', plural: 'Departments', gender: 'n', compound: 'Department' },
  },
  rescue_service: {
    de: { singular: 'Standort', plural: 'Standorte', gender: 'm', compound: 'Standort' },
    en: { singular: 'Location', plural: 'Locations', gender: 'n', compound: 'Location' },
  },
  ils: {
    de: { singular: 'Leitstelle', plural: 'Leitstellen', gender: 'f', compound: 'Leitstellen' },
    en: { singular: 'Control center', plural: 'Control centers', gender: 'n', compound: 'Control center' },
  },
}
builtIn.care_facility = builtIn.hospital

export const facilityProfile = ref('hospital')
export const facilityStructure = ref<FacilityStructure>({
  single_unit: false, uses_vehicles: false, unit_label: null, unit_label_plural: null, unit_gender: null, lead_label: null,
})

export function setFacilityTerminology(profile: string, structure: FacilityStructure) {
  facilityProfile.value = profile
  facilityStructure.value = structure
}

function unitFor(locale: UnitLocale): Unit {
  const structure = facilityStructure.value
  if (facilityProfile.value === 'other' && structure.unit_label) {
    return {
      singular: structure.unit_label,
      plural: structure.unit_label_plural || structure.unit_label,
      gender: structure.unit_gender ?? 'n',
      compound: structure.unit_label,
    }
  }
  return (builtIn[facilityProfile.value] ?? builtIn.hospital)[locale]
}

const lowerFirst = (value: string) => value.charAt(0).toLowerCase() + value.slice(1)
const upperFirst = (value: string) => value.charAt(0).toUpperCase() + value.slice(1)
const GENDER_INDEX: Record<Gender, number> = { f: 0, m: 1, n: 2 }

function germanTokens(unit: Unit): Record<string, string> {
  const g = GENDER_INDEX[unit.gender]
  const noun = unit.singular
  const main = `Haupt${lowerFirst(noun)}`
  const word = (forms: [string, string, string], value = noun) => `${forms[g]} ${value}`
  return {
    unit: noun, units: unit.plural, unitc: unit.compound, unitcl: lowerFirst(unit.compound), unith: main,
    the_unit: word(['die', 'der', 'das']),
    the_unith: word(['die', 'der', 'das'], main),
    a_unit: word(['eine', 'einen', 'ein']),
    a_unit_nom: word(['eine', 'ein', 'ein']),
    your_unit: word(['deine', 'deinen', 'dein']),
    your_own_unit: word(['deine eigene', 'deinen eigenen', 'dein eigenes']),
    your_unit_dat: word(['deiner', 'deinem', 'deinem']),
    my_unit: word(['meine', 'meinen', 'mein']),
    this_unit: word(['diese', 'diesen', 'dieses']),
    no_unit: word(['keine', 'kein', 'kein']),
    no_unit_dat: word(['keiner', 'keinem', 'keinem']),
    the_same_unit_dat: word(['derselben', 'demselben', 'demselben']),
    this_unit_gen: `${['dieser', 'dieses', 'dieses'][g]} ${g === 0 ? noun : noun + (/[sßxz]$/i.test(noun) ? 'es' : 's')}`,
    a_smaller_unit: word(['eine kleinere', 'einen kleineren', 'ein kleineres']),
    to_unit: word(['zur', 'zum', 'zum']),
  }
}

function englishTokens(unit: Unit): Record<string, string> {
  const noun = unit.singular
  const article = /^[aeiou]/i.test(noun) ? 'an' : 'a'
  return {
    unit: noun, units: unit.plural, unitl: lowerFirst(noun), unitsl: lowerFirst(unit.plural),
    a_unit: `${article} ${lowerFirst(noun)}`,
  }
}

/** Replacement values for the terminology placeholders of the current facility type. */
export function terminologyTokens(locale: UnitLocale): Record<string, string> {
  const unit = unitFor(locale)
  return locale === 'de' ? germanTokens(unit) : englishTokens(unit)
}

/** Resolves a placeholder; an upper-case first letter capitalises the result. */
export function terminologyValue(locale: UnitLocale, name: string): string | undefined {
  const value = terminologyTokens(locale)[lowerFirst(name)]
  if (value === undefined) return undefined
  return name.charAt(0) === name.charAt(0).toUpperCase() && name.charAt(0) !== name.charAt(0).toLowerCase()
    ? upperFirst(value)
    : value
}
