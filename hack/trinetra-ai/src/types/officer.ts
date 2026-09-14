/**
 * Police officer profile shown in the Profile section.
 *
 * Every figure is scoped to a single officer. The backend/mock is responsible
 * for returning only the requesting officer's own data — figures for different
 * officers are never mixed.
 */
export interface OfficerProfile {
  /** Stable identifier for the officer. */
  officerId: string;
  name: string;
  /** Profile photo URL (served from the public asset bundle). */
  photoUrl: string;
  /** Police ID / badge number, e.g. "GJ-02471". */
  policeId: string;
  department: string;
  designation: string;
  /** Total unique vehicles caught/detected by this officer. */
  vehiclesCaught: number;
  /** Total number of challans issued by this officer. */
  totalChallans: number;
  /** Sum of the face value of every challan issued by this officer. */
  totalChallanAmount: number;
  /** Amount actually collected from this officer's challans so far. */
  totalAmountCollected: number;
  /** Revenue collected from fully-paid challans belonging to this officer. */
  netRevenue: number;
  /** Unique vehicle number plates associated with this officer. */
  plates: string[];
}
