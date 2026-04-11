/**
 * 表格预览组件（虚拟滚动优化版）
 *
 * 功能：
 * 1. 自动检测 CSV/TSV 分隔符
 * 2. 虚拟滚动支持大数据量（10000+ 行）
 * 3. 动态列宽和自动截断
 *
 * @optimized 2026-04-08
 */
"use client";

import React, { useMemo, useRef, useCallback, useState, useEffect } from "react";

interface TablePreviewProps {
  /** 表格数据（CSV/TSV 格式） */
  data: string;
  /** 最大显示行数（用于非虚拟滚动模式），默认 50 */
  maxRows?: number;
  /** 是否启用虚拟滚动（大数据量自动启用），默认 true */
  enableVirtualScroll?: boolean;
  /** 虚拟滚动阈值（超过此行数自动启用），默认 100 */
  virtualScrollThreshold?: number;
  /** 行高（像素），用于虚拟滚动计算，默认 32 */
  rowHeight?: number;
  /** 容器高度（像素），默认 400 */
  containerHeight?: number;
}

/**
 * 表格预览组件 - 支持虚拟滚动的大数据表格
 */
export const TablePreview: React.FC<TablePreviewProps> = ({
  data,
  maxRows = 50,
  enableVirtualScroll = true,
  virtualScrollThreshold = 100,
  rowHeight = 32,
  containerHeight = 400,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // 解析 CSV/TSV
  const parseTable = useCallback((text: string) => {
    const lines = text.split('\n').filter(Boolean);
    // 自动检测分隔符：优先检测 Tab，否则用逗号
    const separator = text.includes('\t') ? '\t' : ',';
    return lines.map(line => line.split(separator));
  }, []);

  // 解析结果
  const parsedData = useMemo(() => {
    const rows = parseTable(data);
    return rows;
  }, [data, parseTable]);

  // 总行数
  const totalRows = parsedData.length;
  const dataRows = totalRows > 0 ? totalRows - 1 : 0; // 减去表头

  // 是否使用虚拟滚动
  const useVirtualScroll = useMemo(() => {
    return enableVirtualScroll && dataRows > virtualScrollThreshold;
  }, [enableVirtualScroll, dataRows, virtualScrollThreshold]);

  // 虚拟滚动计算
  const virtualScrollData = useMemo(() => {
    if (!useVirtualScroll || !containerRef.current) {
      return { visibleRows: [], startIndex: 0, endIndex: 0 };
    }

    // 可见行数（额外渲染缓冲区）
    const visibleCount = Math.ceil(containerHeight / rowHeight) + 10;
    // 起始索引（带缓冲区）
    const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - 5);
    // 结束索引
    const endIndex = Math.min(dataRows, startIndex + visibleCount);

    // 可见的行数据
    const visibleRows = parsedData.slice(startIndex + 1, endIndex + 1); // +1 跳过表头

    return {
      visibleRows,
      startIndex,
      endIndex,
      totalHeight: dataRows * rowHeight,
      offsetY: startIndex * rowHeight,
    };
  }, [useVirtualScroll, scrollTop, rowHeight, containerHeight, dataRows, parsedData]);

  // 滚动事件处理
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    if (useVirtualScroll) {
      setScrollTop(e.currentTarget.scrollTop);
    }
  }, [useVirtualScroll]);

  // 表头
  const headers = useMemo(() => {
    if (totalRows === 0) return [];
    return parsedData[0].map((cell, i) => cell || `列${i + 1}`);
  }, [parsedData, totalRows]);

  // 小数据量模式（不使用虚拟滚动）
  const smallDataRows = useMemo(() => {
    if (useVirtualScroll || totalRows === 0) return [];
    return parsedData.slice(1, maxRows + 1);
  }, [useVirtualScroll, parsedData, totalRows, maxRows]);

  if (totalRows === 0) {
    return <div className="text-neutral-500 text-sm">无法解析表格数据</div>;
  }

  return (
    <div
      ref={containerRef}
      className="overflow-auto w-full h-full"
      style={{ maxHeight: useVirtualScroll ? containerHeight : undefined }}
      onScroll={handleScroll}
    >
      {useVirtualScroll ? (
        // 虚拟滚动模式
        <table className="min-w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-neutral-800 z-10">
            <tr className="border-b-2 border-neutral-600">
              {headers.map((header, i) => (
                <th
                  key={i}
                  className="px-3 py-2 text-left text-neutral-300 font-semibold whitespace-nowrap bg-neutral-800"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* 占位元素，撑起总高度 */}
            <tr style={{ height: virtualScrollData.offsetY }}>
              <td colSpan={headers.length} style={{ padding: 0 }} />
            </tr>
            {/* 可见的行 */}
            {virtualScrollData.visibleRows.map((row, i) => (
              <tr
                key={virtualScrollData.startIndex + i}
                className="border-b border-neutral-700/50 hover:bg-neutral-700/30 transition-colors"
                style={{ height: rowHeight }}
              >
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-1.5 text-neutral-400 whitespace-nowrap">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        // 普通模式（小数据量）
        <table className="min-w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-neutral-800 z-10">
            <tr className="border-b-2 border-neutral-600">
              {headers.map((header, i) => (
                <th
                  key={i}
                  className="px-3 py-2 text-left text-neutral-300 font-semibold whitespace-nowrap bg-neutral-800"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {smallDataRows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-neutral-700/50 hover:bg-neutral-700/30 transition-colors"
              >
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-1.5 text-neutral-400 whitespace-nowrap">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* 数据统计提示 */}
      <div className="text-xs text-neutral-500 mt-3 p-2 bg-neutral-800/50 rounded">
        📊 共 {dataRows} 行数据
        {useVirtualScroll && "（虚拟滚动已启用）"}
        {!useVirtualScroll && smallDataRows.length < dataRows && (
          <span>，显示前 {smallDataRows.length} 行</span>
        )}
      </div>
    </div>
  );
};

export default TablePreview;