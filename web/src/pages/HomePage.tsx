import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { AnalysisInputForm, type PrefillValue } from "../components/AnalysisInputForm";
import { RecentAnalyses } from "../components/RecentAnalyses";
import { GENTLE_SPRING } from "../lib/motion";

export type HomePageProps = Record<string, never>;

const HEADLINE = "Read between the lines, and across the web.";

export function HomePage(_props: Readonly<HomePageProps>) {
  const [searchParams] = useSearchParams();
  const [prefill, setPrefill] = useState<PrefillValue | null>(null);

  useEffect(() => {
    const imageParam = searchParams.get("image")?.trim() ?? "";
    const urlParam = searchParams.get("url")?.trim() ?? "";
    const textParam = searchParams.get("text")?.trim() ?? "";
    const contextUrlParam = searchParams.get("context_url")?.trim() ?? "";
    const langParam = searchParams.get("lang")?.trim() ?? "";
    const autorun = searchParams.get("autorun") === "1" || searchParams.get("autorun") === "true";

    if (imageParam) {
      setPrefill({
        value: imageParam,
        kind: "image",
        contextUrl: contextUrlParam || undefined,
        lang: langParam || undefined,
        autoSubmit: autorun,
        nonce: 3,
      });
    } else if (urlParam) {
      setPrefill({
        value: urlParam,
        kind: "url",
        contextUrl: contextUrlParam || undefined,
        lang: langParam || undefined,
        autoSubmit: autorun,
        nonce: 1,
      });
    } else if (textParam) {
      setPrefill({
        value: textParam,
        kind: "text",
        contextUrl: contextUrlParam || undefined,
        lang: langParam || undefined,
        autoSubmit: autorun,
        nonce: 2,
      });
    }
  }, [searchParams]);

  return (
    <div className="max-w-[680px] mx-auto pt-[6vh] sm:pt-[10vh] pb-10 space-y-10">
      <div className="space-y-4 text-center">
        <h1 className="display text-[40px] sm:text-[54px] leading-[1.04] text-[var(--fg-primary)]">
          {HEADLINE.split(" ").map((word, i) => (
            <motion.span
              key={`${word}-${i}`}
              initial={{ opacity: 0, y: 8, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)", transitionEnd: { filter: "none" } }}
              transition={{ ...GENTLE_SPRING, delay: 0.04 * i }}
              className="inline-block whitespace-pre"
            >
              {i === 0 ? word : ` ${word}`}
            </motion.span>
          ))}
        </h1>
        <motion.p
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...GENTLE_SPRING, delay: 0.35 }}
          className="text-[15px] text-[var(--fg-secondary)]"
        >
          Paste a link, text, or drop a meme. Every score comes with its sources.
        </motion.p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...GENTLE_SPRING, delay: 0.45 }}
        className="space-y-8"
      >
        <AnalysisInputForm prefill={prefill} />
        <RecentAnalyses />
        <p className="text-center">
          <Link
            to="/extension"
            className="text-xs text-[var(--fg-muted)] hover:text-[var(--fg-primary)] transition-colors"
          >
            Check any page, post, or meme with the browser extension →
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
