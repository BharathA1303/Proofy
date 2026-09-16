/**
 * validationIssueSummary.js
 *
 * Short, officer-facing summaries for Module 2 document validation issues.
 *
 * The backend's `issue.message` is a detailed audit-log string (correction
 * tags like "line1:pad_to_44_safe:from_43", algorithm names, raw evidence)
 * meant for the Technical Audit panel — officer-facing cards need a 1-line,
 * plain-language version instead.
 */

const VALIDATION_ISSUE_SUMMARIES = {
  mrz_auto_correction: {
    warning: 'Minor formatting recovery applied to machine-readable zone — document still verified authentic.',
    critical: 'Machine-readable zone shows signs of tampering and could not be verified.',
  },
  mrz_length_critical: {
    critical: 'Machine-readable zone is malformed and could not be read reliably.',
  },
  mrz_structure: {
    critical: 'Machine-readable zone structure does not match the expected passport format.',
    warning: 'Machine-readable zone has a minor structural discrepancy.',
  },
  document_number_checksum: { failure: 'Document number failed the official checksum verification.' },
  dob_checksum: { failure: 'Date of birth failed the official checksum verification.' },
  expiry_checksum: { failure: 'Expiry date failed the official checksum verification.' },
  composite_checksum: { critical: 'Composite security checksum failed — document integrity could not be confirmed.' },
  expiry_date: { failure: 'This document has expired.' },
  validity_period: { warning: 'Document validity period is unusually long or short.' },
  passport_number_binding: { critical: 'Printed document number does not match the machine-readable zone.' },
  viz_mrz_consistency: { warning: 'One or more printed fields do not match the machine-readable zone.' },
};

/**
 * Return a short, plain-language summary for a validation issue object
 * ({ severity, check, message }). Falls back to a generic 1-line summary
 * for any check/severity combination not explicitly mapped above.
 */
export function summarizeValidationIssue(issue) {
  const short = VALIDATION_ISSUE_SUMMARIES[issue?.check]?.[issue?.severity];
  if (short) return short;
  return issue?.severity === 'warning'
    ? 'Minor non-blocking notice recorded on this document.'
    : 'This document failed an official format or validity check.';
}
