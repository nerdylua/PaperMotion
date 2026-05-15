"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { PlaceholdersAndVanishInput } from "@/components/ui/placeholders-and-vanish-input";
import { MosaicBackground } from "@/components/ui/mosaic-background";
import { ShardField } from "@/components/ui/glass-shard";
import { GlassCard } from "@/components/ui/glass-card";
import { processPaper, processPdfUpload } from "@/lib/api";

const DEMO_PAPER_IDS = new Set(["1706.03762", "2005.14165", "2303.08774"]);

function extractArxivId(inputRaw: string): string | null {
  const input = inputRaw.trim();
  if (!input) return null;

  const directNew = input.match(/^\d{4}\.\d{4,5}(v\d+)?$/i);
  if (directNew) return directNew[0];

  const directOld = input.match(/^[a-z-]+(\.[a-z]{2})?\/\d{7}(v\d+)?$/i);
  if (directOld) return directOld[0];

  const urlAbs = input.match(/arxiv\.org\/abs\/([^?\s#]+)/i);
  if (urlAbs?.[1]) return decodeURIComponent(urlAbs[1]).replace(/\/$/, "");

  const urlPdf = input.match(/arxiv\.org\/pdf\/([^?\s#]+?)(?:\.pdf)?$/i);
  if (urlPdf?.[1]) return decodeURIComponent(urlPdf[1]).replace(/\/$/, "");

  return null;
}

function extractDoi(inputRaw: string): string | null {
  const input = inputRaw.trim();
  if (!input) return null;
  const cleaned = input
    .replace(/^doi:\s*/i, "")
    .replace(/^https?:\/\/doi\.org\//i, "")
    .replace(/^https?:\/\/dx\.doi\.org\//i, "");
  const match = cleaned.match(/(10\.\d{4,9}\/[-._;()/:A-Z0-9]+)/i);
  return match ? match[1].toLowerCase() : null;
}

function extractPdfUrl(inputRaw: string): string | null {
  const input = inputRaw.trim();
  if (!input) return null;
  try {
    const url = new URL(input);
    const lower = url.pathname.toLowerCase();
    if (lower.endsWith(".pdf") || lower.includes(".pdf")) {
      return url.toString();
    }
  } catch {
    return null;
  }
  return null;
}

type InputMode = "arxiv" | "doi" | "pdf_url" | "pdf_upload";

const placeholdersByMode: Record<InputMode, string[]> = {
  arxiv: [
    "Paste an arXiv URL or ID...",
    "1706.03762 (Attention Is All You Need)",
    "https://arxiv.org/abs/2005.14165",
    "2303.08774 (GPT-4 Technical Report)",
    "1810.04805 (BERT)",
  ],
  doi: [
    "Paste a DOI or DOI URL...",
    "10.1145/3366423.3380224",
    "https://doi.org/10.1145/3366423.3380224",
  ],
  pdf_url: [
    "Paste a direct PDF URL...",
    "https://example.org/paper.pdf",
  ],
  pdf_upload: ["Upload a PDF file"],
};

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState<InputMode>("arxiv");
  const [value, setValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const parsedValue = useMemo(() => {
    if (mode === "arxiv") return extractArxivId(value);
    if (mode === "doi") return extractDoi(value);
    if (mode === "pdf_url") return extractPdfUrl(value);
    return null;
  }, [mode, value]);

  const canSubmit = mode === "pdf_upload" ? Boolean(file) : Boolean(parsedValue);

  async function onSubmit(e?: React.SyntheticEvent) {
    e?.preventDefault();
    setTouched(true);
    setError(null);
    if (!canSubmit) return;

    if (mode === "arxiv" && parsedValue && DEMO_PAPER_IDS.has(parsedValue)) {
      router.push(`/abs/${encodeURIComponent(parsedValue)}`);
      return;
    }

    setIsSubmitting(true);
    try {
      let response;
      if (mode === "pdf_upload" && file) {
        response = await processPdfUpload(file, file.name);
      } else if (mode === "arxiv" && parsedValue) {
        response = await processPaper({ source_type: "arxiv", arxiv_id: parsedValue });
      } else if (mode === "doi" && parsedValue) {
        response = await processPaper({ source_type: "doi", doi: parsedValue });
      } else if (mode === "pdf_url" && parsedValue) {
        response = await processPaper({ source_type: "pdf_url", pdf_url: parsedValue });
      }

      if (!response) {
        setError("Could not start processing. Please try again.");
        return;
      }

      const target = `/abs/${encodeURIComponent(response.paper_id)}?jobId=${encodeURIComponent(response.job_id)}`;
      router.push(target);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to start processing";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-dvh relative overflow-hidden bg-black">
      {/* Mosaic background with arXiv logo */}
      <MosaicBackground showLogo logoYFraction={0.20} />

      {/* Floating glass shards */}
      <ShardField />

      <div className="relative z-10 mx-auto w-full max-w-6xl px-6">
        {/* ── First viewport: Logo (clear) + search bar below ── */}
        <section className="min-h-dvh flex flex-col">
          {/* Spacer — keeps the logo area clear */}
          <div className="flex-1" />

          {/* Search area — pinned to lower portion of viewport */}
          <div className="max-w-4xl mx-auto w-full text-center pb-16 sm:pb-24">
            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.5 }}
              className="text-lg sm:text-xl text-white/40 max-w-2xl mx-auto leading-relaxed font-light"
            >
              Paste any arXiv, DOI, or PDF. Watch as it turns complex papers
              into digestible and <span className="text-white/60 font-medium">visually</span> appealing video explanations.
            </motion.p>

            {/* Input Section */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.8 }}
              className="mt-10 max-w-xl mx-auto"
            >
              <div className="relative">
                {/* Input mode toggle */}
                <div className="mb-4 flex flex-wrap items-center justify-center gap-2">
                  {([
                    { id: "arxiv", label: "arXiv" },
                    { id: "doi", label: "DOI" },
                    { id: "pdf_url", label: "PDF URL" },
                    { id: "pdf_upload", label: "Upload PDF" },
                  ] as const).map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => {
                        setMode(option.id);
                        setValue("");
                        setFile(null);
                        setTouched(false);
                        setError(null);
                      }}
                      className={
                        option.id === mode
                          ? "rounded-full bg-white/[0.14] px-4 py-1.5 text-xs uppercase tracking-widest text-white/80 border border-white/[0.25]"
                          : "rounded-full bg-white/[0.05] px-4 py-1.5 text-xs uppercase tracking-widest text-white/40 border border-white/[0.10] hover:text-white/60 hover:border-white/[0.18]"
                      }
                    >
                      {option.label}
                    </button>
                  ))}
                </div>

                {/* Decorative brackets */}
                <div className="absolute -left-4 top-1/2 -translate-y-1/2 text-3xl text-white/10 font-light select-none hidden sm:block">
                  [
                </div>
                <div className="absolute -right-4 top-1/2 -translate-y-1/2 text-3xl text-white/10 font-light select-none hidden sm:block">
                  ]
                </div>

                {mode === "pdf_upload" ? (
                  <div className="space-y-4">
                    <label className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-white/20 bg-white/[0.03] px-6 py-8 text-white/60 transition hover:border-white/40">
                      <input
                        type="file"
                        accept="application/pdf"
                        className="hidden"
                        onChange={(event) => {
                          const next = event.target.files?.[0] || null;
                          setFile(next);
                          setTouched(true);
                        }}
                      />
                      <span className="text-sm uppercase tracking-[0.2em]">Select PDF</span>
                      <span className="text-xs text-white/40">
                        {file ? file.name : "Only PDF files, up to 25 MB"}
                      </span>
                    </label>
                    <button
                      type="button"
                      onClick={onSubmit}
                      disabled={!canSubmit || isSubmitting}
                      className="w-full rounded-2xl bg-white/[0.08] px-6 py-3 text-xs uppercase tracking-[0.2em] text-white/70 border border-white/[0.15] transition hover:bg-white/[0.14] hover:text-white/90 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSubmitting ? "Starting..." : "Start Processing"}
                    </button>
                  </div>
                ) : (
                  <PlaceholdersAndVanishInput
                    placeholders={placeholdersByMode[mode]}
                    value={value}
                    onChange={(e) => {
                      setValue(e.target.value);
                      setTouched(true);
                    }}
                    onSubmit={onSubmit}
                    disabled={isSubmitting || (!canSubmit && touched && value.length > 0)}
                  />
                )}
              </div>

              {/* Status feedback */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.0 }}
                className="mt-4 h-6 text-sm"
              >
                {error ? (
                  <span className="text-[#f27066]">{error}</span>
                ) : mode === "pdf_upload" ? (
                  file ? (
                    <span className="text-[#7dd19b] flex items-center justify-center gap-2">
                      <span className="text-lg">✓</span>
                      <span>Selected:</span>
                      <span className="font-mono bg-[#7dd19b]/10 px-2 py-0.5 rounded">{file.name}</span>
                    </span>
                  ) : touched ? (
                    <span className="text-[#f27066]">Choose a PDF to upload</span>
                  ) : null
                ) : parsedValue ? (
                  <span className="text-[#7dd19b] flex items-center justify-center gap-2">
                    <span className="text-lg">✓</span>
                    <span>Detected:{" "}</span>
                    <span className="font-mono bg-[#7dd19b]/10 px-2 py-0.5 rounded">{parsedValue}</span>
                  </span>
                ) : touched && value ? (
                  <span className="text-[#f27066]">
                    Enter a valid {mode === "doi" ? "DOI" : mode === "pdf_url" ? "PDF URL" : "arXiv URL or ID"}
                  </span>
                ) : null}
              </motion.div>
            </motion.div>

            {/* Quick Examples */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 1.2 }}
              className="mt-8 flex flex-wrap items-center justify-center gap-3"
            >
              <span className="text-sm text-white/30">Try these:</span>
              {[
                { id: "1706.03762", label: "Transformers", icon: "◇" },
                { id: "2005.14165", label: "GPT-3", icon: "◈" },
                { id: "2303.08774", label: "GPT-4", icon: "◆" },
              ].map((example) => (
                <motion.div
                  key={example.id}
                  whileHover={{ scale: 1.05, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Link
                    href={`/abs/${encodeURIComponent(example.id)}`}
                    prefetch={false}
                    className="group block rounded-xl bg-white/[0.04] px-4 py-2.5 text-sm border border-white/[0.08] transition-all hover:bg-white/[0.07] hover:border-white/[0.14]"
                  >
                  <span className="text-white/40 mr-2">{example.icon}</span>
                  <span className="text-white/60 font-mono">{example.id}</span>
                  <span className="text-white/30 ml-2">({example.label})</span>
                  </Link>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </section>

        {/* Pro Tip Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 2.2 }}
          className="mt-20 max-w-2xl mx-auto"
        >
          <GlassCard spotlight className="p-8">
            <div className="flex items-center gap-4 mb-4">
              <div className="h-12 w-12 rounded-xl bg-white/[0.06] flex items-center justify-center border border-white/[0.10]">
                <div
                  className="h-4 w-4 bg-gradient-to-br from-white/50 to-white/20"
                  style={{ clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" }}
                />
              </div>
              <div>
                <h3 className="font-semibold text-white/90">Pro Tip</h3>
                <p className="text-sm text-white/40">One edit turns arXiv into arXivisual</p>
              </div>
            </div>
            <div className="space-y-3 text-sm text-white/45 leading-relaxed">
              <p>
                If your link starts with{" "}
                <code className="text-white/60 bg-white/[0.06] px-1.5 py-0.5 rounded text-xs font-mono">
                  arxiv.org
                </code>
                , just add{" "}
                <code className="text-white/60 bg-white/[0.06] px-1.5 py-0.5 rounded text-xs font-mono">
                  isual
                </code>
                {" "}after{" "}
                <code className="text-white/60 bg-white/[0.06] px-1.5 py-0.5 rounded text-xs font-mono">
                  arxiv
                </code>
                .
              </p>
              <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                <p className="font-mono text-xs text-white/50">
                  Before: arxiv.org/abs/1706.03762
                </p>
                <p className="font-mono text-xs text-white/70 mt-1">
                  After:&nbsp;&nbsp;arxivisual.org/abs/1706.03762
                </p>
              </div>
            </div>
          </GlassCard>
        </motion.div>

        {/* Footer */}
        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 2.4 }}
          className="mt-20 flex flex-col items-center justify-between gap-4 border-t border-white/[0.06] pt-8 text-sm sm:flex-row"
        >
          <div className="flex items-center gap-3 text-white/30">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              className="h-3 w-3 bg-gradient-to-br from-white/30 to-white/10"
              style={{ clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" }}
            />
            <span>Visualizing mathematics, one paper at a time</span>
          </div>
          <div className="flex items-center gap-4">
            <a
              className="rounded-lg px-3 py-1.5 text-white/40 border border-white/[0.06] transition hover:bg-white/[0.04] hover:text-white/60 hover:border-white/[0.12]"
              href="https://arxiv.org"
              target="_blank"
              rel="noreferrer"
            >
              arXiv
            </a>
            <a
              className="rounded-lg px-3 py-1.5 text-white/40 border border-white/[0.06] transition hover:bg-white/[0.04] hover:text-white/60 hover:border-white/[0.12]"
              href="https://www.manim.community/"
              target="_blank"
              rel="noreferrer"
            >
              Manim
            </a>
            <a
              className="rounded-lg px-3 py-1.5 text-white/40 border border-white/[0.06] transition hover:bg-white/[0.04] hover:text-white/60 hover:border-white/[0.12]"
              href="https://www.3blue1brown.com/"
              target="_blank"
              rel="noreferrer"
            >
              3Blue1Brown
            </a>
          </div>
        </motion.footer>
      </div>
    </main>
  );
}
