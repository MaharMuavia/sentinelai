import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/Navbar";

export const metadata: Metadata = {
  title: "Sentinel AI | DataHub Pre-Merge Change Control Agent",
  description: "Autonomous pre-merge Data Reliability Engineer powered by DataHub. Know what a data change will break before you merge it.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 antialiased min-h-screen flex flex-col">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto p-6">{children}</main>
        <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 py-5 text-center text-xs text-slate-500 dark:text-slate-400">
          <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-2">
            <span className="font-medium text-slate-700 dark:text-slate-300">
              Sentinel AI • Powered by DataHub Context Engine
            </span>
            <span className="text-slate-400 dark:text-slate-500 font-mono">
              Build with DataHub Hackathon 2026 • Agents That Do Real Work
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
