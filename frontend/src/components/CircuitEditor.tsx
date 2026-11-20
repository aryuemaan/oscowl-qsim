import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { Issue } from "../types";

const LINE_H = 20;

export interface EditorHandle {
  focusLine: (line: number) => void;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  issues: Issue[];
  focusLine: number | null;
}

// A lightweight code editor: textarea + line numbers + highlighted lines for issues and hotspots.
export const CircuitEditor = forwardRef<EditorHandle, Props>(function CircuitEditor({ value, onChange, issues, focusLine }, ref) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const [scroll, setScroll] = useState(0);
  const lineCount = useMemo(() => value.split("\n").length, [value]);

  const marks = useMemo(() => {
    const m = new Map<number, "error" | "warning">();
    for (const i of issues) {
      if (!i.line || i.severity === "info") continue;
      if (i.severity === "error" || !m.has(i.line)) m.set(i.line, i.severity);
    }
    return m;
  }, [issues]);

  useImperativeHandle(ref, () => ({
    focusLine(line: number) {
      const el = ta.current;
      if (!el) return;
      const lines = el.value.split("\n");
      const start = lines.slice(0, line - 1).reduce((a, l) => a + l.length + 1, 0);
      el.focus();
      el.setSelectionRange(start, start + (lines[line - 1]?.length ?? 0));
      el.scrollTop = Math.max(0, (line - 1) * LINE_H - el.clientHeight / 3);
    },
  }));

  const style = { transform: `translateY(${-scroll}px)` };
  return (
    <div className="editor">
      <div className="layer">
        <div className="layer-inner" style={style}>
          {[...marks.entries()].map(([line, sev]) => (
            <div key={`m${line}`} className={`hl ${sev}`} style={{ top: (line - 1) * LINE_H, height: LINE_H }} />
          ))}
          {focusLine && <div className="hl focus" style={{ top: (focusLine - 1) * LINE_H, height: LINE_H }} />}
          <div className="gutter">
            {Array.from({ length: lineCount }, (_, i) => (
              <div key={i} style={{ height: LINE_H }}>{i + 1}</div>
            ))}
          </div>
        </div>
      </div>
      <textarea
        ref={ta}
        value={value}
        spellCheck={false}
        wrap="off"
        aria-label="OpenQASM circuit"
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => setScroll(e.currentTarget.scrollTop)}
      />
    </div>
  );
});
