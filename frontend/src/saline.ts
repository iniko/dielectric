// NaCl saline molarity ↔ mass-% conversion (linear), mirroring dielectric/reference/liquids.py.
// Physiological anchor: 0.154 mol/L ≡ 0.9 % w/w NaCl. Good for the dilute saline used in validation.
const PHYSIOLOGICAL_MOLARITY = 0.154;
const PHYSIOLOGICAL_MASS_PCT = 0.9;

export function massPercentFromMolarity(molarity: number): number {
  return (molarity / PHYSIOLOGICAL_MOLARITY) * PHYSIOLOGICAL_MASS_PCT;
}

export function molarityFromMassPercent(massPct: number): number {
  return (massPct / PHYSIOLOGICAL_MASS_PCT) * PHYSIOLOGICAL_MOLARITY;
}
