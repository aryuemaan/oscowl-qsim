export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
  return `${(100 * x).toFixed(digits)}%`;
}

export function bytes(x: number | null | undefined): string {
  if (x === null || x === undefined) return "n/a";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"];
  if (x < 1024) return `${x.toFixed(0)} B`;
  const k = Math.min(Math.floor(Math.log(x) / Math.log(1024)), units.length - 1);
  const v = x / 1024 ** k;
  if (k === units.length - 1 && v >= 1024) return `${x.toExponential(1)} B`;
  return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[k]}`;
}

export function ms(x: number): string {
  return x < 1000 ? `${x.toFixed(0)} ms` : `${(x / 1000).toFixed(2)} s`;
}

export function shortBits(s: string, max = 14): string {
  return s.length <= max ? s : `${s.slice(0, 6)}…${s.slice(-6)}`;
}
