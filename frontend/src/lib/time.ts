/**
 * Time formatting helpers. The judge console renders timestamps in two
 * places: timeline rows (relative-or-time-of-day) and inspector panels
 * (absolute ISO-ish for forensic inspection).
 */

export function formatAbsolute(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, "Z");
  } catch {
    return iso;
  }
}

export function formatRelative(iso: string, now: Date = new Date()): string {
  try {
    const d = new Date(iso);
    const deltaMs = d.getTime() - now.getTime();
    const sec = Math.round(deltaMs / 1000);
    if (Math.abs(sec) < 60) return rtf(sec, "second");
    const minutes = Math.round(sec / 60);
    if (Math.abs(minutes) < 60) return rtf(minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return rtf(hours, "hour");
    const days = Math.round(hours / 24);
    return rtf(days, "day");
  } catch {
    return iso;
  }
}

const RTF = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
function rtf(n: number, unit: Intl.RelativeTimeFormatUnit): string {
  return RTF.format(n, unit);
}

export function formatHhMmSs(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString(undefined, { hour12: false });
  } catch {
    return iso;
  }
}
