"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Maximize2, Minimize2, Terminal } from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { getToken } from "@/lib/api";

const log = {
  info: (msg: string) => console.log(`%c[WebTerminal] ${msg}`, "color: #22c55e"),
  error: (msg: string, ...args: unknown[]) => console.error(`[WebTerminal] ${msg}`, ...args),
};

export function WebTerminal() {
  const { isTerminalOpen, closeTerminal, isTerminalFullscreen, toggleTerminalFullscreen } = useUIStore();
  const { currentProjectId } = useWorkspaceStore();

  // Refs - 不触发重新渲染
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<any>(null);
  const fitAddonRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const onDataDisposableRef = useRef<any>(null);
  const isInitializedRef = useRef(false);

  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // 初始化终端并连接
  useEffect(() => {
    if (!isTerminalOpen) return;

    const initAndConnect = async () => {
      // 防止重复初始化
      if (isInitializedRef.current) return;
      isInitializedRef.current = true;

      try {
        // 动态导入 xterm
        const [{ Terminal: XTerm }, { FitAddon }] = await Promise.all([
          import("@xterm/xterm"),
          import("@xterm/addon-fit")
        ]);

        // 注入 CSS
        if (typeof document !== 'undefined' && !document.getElementById('xterm-css')) {
          const link = document.createElement('link');
          link.id = 'xterm-css';
          link.rel = 'stylesheet';
          link.href = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css';
          document.head.appendChild(link);
        }

        // 创建终端
        const xterm = new XTerm({
          theme: {
            background: "#0a0a0a",
            foreground: "#e5e5e5",
            cursor: "#22c55e",
            cursorAccent: "#0a0a0a",
            selectionBackground: "rgba(34, 197, 94, 0.3)",
          },
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          fontSize: 14,
          cursorBlink: true,
          scrollback: 10000,
        });

        const fitAddon = new FitAddon();
        xterm.loadAddon(fitAddon);

        if (terminalRef.current) {
          xterm.open(terminalRef.current);
        }

        xtermRef.current = xterm;
        fitAddonRef.current = fitAddon;

        setTimeout(() => fitAddon.fit(), 100);
        log.info("终端已初始化");

        // 连接 WebSocket
        await connectWebSocket(xterm);

      } catch (error) {
        log.error("初始化失败:", error);
        setConnectionError("初始化失败");
      }
    };

    const connectWebSocket = async (xterm: any) => {
      if (!currentProjectId) {
        setConnectionError("请先选择一个项目");
        return;
      }

      const token = getToken();
      if (!token) {
        setConnectionError("请先登录");
        return;
      }

      const cols = xterm.cols || 80;
      const rows = xterm.rows || 24;

      // 构建 WebSocket URL
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      let wsHost: string;
      if (process.env.NEXT_PUBLIC_API_URL) {
        wsHost = process.env.NEXT_PUBLIC_API_URL.replace(/^https?:\/\//, "");
      } else {
        wsHost = `${window.location.hostname}:8000`;
      }

      const wsUrl = `${wsProtocol}//${wsHost}/api/terminal/ws/${currentProjectId}?token=${encodeURIComponent(token)}&cols=${cols}&rows=${rows}`;
      log.info(`WebSocket URL: ${wsProtocol}//${wsHost}/api/terminal/ws/...`);

      try {
        const ws = new WebSocket(wsUrl, "binary");
        ws.binaryType = "arraybuffer";
        wsRef.current = ws;

        ws.onopen = () => {
          log.info("✅ WebSocket onopen 触发");
          setIsConnected(true);
          setConnectionError(null);
          xterm.focus();
        };

        ws.onmessage = (event) => {
          if (event.data instanceof ArrayBuffer) {
            xterm.write(new Uint8Array(event.data));
          } else {
            xterm.write(event.data);
          }
        };

        ws.onerror = (e) => {
          log.error("WebSocket onerror", e);
          setConnectionError("连接错误");
        };

        ws.onclose = (event) => {
          log.info(`WebSocket onclose: code=${event.code}, reason=${event.reason}`);
          setIsConnected(false);
          if (event.code !== 1000) {
            setConnectionError("连接已断开");
          }
        };

        // 注册输入监听
        onDataDisposableRef.current = xterm.onData((data: string) => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(new TextEncoder().encode(data));
          }
        });
      } catch (e) {
        log.error("创建 WebSocket 失败", e);
        setConnectionError("创建连接失败");
      }
    };

    initAndConnect();

    // 清理函数
    return () => {
      log.info("清理终端");
      if (onDataDisposableRef.current) {
        onDataDisposableRef.current.dispose();
        onDataDisposableRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "关闭");
        wsRef.current = null;
      }
      if (xtermRef.current) {
        xtermRef.current.dispose();
        xtermRef.current = null;
      }
      isInitializedRef.current = false;
      setIsConnected(false);
    };
  }, [isTerminalOpen, currentProjectId]);

  // 窗口大小变化
  useEffect(() => {
    if (!isTerminalOpen) return;

    const handleResize = () => {
      fitAddonRef.current?.fit();
    };

    window.addEventListener("resize", handleResize);
    setTimeout(handleResize, 100);

    return () => window.removeEventListener("resize", handleResize);
  }, [isTerminalOpen]);

  if (!isTerminalOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: "100%", opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: "100%", opacity: 0 }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className={`fixed z-50 bg-neutral-950 border-neutral-800 shadow-2xl flex flex-col ${
          isTerminalFullscreen ? "inset-0 border-0" : "bottom-0 left-0 right-0 h-[40vh] border-t"
        }`}
      >
        {/* 标题栏 */}
        <div className="h-10 border-b border-neutral-800 flex items-center justify-between px-4 shrink-0 bg-neutral-900">
          <div className="flex items-center gap-2">
            <Terminal size={16} className="text-green-500" />
            <span className="text-sm text-neutral-300 font-medium">Web Terminal</span>
            {currentProjectId && (
              <span className="text-xs text-neutral-500">• {currentProjectId.slice(0, 8)}...</span>
            )}
            <div className="flex items-center gap-1.5 ml-2">
              <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
              <span className="text-xs text-neutral-500">{isConnected ? "已连接" : "未连接"}</span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={toggleTerminalFullscreen} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded">
              {isTerminalFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button onClick={closeTerminal} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded">
              <X size={16} />
            </button>
          </div>
        </div>

        {/* 终端容器 */}
        <div className="flex-1 overflow-hidden relative">
          {connectionError && !isConnected && (
            <div className="absolute inset-0 flex items-center justify-center bg-neutral-950/80 z-10">
              <p className="text-red-400">{connectionError}</p>
            </div>
          )}
          <div ref={terminalRef} className="w-full h-full p-2" style={{ backgroundColor: "#0a0a0a" }} />
        </div>
      </motion.div>
    </AnimatePresence>
  );
}