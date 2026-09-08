/**
 * mockSampleOptions.js
 *
 * Pre-configured official reference profiles and inspection cases
 * across all 5 supported credential categories (Passport, Driving Licence,
 * National ID, Visa, and Border Permit).
 *
 * Provides immediate zero-latency availability in the UI with automatic fallback
 * to static public image assets when the backend API is offline or warming up.
 */

export const DEFAULT_SAMPLE_OPTIONS = {
  passport: [
    {
      id: 'passport_official',
      label: 'Official Passport (Genuine)',
      badge: 'OFFICIAL / ACTIVE',
      variant: 'official',
      filename: 'Passport_Aarav_Sharma_Official.jpg',
      url: '/api/v1/verification/sample/passport?variant=official',
      fallbackUrl: '/samples/passport/passport_official.jpg',
      description: 'Authentic passport · Active registry status',
    },
    {
      id: 'passport_blacklist',
      label: 'Blacklisted Passport (Watchlist)',
      badge: 'BLACKLISTED',
      variant: 'blacklist',
      filename: 'Passport_Vikram_Malhotra_Blacklisted.jpg',
      url: '/api/v1/verification/sample/passport?variant=blacklist',
      fallbackUrl: '/samples/passport/passport_blacklist.jpg',
      description: 'Watchlist hit · Revoked in national database',
    },
    {
      id: 'passport_defective',
      label: 'Defective / Fake Passport',
      badge: 'DEFECT / FAKE',
      variant: 'defective',
      filename: 'Passport_Rohit_Verma_Defective.jpg',
      url: '/api/v1/verification/sample/passport?variant=defective',
      fallbackUrl: '/samples/passport/passport_defective.jpg',
      description: 'Tampered credential · Checksum & date mismatch',
    },
  ],

  driving_license: [
    {
      id: 'dl_bharath',
      label: 'State Transport Driving Licence (Official Active)',
      badge: 'OFFICIAL / ACTIVE',
      variant: 'bharath',
      filename: 'DL_Bharath_A_TamilNadu_Genuine.jpg',
      url: '/api/v1/verification/sample/driving_license?variant=bharath',
      fallbackUrl: '/samples/driving_license/dl_bharath_a_genuine.jpg',
      description: 'Original Indian Driving Licence: TN05 20250014128. Issued by Govt of Tamil Nadu. Status: ACTIVE in transport records.',
    },
    {
      id: 'dl_official',
      label: 'Official Driving License (Priya Sundar)',
      badge: 'OFFICIAL / ACTIVE',
      variant: 'official',
      filename: 'DL_Priya_Sundar_Official.jpg',
      url: '/api/v1/verification/sample/driving_license?variant=official',
      fallbackUrl: '/samples/dl/dl_official.jpg',
      description: 'Original driving license: Priya Sundar (DL-0420230012345). Active and verified in transport records.',
    },
    {
      id: 'dl_blacklist',
      label: 'Blacklisted DL (Revoked)',
      badge: 'BLACKLISTED',
      variant: 'blacklist',
      filename: 'DL_Kabir_Mehta_Blacklisted.jpg',
      url: '/api/v1/verification/sample/driving_license?variant=blacklist',
      fallbackUrl: '/samples/dl/dl_blacklist.jpg',
      description: 'Driving license for Kabir Mehta (DL-0120180099887). Status: REVOKED for invalid documentation.',
    },
    {
      id: 'dl_defective',
      label: 'Defective / Fake DL',
      badge: 'DEFECT / FAKE',
      variant: 'defective',
      filename: 'DL_Anil_Kumar_Defective.jpg',
      url: '/api/v1/verification/sample/driving_license?variant=defective',
      fallbackUrl: '/samples/dl/dl_defective.jpg',
      description: 'Tampered DL (INVALID-DL-12): Invalid issue date; missing vehicle types and issuing authority.',
    },
  ],

  national_id: [
    {
      id: 'national_id_official',
      label: 'Official National ID (Genuine)',
      badge: 'OFFICIAL / ACTIVE',
      variant: 'official',
      filename: 'NationalID_Sneha_Patel_Official.jpg',
      url: '/api/v1/verification/sample/national_id?variant=official',
      fallbackUrl: '/samples/national_id/national_id_official.jpg',
      description: 'Official 12-digit National ID for Sneha Patel (8472 9103 8473). Valid and registered in official records.',
    },
    {
      id: 'national_id_blacklist',
      label: 'Blacklisted National ID (Suspended)',
      badge: 'BLACKLISTED',
      variant: 'blacklist',
      filename: 'NationalID_Tariq_Ahmed_Blacklisted.jpg',
      url: '/api/v1/verification/sample/national_id?variant=blacklist',
      fallbackUrl: '/samples/national_id/national_id_blacklist.jpg',
      description: 'National ID for Tariq Ahmed (6541 2398 7101). Status: SUSPENDED / REVOKED on duplicate records.',
    },
    {
      id: 'national_id_defective',
      label: 'Defective / Fake National ID',
      badge: 'DEFECT / FAKE',
      variant: 'defective',
      filename: 'NationalID_Devraj_Singh_Defective.jpg',
      url: '/api/v1/verification/sample/national_id?variant=defective',
      fallbackUrl: '/samples/national_id/national_id_defective.jpg',
      description: 'Defective National ID (1234 5678 9999): Invalid number format with missing personal details.',
    },
  ],

  visa: [
    {
      id: 'visa_official',
      label: 'Official Entry Visa (Genuine)',
      badge: 'OFFICIAL / ACTIVE',
      variant: 'official',
      filename: 'Visa_Aarav_Sharma_Official.jpg',
      url: '/api/v1/verification/sample/visa?variant=official',
      fallbackUrl: '/samples/visa/visa_official.jpg',
      description: 'Official entry visa for Aarav Sharma (V1002003). Valid multi-entry linked to passport Z1234567.',
    },
    {
      id: 'visa_blacklist',
      label: 'Blacklisted Visa (Revoked)',
      badge: 'BLACKLISTED',
      variant: 'blacklist',
      filename: 'Visa_Vikram_Malhotra_Blacklisted.jpg',
      url: '/api/v1/verification/sample/visa?variant=blacklist',
      fallbackUrl: '/samples/visa/visa_blacklist.jpg',
      description: 'Entry visa for Vikram Malhotra (V7008009). Status: REVOKED in official immigration records.',
    },
    {
      id: 'visa_defective',
      label: 'Defective / Fake Visa',
      badge: 'DEFECT / FAKE',
      variant: 'defective',
      filename: 'Visa_Rohit_Verma_Defective.jpg',
      url: '/api/v1/verification/sample/visa?variant=defective',
      fallbackUrl: '/samples/visa/visa_defective.jpg',
      description: 'Invalid visa (V999) with missing details (passport number missing, issue date missing).',
    },
  ],

  border_permit: [
    {
      id: 'border_permit_official',
      label: 'Official Work/Border Permit (Genuine)',
      badge: 'OFFICIAL / ACTIVE',
      variant: 'official',
      filename: 'Permit_Elena_Rostova_Official.jpg',
      url: '/api/v1/verification/sample/border_permit?variant=official',
      fallbackUrl: '/samples/border_permit/border_permit_official.jpg',
      description: 'Official border entry & work permit: Elena Rostova (BP-2026-880011) linked to passport Z1234567.',
    },
    {
      id: 'border_permit_blacklist',
      label: 'Blacklisted Permit (Revoked)',
      badge: 'BLACKLISTED',
      variant: 'blacklist',
      filename: 'Permit_Marcus_Vance_Blacklisted.jpg',
      url: '/api/v1/verification/sample/border_permit?variant=blacklist',
      fallbackUrl: '/samples/border_permit/border_permit_blacklist.jpg',
      description: 'Border permit for Marcus Vance (BP-2025-443322). Status: REVOKED in official border records.',
    },
    {
      id: 'border_permit_defective',
      label: 'Defective / Fake Work Permit',
      badge: 'DEFECT / FAKE',
      variant: 'defective',
      filename: 'Permit_John_Doe_Defective.jpg',
      url: '/api/v1/verification/sample/border_permit?variant=defective',
      fallbackUrl: '/samples/border_permit/border_permit_defective.jpg',
      description: 'Invalid permit (PERMIT-XYZ): Expiry date precedes valid from date; missing passport reference.',
    },
  ],
};

// Aliases for camelCase document type keys
DEFAULT_SAMPLE_OPTIONS.drivingLicense = DEFAULT_SAMPLE_OPTIONS.driving_license;
DEFAULT_SAMPLE_OPTIONS.nationalId = DEFAULT_SAMPLE_OPTIONS.national_id;
DEFAULT_SAMPLE_OPTIONS.borderPermit = DEFAULT_SAMPLE_OPTIONS.border_permit;
