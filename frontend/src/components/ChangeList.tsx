import type { ReactElement } from "react";
import type { AnalysisItem, ChangeRegion } from "../api/types";
import { ChangeCard } from "./ChangeCard";

interface Group {
  key: string;
  title: string;
  regions: ChangeRegion[];
}

/** Groups by section title when the server sent one (redacted for anonymous), else by page. */
function group(regions: ChangeRegion[]): Group[] {
  const groups = new Map<string, Group>();
  for (const r of regions) {
    const page = r.cand_page ?? r.ref_page;
    const title = r.section_title ?? (page != null ? `Page ${page + 1}` : "Other changes");
    const key = r.section_title ? `s:${r.section_id ?? r.section_title}` : `p:${title}`;
    const existing = groups.get(key);
    if (existing) existing.regions.push(r);
    else groups.set(key, { key, title, regions: [r] });
  }
  return [...groups.values()];
}

export function ChangeList({
  regions,
  analysis,
  selectedId,
  onSelect,
}: {
  regions: ChangeRegion[];
  analysis: AnalysisItem[] | null;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}): ReactElement {
  if (regions.length === 0) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        No individual changes were located.
      </p>
    );
  }
  const byRegion = new Map((analysis ?? []).map((a) => [a.region_id, a]));
  return (
    <div className="space-y-4">
      {group(regions).map((g) => (
        <section key={g.key} aria-label={g.title}>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {g.title}
          </h4>
          <ul className="space-y-2">
            {g.regions.map((r) => (
              <ChangeCard
                key={r.id}
                region={r}
                analysis={byRegion.get(r.id)}
                selected={r.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
