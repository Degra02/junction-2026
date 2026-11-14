import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";

export interface AnimatedNumberProps {
  readonly value: number;
  readonly format: (value: number) => string;
  readonly duration?: number;
  readonly className?: string;
}

/** Counts up from 0 to `value` once it mounts or changes; renders the final text for SSR/a11y. */
export function AnimatedNumber({ value, format, duration = 0.9, className }: Readonly<AnimatedNumberProps>) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduce) {
      el.textContent = format(value);
      return;
    }
    const controls = animate(0, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        el.textContent = format(v);
      },
    });
    return () => controls.stop();
  }, [value, format, duration, reduce]);

  return (
    <span ref={ref} className={className}>
      {format(value)}
    </span>
  );
}
