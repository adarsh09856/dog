import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Plans and pricing",
  description: "Review applicable plan or license terms, usage, features and support for this installation.",
};

export default function PricingLayout({ children }: { children: ReactNode }) {
  return children;
}
