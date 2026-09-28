"use client";

import Link from 'next/link';
import { ArrowRight, Bot, Phone, ShieldCheck, Sparkles, Sliders } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/lib/auth';

export default function OverviewPage() {
    const { user } = useAuth();

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="max-w-5xl mx-auto space-y-8">
                {/* Sovereign Platform Banner */}
                <Card className="border border-border/70 bg-gradient-to-br from-card to-card/50 shadow-sm">
                    <CardHeader className="pb-4">
                        <div className="flex items-center gap-2 text-primary text-sm font-semibold tracking-wide uppercase">
                            <Sparkles className="h-4 w-4" />
                            Kodewaves Sovereign Voice AI
                        </div>
                        <CardTitle className="text-3xl font-bold tracking-tight">
                            {user?.displayName ? `Welcome, ${user.displayName.split(' ')[0]}!` : "Welcome to Kodewaves"}
                        </CardTitle>
                        <CardDescription className="text-base text-muted-foreground mt-2 max-w-2xl">
                            Enterprise conversational AI platform with sovereign telephony, direct BYOK model pools, and low-latency voice orchestration.
                        </CardDescription>
                    </CardHeader>
                </Card>

                {/* Quick Actions Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <Card className="flex flex-col justify-between hover:border-primary/40 transition-colors">
                        <CardHeader>
                            <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-2">
                                <Bot className="h-5 w-5" />
                            </div>
                            <CardTitle className="text-lg">Voice Agents</CardTitle>
                            <CardDescription>
                                Build and deploy interactive conversational workflows with low-latency speech pipelines.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button asChild className="w-full">
                                <Link href="/workflow">
                                    Manage Agents <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>

                    <Card className="flex flex-col justify-between hover:border-primary/40 transition-colors">
                        <CardHeader>
                            <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-2">
                                <Sliders className="h-5 w-5" />
                            </div>
                            <CardTitle className="text-lg">Model Providers</CardTitle>
                            <CardDescription>
                                Configure LLM, STT, and TTS engines with private API keys or sovereign pools.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button asChild variant="outline" className="w-full">
                                <Link href="/model-configurations">
                                    Configure Models <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>

                    <Card className="flex flex-col justify-between hover:border-primary/40 transition-colors">
                        <CardHeader>
                            <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-2">
                                <Phone className="h-5 w-5" />
                            </div>
                            <CardTitle className="text-lg">Telephony</CardTitle>
                            <CardDescription>
                                Connect SIP trunks, Twilio, Exotel, Plivo, Telnyx, or WebRTC carriers.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button asChild variant="outline" className="w-full">
                                <Link href="/telephony-configurations">
                                    Manage Telephony <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>
                </div>

                {/* Platform Governance & Control Plane */}
                <Card className="border border-border/60">
                    <CardHeader>
                        <div className="flex items-center gap-2">
                            <ShieldCheck className="h-5 w-5 text-emerald-500" />
                            <CardTitle className="text-lg">Sovereign Control Plane</CardTitle>
                        </div>
                        <CardDescription>
                            Your deployment is 100% self-hosted with local database accounting, direct telephony, and zero external vendor locks.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap gap-4">
                            <Button asChild variant="secondary">
                                <Link href="/admin">
                                    Admin Control Plane
                                </Link>
                            </Button>
                            <Button asChild variant="outline">
                                <Link href="/billing">
                                    Wallet &amp; Quotas
                                </Link>
                            </Button>
                            <Button asChild variant="outline">
                                <Link href="/recordings">
                                    Call Recordings
                                </Link>
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
