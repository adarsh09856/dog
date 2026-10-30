"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { signupApiV1AuthSignupPost } from "@/client/sdk.gen";
import { AuthEnterpriseCTA } from "@/components/auth/AuthEnterpriseCTA";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { detailFromError } from "@/lib/apiError";
import { getPostAuthDestination } from "@/lib/pricingSelection";

import pageStyles from "../../PublicPages.module.css";

export function SignupForm() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [authSearch, setAuthSearch] = useState("");

  useEffect(() => {
    setAuthSearch(window.location.search);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    setLoading(true);

    try {
      const body = { email, password, name: name || undefined, organization_name: orgName || undefined };
      const res = await signupApiV1AuthSignupPost({ body });

      if (res.error || !res.data) {
        toast.error(detailFromError(res.error, "Signup failed"));
        return;
      }

      // Set httpOnly cookies via server route
      const session = await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: res.data.token, user: res.data.user }),
      });

      if (!session.ok) {
        toast.error("Account created, but sign-in failed. Please sign in again.");
        return;
      }

      if (typeof window !== "undefined" && res.data.token) {
        localStorage.setItem("kodewaves_auth_token", res.data.token);
      }

      window.location.href = getPostAuthDestination(window.location.search);
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell enterpriseSlot={<AuthEnterpriseCTA />}>
      <div className={pageStyles.authFormIntro}>
        <p className={pageStyles.eyebrow}>Workspace access</p>
        <h1 className={pageStyles.authHeading}>Create an account</h1>
        <p>Set up your workspace profile to start configuring voice agents.</p>
      </div>

      <form onSubmit={handleSubmit} className={pageStyles.authFields}>
        <div className="space-y-2">
          <Label htmlFor="name">Full Name</Label>
          <Input
            id="name"
            autoComplete="name"
            type="text"
            placeholder="John Doe"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="orgName">Organization / Company Name</Label>
          <Input
            id="orgName"
            autoComplete="organization"
            type="text"
            placeholder="Acme Corp"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            autoComplete="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            autoComplete="new-password"
            type="password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirmPassword">Confirm password</Label>
          <Input
            id="confirmPassword"
            autoComplete="new-password"
            type="password"
            placeholder="Confirm your password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
          />
        </div>
        <Button type="submit" className={`${pageStyles.authSubmit} w-full`} disabled={loading}>
          {loading ? "Creating account..." : "Create account"}
        </Button>
      </form>

      <p className={pageStyles.authFoot}>
        Already have an account?{" "}
        <Link href={`/auth/login${authSearch}`} className="text-primary underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
