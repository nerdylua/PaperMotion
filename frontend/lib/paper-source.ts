export type PaperSource =
    | { kind: "arxiv"; arxivId: string }
    | { kind: "pdf"; pdfUrl: string };

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

function isDirectPdfUrl(inputRaw: string): string | null {
    const input = inputRaw.trim();
    if (!input) return null;

    try {
        const parsed = new URL(input);
        if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
            return null;
        }
        const path = parsed.pathname.toLowerCase();
        if (path.endsWith(".pdf")) {
            return parsed.toString();
        }
        const combined = `${parsed.pathname}${parsed.search}`.toLowerCase();
        if (combined.includes(".pdf")) {
            return parsed.toString();
        }
    } catch {
        return null;
    }

    return null;
}

export function parsePaperSource(inputRaw: string): PaperSource | null {
    const arxivId = extractArxivId(inputRaw);
    if (arxivId) return { kind: "arxiv", arxivId };

    const pdfUrl = isDirectPdfUrl(inputRaw);
    if (pdfUrl) return { kind: "pdf", pdfUrl };

    return null;
}
