import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Plans and pricing",
  description:
    "Review configured platform plans, credit bundles and the costs of a hosted workspace or client installation.",
};

export default function PricingLayout({ children }: { children: ReactNode }) {
  return children;
}
