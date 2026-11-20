import { CircleAlert, Info, TriangleAlert } from "lucide-react";
import type { Issue } from "../types";

const ICON = { error: CircleAlert, warning: TriangleAlert, info: Info };

export function IssuesList({ issues, onJump }: { issues: Issue[]; onJump: (line: number) => void }) {
  if (!issues.length) return null;
  return (
    <div className="issues">
      {issues.map((i, k) => {
        const Icon = ICON[i.severity];
        return (
          <div key={k} className="issue" onClick={() => i.line && onJump(i.line)} title={i.rule}>
            <Icon size={15} className={`sev-${i.severity}`} style={{ marginTop: 2, flexShrink: 0 }} />
            <span className="ln">{i.line ? `line ${i.line}` : "circuit"}</span>
            <span>{i.message}</span>
            <span className="src">{i.source === "gemma" ? "Gemma" : i.source === "lint" ? "lint" : "parser"}</span>
          </div>
        );
      })}
    </div>
  );
}
