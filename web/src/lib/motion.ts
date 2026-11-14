import type { Transition } from "motion/react";

/**
 * Material 3 Expressive-inspired motion tokens:
 * - Spatial springs govern layout, size, drawer, and card position changes (subtle physical overshoot).
 * - Effect curves govern opacity, color, and highlight transitions (no overshoot).
 */
export const SPATIAL_SPRING: Transition = {
  type: "spring",
  stiffness: 380,
  damping: 32,
  mass: 0.85,
};

export const SNAPPY_SPRING: Transition = {
  type: "spring",
  stiffness: 520,
  damping: 36,
  mass: 0.7,
};

export const GENTLE_SPRING: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 28,
  mass: 0.95,
};

export const EFFECT_TRANSITION: Transition = {
  duration: 0.18,
  ease: [0.2, 0, 0, 1],
};
