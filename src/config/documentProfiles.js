/**
 * documentProfiles.js
 *
 * Configuration-driven document type definitions.
 *
 * Each profile defines:
 *   - label          Display name used in tabs and headings
 *   - shortLabel     Compact label for narrow UI contexts
 *   - icon           SVG path id or unicode reference (resolved in components)
 *   - travelerFields Ordered list of traveler info fields for this document type
 *   - verificationChecks  Ordered list of checks shown in VerificationChecks panel
 *   - acceptedMimeTypes   File types accepted by the upload component
 *   - maxFileSizeMB  Maximum upload size in megabytes
 *
 * Do NOT put verification algorithm logic here.
 * This is purely UI/UX configuration.
 *
 * Adding a new document type:
 *   1. Add a new key to DOCUMENT_PROFILES
 *   2. Add the key to DOCUMENT_TYPE_ORDER
 *   That's it — the workspace is reused automatically.
 */

/** Canonical document type keys */
export const DOCUMENT_TYPES = {
  PASSPORT:       'passport',
  VISA:           'visa',
  DRIVING_LICENSE:'drivingLicense',
  NATIONAL_ID:    'nationalId',
  BORDER_PERMIT:  'borderPermit',
};

/** Ordered list — drives tab rendering */
export const DOCUMENT_TYPE_ORDER = [
  DOCUMENT_TYPES.PASSPORT,
  DOCUMENT_TYPES.VISA,
  DOCUMENT_TYPES.DRIVING_LICENSE,
  DOCUMENT_TYPES.NATIONAL_ID,
  DOCUMENT_TYPES.BORDER_PERMIT,
];

/**
 * Traveler field definition shape:
 * {
 *   key:         string   — matches verificationSession.traveler key
 *   label:       string   — displayed label
 *   placeholder: string   — shown in standby state
 * }
 */

const COMMON_FIELDS = {
  name:        { key: 'name',        label: 'Full Name',        placeholder: '—' },
  docNumber:   { key: 'docNumber',   label: 'Document Number',  placeholder: '—' },
  dob:         { key: 'dob',         label: 'Date of Birth',    placeholder: '—' },
  nationality: { key: 'nationality', label: 'Nationality',      placeholder: '—' },
  authority:   { key: 'authority',   label: 'Issuing Authority', placeholder: '—' },
  expiry:      { key: 'expiry',      label: 'Expiry Date',      placeholder: '—' },
  issuedDate:  { key: 'issuedDate',  label: 'Issue Date',       placeholder: '—' },
  placeOfBirth:{ key: 'placeOfBirth',label: 'Place of Birth',   placeholder: '—' },
  gender:      { key: 'gender',      label: 'Gender',           placeholder: '—' },
  mrz:         { key: 'mrz',         label: 'Machine-Readable Line', placeholder: '—' },
  vehicleClass:{ key: 'vehicleClass',label: 'Vehicle Class',    placeholder: '—' },
  permitType:  { key: 'permitType',  label: 'Permit Type',      placeholder: '—' },
  portOfEntry: { key: 'portOfEntry', label: 'Port of Entry',    placeholder: '—' },
  passportNumber: { key: 'passportNumber', label: 'Linked Passport #', placeholder: '—' },
  visaType:       { key: 'visaType',       label: 'Visa Type / Class', placeholder: '—' },
  entries:        { key: 'entries',        label: 'Entries',          placeholder: '—' },
  durationOfStay: { key: 'durationOfStay', label: 'Duration of Stay', placeholder: '—' },
  bloodGroup:     { key: 'bloodGroup',     label: 'Blood Group',      placeholder: '—' },
  validFrom:      { key: 'validFrom',      label: 'Valid From',       placeholder: '—' },
  validTo:        { key: 'validTo',        label: 'Valid Till',       placeholder: '—' },
  licenseNumber:  { key: 'licenseNumber',  label: 'License Number',   placeholder: '—' },
  state:          { key: 'state',          label: 'Issuing State',    placeholder: '—' },
  identityNumber: { key: 'identityNumber', label: 'Identity Number',  placeholder: '—' },
  maskedIdentityNumber: { key: 'maskedIdentityNumber', label: 'National ID #', placeholder: '—' },
  yearOfBirth:    { key: 'yearOfBirth',    label: 'Year of Birth',    placeholder: '—' },
  address:        { key: 'address',        label: 'Address',          placeholder: '—' },
  qrPayload:      { key: 'qrPayload',      label: 'QR Code Data',     placeholder: '—' },
};

