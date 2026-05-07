import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import GlobalColdStartLoader from "@/components/GlobalColdStartLoader";

export const metadata: Metadata = {
  title: "Internal Ops | Operations Console",
  description: "Investor Ops & Intelligence Suite",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-background text-foreground min-h-screen overflow-x-hidden">
        <GlobalColdStartLoader>
          <div className="flex bg-grid-pattern min-h-screen">
            <Sidebar />
            <main className="flex-1 ml-64 p-12">
              {children}
            </main>
          </div>
        </GlobalColdStartLoader>
      </body>
    </html>
  );
}
