/** Format an instant in the workspace timezone for a datetime-local control. */
export function appointmentInputTime(value: string | Date, timeZone = 'Asia/Kolkata'): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}

function workspaceWallTime(value: string, timeZone: string): Date {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    throw new Error('Enter valid appointment times.');
  }
  const wallTime = Date.parse(`${value}:00Z`);
  if (!Number.isFinite(wallTime)) throw new Error('Enter valid appointment times.');
  let instant = wallTime;
  // Resolve the zone offset at the requested wall time, including DST changes.
  for (let attempt = 0; attempt < 3; attempt++) {
    const observed = Date.parse(`${appointmentInputTime(new Date(instant), timeZone)}:00Z`);
    instant += wallTime - observed;
  }
  const result = new Date(instant);
  if (appointmentInputTime(result, timeZone) !== value) {
    throw new Error('Enter valid appointment times.');
  }
  return result;
}

export function appointmentTimes(start: string, end?: string, timeZone = 'Asia/Kolkata'): { start_time: string; end_time: string } {
  const startDate = workspaceWallTime(start, timeZone);
  const endDate = end ? workspaceWallTime(end, timeZone) : new Date(startDate.getTime() + 30 * 60_000);
  if (endDate <= startDate) throw new Error('End time must be after start time.');
  return { start_time: startDate.toISOString(), end_time: endDate.toISOString() };
}
