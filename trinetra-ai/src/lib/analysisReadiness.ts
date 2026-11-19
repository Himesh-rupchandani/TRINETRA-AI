/** Health only gives a negative admission signal, not proof models work. */
export interface AnalysisHealth {
  vision?: { available?: boolean; reason?: string | null };
  resource_budget?: { allowed?: boolean; reason?: string | null };
}

export function analysisUnavailableReason(health: AnalysisHealth): string | null {
  if (health.vision?.available === false) {
    return health.vision.reason || 'Video analysis is unavailable: the backend vision stack is not ready.';
  }
  if (health.resource_budget?.allowed === false) {
    return health.resource_budget.reason || 'Video analysis is paused due to backend memory limits.';
  }
  return null;
}
