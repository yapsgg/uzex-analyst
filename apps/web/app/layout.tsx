import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { type ReactNode, Suspense } from "react";
import { NewChatButton } from "@/components/nav";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import "./globals.css";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Exchange Analyst",
  description: "Ask questions about the commodity exchange deal registry in Russian, Uzbek, or English.",
};

export default function RootLayout({ children }: { readonly children: ReactNode }) {
  return (
    <html className={cn(geistSans.variable, geistMono.variable)} lang="en">
      <body className="flex min-h-dvh flex-col bg-background text-foreground antialiased">
        <TooltipProvider>
          <div className="fixed top-3 right-3 z-30">
            <Suspense fallback={null}>
              <NewChatButton />
            </Suspense>
          </div>
          {children}
        </TooltipProvider>
      </body>
    </html>
  );
}
