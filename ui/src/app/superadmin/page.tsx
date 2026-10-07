"use client";

import { getUserEmail } from "@/lib/auth/userDisplay";

import { ArrowRight, List, Loader2, ShieldAlert } from 'lucide-react';
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from '@/lib/auth';
import { impersonateAsSuperadmin } from "@/lib/utils";

type ImpersonationTarget = "provider" | "email";

export default function SuperadminPage() {
    const [providerUserId, setProviderUserId] = useState("");
    const [email, setEmail] = useState("");
    const [error, setError] = useState<{ target: ImpersonationTarget; message: string } | null>(null);
    const [loadingTarget, setLoadingTarget] = useState<ImpersonationTarget | null>(null);
    const { user, getAccessToken } = useAuth();

    const handleImpersonate = async (target: ImpersonationTarget, value: string) => {
        const trimmedValue = value.trim();
        setError(null);

        if (!trimmedValue) {
            setError({
                target,
                message: target === "provider" ? "Enter a provider user ID." : "Enter an email address.",
            });
            return;
        }

        setLoadingTarget(target);

        try {
            if (!user) {
                setError({
                    target,
                    message: "User not authenticated. Please log in and try again.",
                });
                return;
            }

            const accessToken = await getAccessToken();
            if (!accessToken) {
                throw new Error('Missing admin access token');
            }

            await impersonateAsSuperadmin({
                accessToken: accessToken,
                ...(target === "provider"
                    ? { providerUserId: trimmedValue }
                    : { email: trimmedValue }),
                redirectPath: '/workflow',
                openInNewTab: true,
            });
        } catch (err) {
            setError({
                target,
                message: err instanceof Error ? err.message : "Failed to impersonate user. Please try again.",
            });
            console.error("Impersonation error:", err);
        } finally {
            setLoadingTarget(null);
        }
    };

    const handleProviderImpersonate = async (e: React.FormEvent) => {
        e.preventDefault();
        await handleImpersonate("provider", providerUserId);
    };

    const handleEmailImpersonate = async (e: React.FormEvent) => {
        e.preventDefault();
        await handleImpersonate("email", email);
    };

    const isSuper = (user as any)?.is_superuser || (user as any)?.role === 'admin' || (user as any)?.is_admin;

    if (!isSuper) {
        return (
            <div className="flex h-[70vh] flex-col items-center justify-center p-6 text-center">
                <ShieldAlert className="h-12 w-12 text-destructive mb-4" />
                <h1 className="text-2xl font-bold tracking-tight">Superadmin Access Required</h1>
                <p className="mt-2 text-sm text-muted-foreground max-w-md">
                    Your account ({getUserEmail(user)}) does not have administrative privileges to access this area.
                </p>
                <div className="mt-6 flex gap-4">
                    <Link href="/workflow">
                        <Button variant="outline">Back to Workflows</Button>
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <>
            <main className="container mx-auto p-6 space-y-6 max-w-5xl">
                <div className="text-center">
                    <h1 className="text-3xl font-bold mb-2">Superadmin Dashboard</h1>
                    <p className="text-sm text-muted-foreground">Manage users and view system-wide data</p>
                </div>

                <div className="p-4 rounded-xl border border-primary/40 bg-primary/5 flex items-center justify-between">
                    <div>
                        <div className="font-bold text-sm text-primary">New: Kodewaves Sovereign Admin Suite</div>
                        <div className="text-xs text-muted-foreground">Manage master provider keys, retail margins, credit bundles, live calls, and content moderation.</div>
                    </div>
                    <Link href="/admin">
                        <Button className="gap-2 text-xs">
                            Open Sovereign Admin <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                    </Link>
                </div>

                <div className="grid gap-6 md:grid-cols-2">
                        <Card>
                            <CardHeader>
                                <CardTitle>Provider User ID</CardTitle>
                                <CardDescription>
                                    Impersonate with the Stack provider user ID
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <form onSubmit={handleProviderImpersonate} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="providerUserId">Provider User ID</Label>
                                        <Input
                                            id="providerUserId"
                                            value={providerUserId}
                                            onChange={(e) => setProviderUserId(e.target.value)}
                                            placeholder="Provider user ID"
                                            required
                                        />
                                    </div>

                                    {error?.target === "provider" && (
                                        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg text-sm">
                                            {error.message}
                                        </div>
                                    )}

                                    <Button
                                        type="submit"
                                        disabled={loadingTarget !== null}
                                        className="w-full"
                                    >
                                        {loadingTarget === "provider" ? (
                                            <>
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                Processing...
                                            </>
                                        ) : (
                                            'Impersonate by Provider ID'
                                        )}
                                    </Button>
                                </form>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle>Email</CardTitle>
                                <CardDescription>
                                    Impersonate with a primary email address
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <form onSubmit={handleEmailImpersonate} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="email">Email Address</Label>
                                        <Input
                                            id="email"
                                            type="email"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            placeholder="user@example.com"
                                            required
                                        />
                                    </div>

                                    {error?.target === "email" && (
                                        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg text-sm">
                                            {error.message}
                                        </div>
                                    )}

                                    <Button
                                        type="submit"
                                        disabled={loadingTarget !== null}
                                        className="w-full"
                                    >
                                        {loadingTarget === "email" ? (
                                            <>
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                Processing...
                                            </>
                                        ) : (
                                            'Impersonate by Email'
                                        )}
                                    </Button>
                                </form>
                            </CardContent>
                        </Card>

                        <Card className="md:col-span-2">
                            <CardHeader>
                                <CardTitle>Workflow Runs</CardTitle>
                                <CardDescription>
                                    View and manage all workflow runs across organizations
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <Link href="/superadmin/runs">
                                    <Button className="w-full md:w-auto">
                                        <List className="mr-2 h-4 w-4" />
                                        View All Runs
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </Button>
                                </Link>
                            </CardContent>
                        </Card>
                </div>
            </main>
        </>
    );
}
