import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/ToastProvider";
import { AuthProvider } from "@/components/providers/AuthProvider";

// ✨ 使用系统字体避免 Turbopack 开发模式下的字体加载问题
export const metadata: Metadata = {
  title: "Autonome Studio",
  description: "AI-Native Bioinformatics IDE",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="h-screen w-screen overflow-hidden bg-background text-foreground transition-colors duration-300">
        <ThemeProvider>
          <AuthProvider>
            {children}
            <ToastProvider />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
