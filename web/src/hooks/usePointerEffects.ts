import { useEffect, type RefObject } from "react";

/**
 * One document-level pointer listener for the cursor effects:
 * - `[data-spotlight]` under the pointer gets `--x`/`--y` (pointer position inside it);
 * - the backdrop gets `--mx`/`--my` (viewport position) for the lagging glow.
 * Fine pointers only; nothing runs for touch or reduced motion.
 */
export function usePointerEffects(backdropRef: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!fine.matches || reduced.matches) return;

    let frame = 0;
    let last: PointerEvent | null = null;

    const flush = () => {
      frame = 0;
      const ev = last;
      if (!ev) return;
      const backdrop = backdropRef.current;
      if (backdrop) {
        backdrop.style.setProperty("--mx", `${ev.clientX}px`);
        backdrop.style.setProperty("--my", `${ev.clientY}px`);
        backdrop.dataset.pointer = "on";
      }
      const target = ev.target instanceof Element ? ev.target.closest<HTMLElement>("[data-spotlight]") : null;
      if (target) {
        const rect = target.getBoundingClientRect();
        target.style.setProperty("--x", `${ev.clientX - rect.left}px`);
        target.style.setProperty("--y", `${ev.clientY - rect.top}px`);
      }
    };

    const onMove = (ev: PointerEvent) => {
      if (ev.pointerType !== "mouse") return;
      last = ev;
      if (!frame) frame = requestAnimationFrame(flush);
    };

    const onLeave = () => {
      const backdrop = backdropRef.current;
      if (backdrop) backdrop.dataset.pointer = "off";
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [backdropRef]);
}
