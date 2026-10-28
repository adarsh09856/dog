import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { FilterBuilder } from './FilterBuilder';
import type { ActiveFilter, FilterAttribute, FilterValue } from '@/types/filters';

function Harness({ attribute, value, onApply, valid = true }: {
    attribute: FilterAttribute; value: FilterValue; valid?: boolean;
    onApply: (values: FilterValue[]) => void;
}) {
    const [filters, setFilters] = useState<ActiveFilter[]>([{ attribute, value, isValid: valid }]);
    return <FilterBuilder availableAttributes={[attribute]} activeFilters={filters}
        onFiltersChange={setFilters} onApplyFilters={() => onApply(filters.map(filter => filter.value))} />;
}

describe('filter keyboard application', () => {
    it('applies the currently typed run ID without requiring blur', () => {
        const onApply = vi.fn();
        render(<Harness attribute={{ id: 'runId', label: 'Run ID', type: 'number', config: {} }}
            value={{ value: 167 }} onApply={onApply} />);
        const input = screen.getByRole('spinbutton', { name: 'Value' });
        fireEvent.focus(input);
        fireEvent.change(input, { target: { value: '166' } });
        fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });
        expect(onApply).toHaveBeenCalledWith([{ value: 166 }]);
    });

    it('enables Apply for a newly entered number before blur', () => {
        render(<Harness attribute={{ id: 'runId', label: 'Run ID', type: 'number', config: {} }}
            value={{ value: null }} valid={false} onApply={vi.fn()} />);
        fireEvent.change(screen.getByRole('spinbutton', { name: 'Value' }), { target: { value: '166' } });
        expect((screen.getByRole('button', { name: /Apply/ }) as HTMLButtonElement).disabled).toBe(false);
    });

    it('applies current text rather than the previous phone filter', () => {
        const onApply = vi.fn();
        render(<Harness attribute={{ id: 'callerNumber', label: 'Caller Number', type: 'text', config: {} }}
            value={{ value: '+910000000001' }} onApply={onApply} />);
        const input = screen.getByRole('textbox');
        fireEvent.change(input, { target: { value: '+910000000002' } });
        fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });
        expect(onApply).toHaveBeenCalledWith([{ value: '+910000000002' }]);
    });

    it('applies both current duration boundaries without requiring blur', () => {
        const onApply = vi.fn();
        render(<Harness attribute={{ id: 'duration', label: 'Duration', type: 'numberRange', config: {} }}
            value={{ min: 10, max: 30 }} onApply={onApply} />);
        fireEvent.change(screen.getByRole('spinbutton', { name: 'Min' }), { target: { value: '20' } });
        const maximum = screen.getByRole('spinbutton', { name: 'Max' });
        fireEvent.change(maximum, { target: { value: '40' } });
        fireEvent.keyDown(maximum, { key: 'Enter', ctrlKey: true });
        expect(onApply).toHaveBeenCalledWith([{ min: 20, max: 40 }]);
    });

    it('does not apply a now-invalid duration using its old valid boundaries', () => {
        const onApply = vi.fn();
        render(<Harness attribute={{ id: 'duration', label: 'Duration', type: 'numberRange', config: {} }}
            value={{ min: 10, max: 30 }} onApply={onApply} />);
        const minimum = screen.getByRole('spinbutton', { name: 'Min' });
        fireEvent.change(minimum, { target: { value: '40' } });
        fireEvent.keyDown(minimum, { key: 'Enter', ctrlKey: true });
        expect(onApply).not.toHaveBeenCalled();
    });
});