/**
 * Verification check definition shape:
 * {
 *   key:   string  — matches verificationSession.checks key
 *   label: string  — displayed label
 * }
 */
const COMMON_CHECKS = [
  { key: 'documentValidation',  label: 'Document Validation'  },
  { key: 'tamperingDetection',  label: 'Tampering Detection'  },
  { key: 'faceVerification',    label: 'Face Verification'    },
  { key: 'registryVerification',label: 'Registry Verification'},
  { key: 'riskAssessment',      label: 'Risk Assessment'      },
];

export const DOCUMENT_PROFILES = {
  [DOCUMENT_TYPES.PASSPORT]: {
    label:      'Passport',
    shortLabel: 'Passport',
    status:     'available',
    travelerFields: [
      COMMON_FIELDS.name,
      COMMON_FIELDS.docNumber,
      COMMON_FIELDS.dob,
      COMMON_FIELDS.nationality,
      COMMON_FIELDS.gender,
      COMMON_FIELDS.placeOfBirth,
      COMMON_FIELDS.authority,
      COMMON_FIELDS.issuedDate,
      COMMON_FIELDS.expiry,
      COMMON_FIELDS.mrz,
    ],
    verificationChecks: COMMON_CHECKS,
    acceptedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
    maxFileSizeMB: 10,
  },

  [DOCUMENT_TYPES.VISA]: {
    label:      'Visa',
    shortLabel: 'Visa',
    status:     'available',
    travelerFields: [
      COMMON_FIELDS.name,
      COMMON_FIELDS.docNumber,
      COMMON_FIELDS.passportNumber,
      COMMON_FIELDS.visaType,
      COMMON_FIELDS.nationality,
      COMMON_FIELDS.dob,
      COMMON_FIELDS.issuedDate,
      COMMON_FIELDS.expiry,
      COMMON_FIELDS.entries,
      COMMON_FIELDS.authority,
    ],
    verificationChecks: COMMON_CHECKS,
    acceptedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
    maxFileSizeMB: 10,
  },

  [DOCUMENT_TYPES.DRIVING_LICENSE]: {
    label:      'Driving License',
    shortLabel: 'DL',
    status:     'available',
    travelerFields: [
      COMMON_FIELDS.name,
      COMMON_FIELDS.docNumber,
      COMMON_FIELDS.dob,
      COMMON_FIELDS.issuedDate,
      COMMON_FIELDS.expiry,
      COMMON_FIELDS.bloodGroup,
      COMMON_FIELDS.vehicleClass,
      COMMON_FIELDS.authority,
      COMMON_FIELDS.state,
    ],
    verificationChecks: COMMON_CHECKS,
    acceptedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
    maxFileSizeMB: 8,
  },

  [DOCUMENT_TYPES.NATIONAL_ID]: {
    label:      'National ID',
    shortLabel: 'NID',
    status:     'available',
    travelerFields: [
      COMMON_FIELDS.name,
      COMMON_FIELDS.docNumber,
      COMMON_FIELDS.maskedIdentityNumber,
      COMMON_FIELDS.dob,
      COMMON_FIELDS.yearOfBirth,
      COMMON_FIELDS.gender,
      COMMON_FIELDS.authority,
      COMMON_FIELDS.address,
    ],
    verificationChecks: COMMON_CHECKS,
    acceptedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
    maxFileSizeMB: 8,
  },

  [DOCUMENT_TYPES.BORDER_PERMIT]: {
    label:      'Border Permit',
    shortLabel: 'Permit',
    status:     'available',
    travelerFields: [
      COMMON_FIELDS.name,
      COMMON_FIELDS.docNumber,
      COMMON_FIELDS.dob,
      COMMON_FIELDS.passportNumber,
      COMMON_FIELDS.permitType,
      COMMON_FIELDS.portOfEntry,
      COMMON_FIELDS.authority,
      COMMON_FIELDS.validFrom,
      COMMON_FIELDS.validTo,
      COMMON_FIELDS.expiry,
    ],
    verificationChecks: COMMON_CHECKS,
    acceptedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
    maxFileSizeMB: 10,
  },
};

/**
 * Returns the profile for a given document type key.
 * Falls back to passport profile if key is unknown.
 */
export function getProfile(documentType) {
  return DOCUMENT_PROFILES[documentType] ?? DOCUMENT_PROFILES[DOCUMENT_TYPES.PASSPORT];
}
