"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type UploadModalContextValue = {
  isOpen: boolean;
  open: () => void;
  close: () => void;
};

const UploadModalContext = createContext<UploadModalContextValue | null>(null);

export function UploadModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  const value = useMemo(
    () => ({
      isOpen,
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
    }),
    [isOpen],
  );

  return <UploadModalContext.Provider value={value}>{children}</UploadModalContext.Provider>;
}

export function useUploadModal() {
  const ctx = useContext(UploadModalContext);
  if (!ctx) {
    throw new Error("useUploadModal must be used within UploadModalProvider");
  }
  return ctx;
}
