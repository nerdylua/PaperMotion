# arXivisual Frontend

Next.js app for the arXivisual scrollytelling reader. It accepts arXiv IDs/URLs, DOIs, direct PDF URLs, and PDF uploads, then talks to the backend processing API or serves cached demo papers.

## Routes

- `/`: landing page and paper input modes.
- `/abs/[...id]`: processing state and card-stack paper reader.
- `/topic`: arXiv topic graph UI with SVG graph, paper snapshots, and explainer video.

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Configuration

- `NEXT_PUBLIC_API_URL`: backend base URL, defaults to `http://localhost:8000`.
- `NEXT_PUBLIC_USE_MOCK=true`: use mock API responses.

Demo paper IDs `1706.03762`, `2005.14165`, and `2303.08774` bypass the backend through `lib/mock-data.ts`.

## Checks

```bash
npm run lint
npm run build
```

## Notes

The active reader uses `components/CardStack.tsx` and `components/StackCard.tsx`. Markdown and math rendering are handled by `components/MarkdownContent.tsx`; video playback is handled by `components/VideoPlayer.tsx`.

Styling uses Tailwind CSS v4, Framer Motion, glassmorphism primitives, and `next-themes`.

