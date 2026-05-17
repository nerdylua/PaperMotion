"use client";

import React, { useId, useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

function seededRandom(seed: number) {
  const value = Math.sin(seed * 12.9898) * 43758.5453;
  return value - Math.floor(value);
}

interface SparklesProps {
  className?: string;
  size?: number;
  minSize?: number | null;
  density?: number;
  speed?: number;
  minSpeed?: number | null;
  opacity?: number;
  direction?: "top" | "bottom" | "left" | "right";
  opacitySpeed?: number;
  minOpacity?: number | null;
  color?: string;
  mousemove?: boolean;
  hover?: boolean;
  background?: string;
  options?: Record<string, unknown>;
}

export const SparklesCore = ({
  className,
  background = "transparent",
  minSize = 0.4,
  size = 1,
  speed = 1,
  direction = "top",
  color = "#FFF",
  density = 100,
}: SparklesProps) => {
  const id = useId();
  
  const sparkles = useMemo(() => {
    return Array.from({ length: density }, (_, i) => ({
      id: i,
      x: seededRandom(i + 1) * 100,
      y: seededRandom(i + 101) * 100,
      size: seededRandom(i + 201) * (size - (minSize ?? 0.4)) + (minSize ?? 0.4),
      duration: seededRandom(i + 301) * 2 + 1,
      delay: seededRandom(i + 401) * 2,
    }));
  }, [density, size, minSize]);

  const getDirectionValues = () => {
    switch (direction) {
      case "top":
        return { y: [0, -100] };
      case "bottom":
        return { y: [0, 100] };
      case "left":
        return { x: [0, -100] };
      case "right":
        return { x: [0, 100] };
      default:
        return { y: [0, -100] };
    }
  };

  return (
    <div
      className={cn("relative overflow-hidden", className)}
      style={{ background }}
    >
      {sparkles.map((sparkle) => (
        <motion.span
          key={`${id}-${sparkle.id}`}
          className="absolute rounded-full"
          style={{
            left: `${sparkle.x}%`,
            top: `${sparkle.y}%`,
            width: sparkle.size,
            height: sparkle.size,
            backgroundColor: color,
            boxShadow: `0 0 ${sparkle.size * 2}px ${color}`,
          }}
          animate={{
            opacity: [0, 1, 0],
            scale: [0, 1, 0],
            ...getDirectionValues(),
          }}
          transition={{
            duration: sparkle.duration / speed,
            repeat: Infinity,
            delay: sparkle.delay,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
};
