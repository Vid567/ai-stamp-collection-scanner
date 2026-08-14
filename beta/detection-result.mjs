// Each detected physical stamp remains a separate inventory candidate.
// Similarity may be reported later, but must never silently reduce row counts.
export function regionsToPhysicalStampGroups(regions) {
  return regions.map(region => ({...region, quantity: 1, matches: [region]}));
}
