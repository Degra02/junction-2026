import type { ReactNode } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Info } from "lucide-react";

export interface HintProps {
  /** What the tooltip says: one or two short sentences. */
  readonly content: ReactNode;
  /** The element the tooltip explains; it must accept a ref and focus (button, tag with tabIndex). */
  readonly children: ReactNode;
  readonly side?: "top" | "bottom" | "left" | "right";
}

/** Help in context: a short explanation on hover or keyboard focus. */
export function Hint({ content, children, side = "top" }: Readonly<HintProps>) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          collisionPadding={12}
          className="z-50 glass-popover rounded-lg px-2.5 py-1.5 max-w-[280px] text-xs leading-relaxed text-[var(--fg-primary)]"
        >
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

/** A small (i) button that explains the thing next to it. */
export function InfoHint({ label, content }: Readonly<{ label: string; content: ReactNode }>) {
  return (
    <Hint content={content}>
      <button
        type="button"
        aria-label={label}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[var(--fg-muted)] hover:text-[var(--fg-primary)] cursor-help"
      >
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </Hint>
  );
}
