"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { MosaicBackground } from "@/components/ui/mosaic-background";
import { ShardField } from "@/components/ui/glass-shard";
import { GlassCard } from "@/components/ui/glass-card";
import { VideoPlayer } from "@/components/VideoPlayer";
import {
    getTopicGraphStatus,
    startTopicGraphJob,
    type TopicGraphEdge,
    type TopicGraphNode,
    type TopicGraphMode,
} from "@/lib/api";

const POLL_MS = 1500;

function clampMax(value: number) {
    return Math.max(1, Math.min(5, value));
}

function buildPositions(nodes: TopicGraphNode[], size: number) {
    const count = nodes.length;
    const center = size / 2;
    const radius = size * 0.34;
    return nodes.map((node, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, count);
        return {
            id: node.id,
            x: center + Math.cos(angle) * radius,
            y: center + Math.sin(angle) * radius,
        };
    });
}

function truncateText(value: string, maxLen: number) {
    if (value.length <= maxLen) return value;
    return `${value.slice(0, maxLen - 3).trimEnd()}...`;
}

export default function TopicGraphPage() {
    const [topic, setTopic] = useState("");
    const [maxResults, setMaxResults] = useState(5);
    const [mode, setMode] = useState<TopicGraphMode>("explanation");
    const [jobId, setJobId] = useState<string | null>(null);
    const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
    const [progress, setProgress] = useState(0);
    const [currentStep, setCurrentStep] = useState<string | undefined>();
    const [error, setError] = useState<string | null>(null);
    const [nodes, setNodes] = useState<TopicGraphNode[]>([]);
    const [edges, setEdges] = useState<TopicGraphEdge[]>([]);
    const [videoUrl, setVideoUrl] = useState<string | undefined>();
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

    const positions = useMemo(() => buildPositions(nodes, 520), [nodes]);
    const positionMap = useMemo(() => {
        const map = new Map<string, { x: number; y: number }>();
        for (const pos of positions) map.set(pos.id, { x: pos.x, y: pos.y });
        return map;
    }, [positions]);

    const nodeMap = useMemo(() => {
        const map = new Map<string, TopicGraphNode>();
        for (const node of nodes) map.set(node.id, node);
        return map;
    }, [nodes]);

    const selectedNode = useMemo(() => {
        if (!nodes.length) return null;
        return nodes.find((node) => node.id === selectedNodeId) ?? nodes[0];
    }, [nodes, selectedNodeId]);

    useEffect(() => {
        if (!jobId || status !== "running") return;

        const timer = setInterval(async () => {
            try {
                const data = await getTopicGraphStatus(jobId);
                setProgress(data.progress ?? 0);
                setCurrentStep(data.current_step);

                if (data.status === "completed") {
                    setStatus("done");
                    setNodes(data.nodes ?? []);
                    setEdges(data.edges ?? []);
                    setVideoUrl(data.video_url);
                    clearInterval(timer);
                }

                if (data.status === "failed") {
                    setStatus("error");
                    setError(data.error || "Topic graph failed");
                    clearInterval(timer);
                }
            } catch (err) {
                setStatus("error");
                setError(err instanceof Error ? err.message : "Failed to fetch status");
                clearInterval(timer);
            }
        }, POLL_MS);

        return () => clearInterval(timer);
    }, [jobId, status]);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        if (!topic.trim()) {
            setError("Enter a topic to search");
            return;
        }

        setStatus("running");
        setProgress(0);
        setNodes([]);
        setEdges([]);
        setVideoUrl(undefined);

        try {
            const response = await startTopicGraphJob({
                topic: topic.trim(),
                max_results: clampMax(maxResults),
                mode,
            });
            setJobId(response.job_id);
            setCurrentStep("Queued for processing");
        } catch (err) {
            setStatus("error");
            setError(err instanceof Error ? err.message : "Failed to start job");
        }
    }

    return (
        <main className="min-h-dvh relative overflow-hidden bg-black">
            <MosaicBackground showLogo={false} />
            <ShardField />

            <div className="relative z-10 mx-auto w-full max-w-6xl px-6 py-16">
                <motion.header
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                    className="text-center"
                >
                    <p className="text-xs tracking-[0.35em] uppercase text-white/50">Topic Graph</p>
                    <h1 className="mt-3 text-4xl sm:text-5xl font-semibold text-white">
                        Map the paper landscape
                    </h1>
                    <p className="mt-4 text-white/50 max-w-2xl mx-auto">
                        Search arXiv by topic, build an embedding similarity graph, and generate a
                        Manim explainer video.
                    </p>
                </motion.header>

                <GlassCard className="mt-10 p-8">
                    <form onSubmit={onSubmit} className="grid gap-6 md:grid-cols-[1.3fr_0.7fr_0.7fr_auto]">
                        <div className="flex flex-col gap-2">
                            <label className="text-xs uppercase tracking-[0.2em] text-white/50">Topic</label>
                            <input
                                value={topic}
                                onChange={(e) => setTopic(e.target.value)}
                                placeholder="e.g., retrieval augmented generation"
                                className="rounded-xl bg-white/[0.06] border border-white/[0.12] px-4 py-3 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-white/30"
                            />
                        </div>

                        <div className="flex flex-col gap-2">
                            <label className="text-xs uppercase tracking-[0.2em] text-white/50">Max papers</label>
                            <input
                                type="number"
                                min={1}
                                max={5}
                                value={maxResults}
                                onChange={(e) => setMaxResults(Number(e.target.value))}
                                className="rounded-xl bg-white/[0.06] border border-white/[0.12] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30"
                            />
                        </div>

                        <div className="flex flex-col gap-2">
                            <label className="text-xs uppercase tracking-[0.2em] text-white/50">Mode</label>
                            <select
                                value={mode}
                                onChange={(e) => setMode(e.target.value as TopicGraphMode)}
                                className="rounded-xl bg-white/[0.06] border border-white/[0.12] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30"
                            >
                                <option value="explanation">Explanation</option>
                                <option value="comparison">Comparison</option>
                            </select>
                        </div>

                        <div className="flex items-end">
                            <button
                                type="submit"
                                className="w-full rounded-xl bg-white text-black px-6 py-3 text-xs uppercase tracking-[0.2em] font-semibold hover:bg-white/90"
                            >
                                Generate
                            </button>
                        </div>
                    </form>

                    {error && <p className="mt-4 text-sm text-[#f27066]">{error}</p>}

                    {status === "running" && (
                        <div className="mt-6 text-sm text-white/60">
                            <p>Progress: {(progress * 100).toFixed(0)}%</p>
                            {currentStep && <p className="mt-1">{currentStep}</p>}
                        </div>
                    )}
                </GlassCard>

                {(nodes.length > 0 || status === "done") && (
                    <div className="mt-12 grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
                        <GlassCard className="p-6">
                            <h2 className="text-lg font-semibold text-white">Similarity graph</h2>
                            <div className="mt-4 rounded-2xl bg-black/40 border border-white/[0.08] p-4">
                                <svg viewBox="0 0 520 520" className="mx-auto block h-[420px] w-full">
                                    <defs>
                                        <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
                                            <stop offset="0%" stopColor="#7dd19b" stopOpacity="0.9" />
                                            <stop offset="100%" stopColor="#7dd19b" stopOpacity="0.1" />
                                        </radialGradient>
                                    </defs>

                                    {edges.map((edge, idx) => {
                                        const source = positionMap.get(edge.source);
                                        const target = positionMap.get(edge.target);
                                        if (!source || !target) return null;
                                        const opacity = Math.max(0.2, Math.min(0.9, edge.weight));
                                        return (
                                            <line
                                                key={`${edge.source}-${edge.target}-${idx}`}
                                                x1={source.x}
                                                y1={source.y}
                                                x2={target.x}
                                                y2={target.y}
                                                stroke={`rgba(125, 209, 155, ${opacity})`}
                                                strokeWidth={1.5}
                                            />
                                        );
                                    })}

                                    {positions.map((pos) => {
                                        const node = nodeMap.get(pos.id);
                                        const isActive = node?.id === selectedNode?.id;
                                        const label = node ? truncateText(node.title, 18) : pos.id;
                                        return (
                                            <g
                                                key={pos.id}
                                                onClick={() => node && setSelectedNodeId(node.id)}
                                                style={{ cursor: node ? "pointer" : "default" }}
                                            >
                                                <title>{node?.title ?? pos.id}</title>
                                                <circle
                                                    cx={pos.x}
                                                    cy={pos.y}
                                                    r={isActive ? 22 : 18}
                                                    fill="url(#nodeGlow)"
                                                    stroke={
                                                        isActive
                                                            ? "rgba(255,255,255,0.9)"
                                                            : "rgba(255,255,255,0.5)"
                                                    }
                                                    strokeWidth={isActive ? 1.6 : 1}
                                                />
                                                <text
                                                    x={pos.x}
                                                    y={pos.y + 34}
                                                    textAnchor="middle"
                                                    fontSize={10}
                                                    fill={
                                                        isActive
                                                            ? "rgba(255,255,255,0.9)"
                                                            : "rgba(255,255,255,0.7)"
                                                    }
                                                >
                                                    <tspan x={pos.x}>{pos.id}</tspan>
                                                    {node && (
                                                        <tspan x={pos.x} dy={12}>
                                                            {label}
                                                        </tspan>
                                                    )}
                                                </text>
                                            </g>
                                        );
                                    })}
                                </svg>
                            </div>
                        </GlassCard>

                        <div className="grid gap-6">
                            {selectedNode && (
                                <GlassCard className="p-6">
                                    <h2 className="text-lg font-semibold text-white">Paper snapshot</h2>
                                    <div className="mt-4 space-y-4 text-sm text-white/70">
                                        <p className="text-base text-white font-medium">
                                            {selectedNode.title}
                                        </p>
                                        <p className="text-xs text-white/40">
                                            {selectedNode.authors.join(", ")}
                                        </p>
                                        {selectedNode.abstract_animation_url && (
                                            <VideoPlayer
                                                src={selectedNode.abstract_animation_url}
                                                title="Abstract snapshot"
                                            />
                                        )}
                                        {!selectedNode.abstract_animation_url &&
                                            selectedNode.abstract_animation_error && (
                                                <p className="rounded-lg border border-[#f27066]/20 bg-[#f27066]/10 px-3 py-2 text-xs text-[#f27066]">
                                                    Snapshot animation could not be rendered.
                                                </p>
                                            )}
                                        {selectedNode.abstract_summary && (
                                            <div>
                                                <p className="text-xs uppercase tracking-[0.2em] text-white/35">
                                                    Brief read
                                                </p>
                                                <p className="mt-2 text-sm text-white/65 leading-relaxed">
                                                    {selectedNode.abstract_summary}
                                                </p>
                                            </div>
                                        )}
                                        {(selectedNode.abstract_key_points?.length ?? 0) > 0 && (
                                            <div>
                                                <p className="text-xs uppercase tracking-[0.2em] text-white/35">
                                                    Key points
                                                </p>
                                                <ul className="mt-2 space-y-2">
                                                    {(selectedNode.abstract_key_points ?? []).map((point, index) => (
                                                        <li
                                                            key={`${selectedNode.id}-point-${index}`}
                                                            className="text-sm text-white/60 leading-relaxed"
                                                        >
                                                            {point}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                        <p className="text-sm text-white/60 leading-relaxed">
                                            {selectedNode.abstract}
                                        </p>
                                        <div className="flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.2em] text-white/40">
                                            {selectedNode.categories.map((cat) => (
                                                <span
                                                    key={cat}
                                                    className="rounded-full border border-white/[0.12] px-2 py-1"
                                                >
                                                    {cat}
                                                </span>
                                            ))}
                                        </div>
                                        <a
                                            href={`https://arxiv.org/abs/${selectedNode.id}`}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-[#7dd19b]"
                                        >
                                            Open arXiv
                                        </a>
                                    </div>
                                </GlassCard>
                            )}
                            <GlassCard className="p-6">
                                <h2 className="text-lg font-semibold text-white">Papers</h2>
                                <div className="mt-4 grid gap-4">
                                    {nodes.map((node) => (
                                        <div
                                            key={node.id}
                                            onClick={() => setSelectedNodeId(node.id)}
                                            className={
                                                node.id === selectedNode?.id
                                                    ? "rounded-xl border border-white/40 bg-white/[0.08] p-4"
                                                    : "rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 hover:border-white/30 hover:bg-white/[0.06]"
                                            }
                                        >
                                            <p className="text-sm text-white/70 font-medium">{node.title}</p>
                                            <p className="mt-2 text-xs text-white/40">
                                                {node.authors.slice(0, 3).join(", ")}
                                                {node.authors.length > 3 ? " et al" : ""}
                                            </p>
                                            <a
                                                href={`https://arxiv.org/abs/${node.id}`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="mt-2 inline-block text-xs uppercase tracking-[0.2em] text-[#7dd19b]"
                                            >
                                                Open arXiv
                                            </a>
                                        </div>
                                    ))}
                                </div>
                            </GlassCard>

                            {videoUrl && (
                                <GlassCard className="p-6">
                                    <h2 className="text-lg font-semibold text-white">Explainer video</h2>
                                    <VideoPlayer src={videoUrl} className="mt-4" />
                                </GlassCard>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </main>
    );
}
