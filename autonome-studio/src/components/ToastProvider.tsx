"use client";

import { Toaster } from 'sonner';

export function ToastProvider() {
  return (
    <Toaster
      position="top-right"
      theme="dark"
      richColors
      closeButton
      duration={5000}
      toastOptions={{
        style: {
          background: '#1a1a1a',
          border: '1px solid #333',
          color: '#e5e5e5',
        },
      }}
    />
  );
}