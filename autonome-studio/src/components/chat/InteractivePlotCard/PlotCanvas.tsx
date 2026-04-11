/**
 * PlotCanvas - 图表画布组件
 *
 * 基于 ECharts 实现交互式图表渲染
 * 支持多种图表类型：scatter, heatmap, bar, line, volcano, pca, boxplot 等
 */

'use client';

import { useRef, useEffect, memo } from 'react';
import * as echarts from 'echarts';
import type { ECharts, EChartsOption } from 'echarts';
import type { PlotType, PlotCanvasProps } from './types';

// ==========================================
// ✨ ECharts 主题配置
// ==========================================

const DARK_THEME = {
  backgroundColor: 'transparent',
  textStyle: {
    color: '#a1a1aa',
  },
  title: {
    textStyle: {
      color: '#e4e4e7',
    },
    subtextStyle: {
      color: '#71717a',
    },
  },
  legend: {
    textStyle: {
      color: '#a1a1aa',
    },
  },
  categoryAxis: {
    axisLine: {
      lineStyle: {
        color: '#3f3f46',
      },
    },
    axisLabel: {
      color: '#a1a1aa',
    },
    splitLine: {
      lineStyle: {
        color: '#27272a',
      },
    },
  },
  valueAxis: {
    axisLine: {
      lineStyle: {
        color: '#3f3f46',
      },
    },
    axisLabel: {
      color: '#a1a1aa',
    },
    splitLine: {
      lineStyle: {
        color: '#27272a',
      },
    },
  },
};

// ==========================================
// ✨ PlotCanvas 主组件
// ==========================================

export const PlotCanvas = memo(function PlotCanvas({
  plotType,
  config,
  title,
  dataSource,
  parameters,
  onChartReady,
  aspectRatio = 1.5,
}: PlotCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  // ✨ 初始化图表
  useEffect(() => {
    if (!containerRef.current) return;

    // 注册深色主题
    echarts.registerTheme('autonome-dark', DARK_THEME);

    // ✨ 使用 SVG 渲染器初始化 ECharts 实例（支持矢量图导出）
    const chart = echarts.init(containerRef.current, 'autonome-dark', {
      renderer: 'svg', // 使用 SVG 渲染，支持矢量导出
    });
    chartRef.current = chart;

    // 回调图表实例
    if (onChartReady) {
      onChartReady(chart);
    }

    // 窗口 resize 处理
    const handleResize = () => {
      chart.resize();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, [onChartReady]);

  // ✨ 更新图表配置 - 当 config 或 parameters 变化时更新
  useEffect(() => {
    if (!chartRef.current || !config) return;

    // 直接使用传入的 config（已由 utils.ts 的 generateEChartsConfig 生成完整配置）
    // 但需要确保深色主题样式被应用
    const themedConfig = applyDarkTheme(config);
    chartRef.current.setOption(themedConfig as EChartsOption, true);
  }, [config, parameters]);

  return (
    <div
      ref={containerRef}
      className="w-full bg-neutral-950 rounded-lg overflow-hidden"
      style={{ height: `${300 * aspectRatio}px`, minHeight: 300 }}
    />
  );
});

// ==========================================
// ✨ 应用深色主题样式
// ==========================================

function applyDarkTheme(config: Record<string, unknown>): Record<string, unknown> {
  // 深色主题基础样式
  const darkStyles = {
    backgroundColor: 'transparent',
    textStyle: { color: '#a1a1aa' },
  };

  // 合并配置，确保深色主题
  return {
    ...darkStyles,
    ...config,
    // 确保标题样式
    title: {
      ...((config.title as Record<string, unknown>) || {}),
      textStyle: {
        fontSize: 14,
        fontWeight: 'bold',
        color: '#e4e4e7',
        ...((config.title as Record<string, unknown>)?.textStyle as Record<string, unknown> || {}),
      },
    },
    // 确保图例样式
    legend: {
      ...((config.legend as Record<string, unknown>) || {}),
      textStyle: {
        color: '#a1a1aa',
        ...((config.legend as Record<string, unknown>)?.textStyle as Record<string, unknown> || {}),
      },
    },
    // 确保 tooltip 样式
    tooltip: {
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#3f3f46',
      textStyle: { color: '#e4e4e7' },
      ...(config.tooltip as Record<string, unknown>),
    },
  };
}

export default PlotCanvas;