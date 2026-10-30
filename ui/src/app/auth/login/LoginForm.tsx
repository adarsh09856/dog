"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { loginApiV1AuthLoginPost } from "@/client/sdk.gen";
import { AuthEnterpriseCTA } from "@/components/auth/AuthEnterpriseCTA";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getAuthContinuationSearch, getPostAuthDestination } from "@/lib/pricingSelection";

import pageStyles from "../../PublicPages.module.css";

export function LoginForm({ signupEnabled }: { signupEnabled: boolean }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [signupContinuation, setSignupContinuation] = useState("");

  useEffect(() => {
    setSignupContinuation(getAuthContinuationSearch(window.location.search));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const res = await loginApiV1AuthLoginPost({
        body: { email, password },
      });

      if (res.error || !res.data) {
        const detail = (res.error as { detail?: string })?.detail;
        toast.error(detail || "Login failed");
        return;
      }

      // Set httpOnly cookies via server route
      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: res.data.token, user: res.data.user }),
      });

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
        <h1 className={pageStyles.authHeading}>Sign in</h1>
        <p>Continue to your agents, channels and conversation history.</p>
      </div>

      <form onSubmit={handleSubmit} className={pageStyles.authFields}>
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
            autoComplete="current-password"
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <Button type="submit" className={`${pageStyles.authSubmit} w-full`} disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </Button>
      </form>

      {signupEnabled && (
        <p className={pageStyles.authFoot}>
          Don&apos;t have an account?{" "}
          <Link href={`/auth/signup${signupContinuation}`} className="text-primary underline-offset-4 hover:underline">
            Sign up
          </Link>
        </p>
      )}
    </AuthShell>
  );
}
