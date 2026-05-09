export async function derivePdfPaperId(pdfUrl: string): Promise<string> {
    const normalized = pdfUrl.trim();
    if (!normalized) {
        throw new Error("PDF URL is required");
    }

    const data = new TextEncoder().encode(normalized);
    const digest = await crypto.subtle.digest("SHA-1", data);
    const bytes = Array.from(new Uint8Array(digest));
    const hex = bytes.map((b) => b.toString(16).padStart(2, "0")).join("");
    return `pdf_${hex.slice(0, 12)}`;
}
