import type { Metadata } from "next";
import { Barlow_Condensed, Inter } from "next/font/google";
import { Shell } from "@/components/Shell";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const barlow = Barlow_Condensed({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--font-barlow" });

export const metadata: Metadata = {
  title: "AutoEng Studio",
  description: "Design, simulate, analyse and validate automobiles and their components.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${inter.variable} ${barlow.variable} h-full`} suppressHydrationWarning>
      <head>
        {/* Apply the saved colour theme before first paint to avoid a flash. */}
        <script
          dangerouslySetInnerHTML={{
            __html: "try{var t=localStorage.getItem('autoeng.theme');if(t)document.documentElement.dataset.theme=t}catch(e){}",
          }}
        />
      </head>
      <body className="min-h-full">
        <SessionProvider>
          <Shell>{children}</Shell>
        </SessionProvider>
      </body>
    </html>
  );
}
