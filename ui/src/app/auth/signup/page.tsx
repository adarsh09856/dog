import { redirect } from "next/navigation";

import { getSignupEnabled } from "@/lib/auth/config";

import { SignupForm } from "./SignupForm";

export const dynamic = "force-dynamic";

export default async function SignupPage() {
  if (
    process.env.NEXT_PUBLIC_KODEWAVES_EDITION === "client" ||
    !(await getSignupEnabled())
  ) {
    redirect("/auth/login");
  }

  return <SignupForm />;
}
