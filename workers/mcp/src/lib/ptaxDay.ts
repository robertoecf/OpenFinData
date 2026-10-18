/**
 * Why a PTAX day can come back empty.
 *
 * Kept free of imports so it loads under `node --test` without pulling the
 * worker's JSON catalogs, which need import attributes Node requires and
 * esbuild does not.
 */

/** Brazil has no DST, so BRT is a fixed UTC-3 offset. */
export function brtNow(nowMs: number = Date.now()): { date: string; hour: number } {
  const brt = new Date(nowMs - 3 * 60 * 60 * 1000);
  return { date: brt.toISOString().slice(0, 10), hour: brt.getUTCHours() };
}

/**
 * PTAX has no quote on weekends, holidays, future dates, or before the
 * closing rate is published (~13h BRT). An empty array alone makes those
 * indistinguishable, so say which one it was.
 */
export function emptyDayReason(
  day: string,
  nowMs: number = Date.now(),
): { reason: string; note: string } {
  const dow = new Date(`${day}T12:00:00Z`).getUTCDay();
  if (dow === 0 || dow === 6) {
    return {
      reason: "non_business_day",
      note: `${day} is a weekend; PTAX is published on business days only`,
    };
  }
  const now = brtNow(nowMs);
  if (day > now.date) {
    return { reason: "future_date", note: `${day} is in the future; today in BRT is ${now.date}` };
  }
  if (day === now.date && now.hour < 13) {
    return {
      reason: "not_published_yet",
      note: `it is ${String(now.hour).padStart(2, "0")}h BRT and the closing PTAX for ${day} is normally published around 13h, so it may not be out yet; a holiday would also leave it empty`,
    };
  }
  return { reason: "no_quote_for_date", note: `no PTAX for ${day}; most likely a national holiday` };
}
