/**
 * 分类导航组件
 */

'use client';

import React from 'react';
import { Layers } from 'lucide-react';

interface Category {
  id: string;
  name: string;
  icon: string;
}

interface CategoryNavProps {
  categories: Category[];
  selectedCategory: string | null;
  onSelectCategory: (category: string | null) => void;
}

export function CategoryNav({ categories, selectedCategory, onSelectCategory }: CategoryNavProps) {
  return (
    <div className="sticky top-24">
      <h3 className="text-xs font-medium text-neutral-500 uppercase tracking-wider mb-3">
        分类筛选
      </h3>

      <div className="space-y-1">
        {/* 全部 */}
        <button
          onClick={() => onSelectCategory(null)}
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
            selectedCategory === null
              ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
              : 'hover:bg-neutral-800 text-neutral-400'
          }`}
        >
          <Layers size={16} />
          <span>全部技能</span>
        </button>

        {/* 分类列表 */}
        {categories.map((category) => (
          <button
            key={category.id}
            onClick={() => onSelectCategory(category.id)}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
              selectedCategory === category.id
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'hover:bg-neutral-800 text-neutral-400'
            }`}
          >
            <span className="text-base">{category.icon}</span>
            <span>{category.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}