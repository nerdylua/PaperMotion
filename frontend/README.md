# PaperMotion Frontend

Next.js app for the PaperMotion scrollytelling reader. It accepts arXiv IDs/URLs, DOIs, direct PDF URLs, and PDF uploads, then talks to the backend processing API or serves cached demo papers.

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

## Checks

```bash
npm run lint
npm run build
```

## Notes

The active reader uses `components/CardStack.tsx` and `components/StackCard.tsx`. Markdown and math rendering are handled by `components/MarkdownContent.tsx`; video playback is handled by `components/VideoPlayer.tsx`.

Styling uses Tailwind CSS v4, Framer Motion, glassmorphism primitives, and `next-themes`.