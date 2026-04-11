/**
 * 参数类型选择器
 */

'use client';

import React from 'react';
import { ChevronDown } from 'lucide-react';
import { ParameterType, PARAMETER_TYPES } from './types';

interface TypeSelectorProps {
  value: ParameterType;
  onChange: (type: ParameterType) => void;
  className?: string;
}

export function TypeSelector({ value, onChange, className = '' }: TypeSelectorProps) {
  const selected = PARAMETER_TYPES.find(t => t.value === value);

  return (
    <div className={`relative ${className}`}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as ParameterType)}
        className="appearance-none w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white pr-8 focus:border-blue-500 focus:outline-none cursor-pointer"
      >
        {PARAMETER_TYPES.map(type => (
          <option key={type.value} value={type.value}>
            {type.icon} {type.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={14}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 pointer-events-none"
      />
    </div>
  );
}