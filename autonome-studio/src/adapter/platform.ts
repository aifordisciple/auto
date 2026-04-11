/**
 * 平台检测模块
 *
 * 用于检测当前运行环境是 Web 还是 Tauri 桌面端
 */

/**
 * 检测是否在 Tauri 桌面端环境
 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI__' in window;
}

/**
 * 检测是否在 Web 浏览器环境
 */
export function isWeb(): boolean {
  return typeof window !== 'undefined' && !('__TAURI__' in window);
}

/**
 * 检测是否在服务端渲染环境
 */
export function isSSR(): boolean {
  return typeof window === 'undefined';
}

/**
 * 平台类型
 */
export type PlatformType = 'web' | 'desktop' | 'ssr';

/**
 * 获取当前平台类型
 */
export function getPlatform(): PlatformType {
  if (isSSR()) return 'ssr';
  if (isTauri()) return 'desktop';
  return 'web';
}

/**
 * 平台常量
 */
export const Platform = {
  isTauri,
  isWeb,
  isSSR,
  getPlatform,
  /**
   * 当前平台类型
   */
  get type(): PlatformType {
    return getPlatform();
  },
  /**
   * 是否是桌面端
   */
  get isDesktop(): boolean {
    return isTauri();
  },
} as const;

/**
 * Tauri invoke 函数类型（用于类型安全）
 */
export type TauriInvoke = <T>(
  cmd: string,
  args?: Record<string, unknown>
) => Promise<T>;

/**
 * 获取 Tauri invoke 函数
 * 如果不在 Tauri 环境中，返回 null
 */
export function getTauriInvoke(): TauriInvoke | null {
  if (!isTauri()) return null;

  // 动态导入 @tauri-apps/api/core
  // 使用类型断言避免编译错误
  return async (cmd: string, args?: Record<string, unknown>) => {
    const { invoke } = await import('@tauri-apps/api/core');
    return invoke(cmd, args);
  };
}