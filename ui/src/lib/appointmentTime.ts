/** Format an instant for a datetime-local control in the browser's timezone. */
export function appointmentInputTime(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function appointmentTimes(start: string, end?: string): { start_time: string; end_time: string } {
  const startDate = new Date(start);
  const endDate = end ? new Date(end) : new Date(startDate.getTime() + 30 * 60_000);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    throw new Error('Enter valid appointment times.');
  }
  if (endDate <= startDate) throw new Error('End time must be after start time.');
  return { start_time: startDate.toISOString(), end_time: endDate.toISOString() };
}
