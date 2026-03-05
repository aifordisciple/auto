import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en" className="dark">
      <body className="h-screen w-screen overflow-hidden bg-background text-foreground">
        {children}
      </body>
    </html>
  );
}
