import { describe, expect, it } from 'vitest';
import { createToolDefinition, getCategoryConfig } from './config';

describe('appointment tool authoring', () => {
    it('creates a native booking definition without external credentials or URL', () => {
        expect(createToolDefinition('book_appointment')).toEqual({ schema_version: 1, type: 'book_appointment' });
        const category = getCategoryConfig('book_appointment');
        expect(category?.disabled).not.toBe(true);
        expect(category?.autoFill?.description).toContain('booked=true');
    });
});
