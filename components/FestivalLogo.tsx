"use client";

import { useState } from "react";

export function FestivalLogo({ slug, name, large = false }: { slug: string; name: string; large?: boolean }) {
  const [failed, setFailed] = useState(false);
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join("");
  return <div className={`festivalLogo ${large ? "large" : ""}`}>{failed ? <span>{initials}</span> : <img src={`/logos/${slug}.png`} alt={`${name} logo`} onError={() => setFailed(true)} />}</div>;
}
