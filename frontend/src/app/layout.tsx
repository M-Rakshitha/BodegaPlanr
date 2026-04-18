import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "BodegaPlanr",
  description: "Corner Store Planning — AI-powered inventory & vendor intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <Nav />
        <div className="pt-24">{children}</div>
      </body>
    </html>
  );
}
