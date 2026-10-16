import type { Metadata } from "next";
import "./globals.css";
import "./simple-page.css";

export const metadata: Metadata = {
  title: "Rentra | Find a place to rent in Nepal",
  description: "Discover rental homes and spaces across Nepal.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
