// Rehearsed demo point (backend/HANDOFF.md): on the usual start_1 → destination_2 path, so
// verifying an obstacle here visibly reroutes WalkLah (≈558 m → ≈681 m). Used only when
// VITE_DEMO_MODE=true, as a shortcut for the presenter; it never creates a report by itself.
export const DEMO_OBSTACLE = { latitude: 3.11916, longitude: 101.65565 } as const

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
