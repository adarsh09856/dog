import { describe, expect, it } from 'vitest';
import { appointmentInputTime, appointmentTimes } from './appointmentTime';

describe('appointment time conversion', () => {
  it('uses India wall time independent of the browser timezone', () => {
    expect(appointmentInputTime('2026-10-07T09:00:00Z')).toBe('2026-10-07T14:30');
    expect(appointmentTimes('2026-10-07T14:30').start_time).toBe('2026-10-07T09:00:00.000Z');
    expect(appointmentTimes('2026-10-07T14:30').end_time).toBe('2026-10-07T09:30:00.000Z');
  });
  it('honors a workspace timezone with summer and winter offsets', () => {
    expect(appointmentInputTime('2026-07-07T14:30:00Z', 'America/New_York')).toBe('2026-07-07T10:30');
    expect(appointmentTimes('2026-07-07T10:30', undefined, 'America/New_York').start_time).toBe('2026-07-07T14:30:00.000Z');
    expect(appointmentTimes('2026-01-07T10:30', undefined, 'America/New_York').start_time).toBe('2026-01-07T15:30:00.000Z');
    expect(() => appointmentTimes('2026-03-08T02:30', undefined, 'America/New_York')).toThrow('valid appointment');
  });
  it('rejects invalid or reversed times', () => {
    expect(() => appointmentTimes('invalid')).toThrow('valid appointment');
    expect(() => appointmentTimes('2026-10-07T14:30', '2026-10-07T14:00')).toThrow('after start');
  });
});
