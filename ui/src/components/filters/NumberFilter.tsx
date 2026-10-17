import { useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberValue } from "@/types/filters";

interface NumberFilterProps {
  value: NumberValue;
  onChange: (value: NumberValue) => void;
  error?: string;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
}

export const NumberFilter: React.FC<NumberFilterProps> = ({
  value,
  onChange,
  error,
  placeholder = "Enter value",
  min,
  max,
  step = 1,
}) => {
  // Keep the editable value while publishing the current draft for Apply.
  const [localValue, setLocalValue] = useState<string>(value.value?.toString() ?? '');

  // Sync local state when parent value changes (e.g., from URL or clear)
  useEffect(() => {
    setLocalValue(value.value?.toString() ?? '');
  }, [value.value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextValue = e.target.value;
    setLocalValue(nextValue);
    if (nextValue === '') {
      onChange({ value: null });
    } else {
      const num = parseInt(nextValue, 10);
      if (!isNaN(num)) {
        onChange({ value: num });
      }
    }
  };

  return (
    <div className="space-y-2">
      <div className="space-y-2">
        <Label htmlFor="number-filter">Value</Label>
        <Input
          id="number-filter"
          type="number"
          value={localValue}
          onChange={handleChange}
          placeholder={placeholder}
          min={min}
          max={max}
          step={step}
          className={error ? "border-red-500" : ""}
        />
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
};
