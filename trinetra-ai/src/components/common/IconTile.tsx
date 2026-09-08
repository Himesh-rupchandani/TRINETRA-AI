/**
 * Compatibility shim — the demo-flow data module types its demo cards
 * with this tone union. The rebuilt UI no longer renders icon tiles,
 * but the engine file's type import must keep resolving.
 */
export type TileTone =
  | 'blue'
  | 'green'
  | 'purple'
  | 'orange'
  | 'brand'
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  | 'info'
  | 'online'
  | 'offline'
  | 'neutral';
