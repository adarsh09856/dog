"use client";
import { WorkspacePageHeader } from "@/components/layout/WorkspacePageHeader";

import { AudioLines, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";

import CallRecordingsList from "./CallRecordingsList";
import RecordingsList from "./RecordingsList";
import { RecordingsUploadDialog } from "./RecordingsUploadDialog";
import TtsCacheList from "./TtsCacheList";

export default function RecordingsPage() {
    const { user, redirectToLogin, loading } = useAuth();
    const [isUploadOpen, setIsUploadOpen] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    useEffect(() => {
        if (!loading && !user) {
            redirectToLogin();
        }
    }, [loading, user, redirectToLogin]);

    if (loading || !user) {
        return (
            <div className="container mx-auto px-4 py-8">
                <div className="space-y-4">
                    <Skeleton className="h-12 w-64" />
                    <Skeleton className="h-64 w-full" />
                </div>
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8">
            <WorkspacePageHeader
                area="OPERATIONS / AUDIO LIBRARY"
                title="Audio library"
                description="Keep reusable audio and generated speech together. Uploaded recordings and cached TTS have separate controls, so refreshing generated speech does not alter source files."
                actions={<Button onClick={() => setIsUploadOpen(true)}><Upload className="mr-2 h-4 w-4" />Upload recording</Button>}
            />

            <div className="mb-5 flex items-start gap-3 rounded-xl border border-border bg-muted/30 p-4">
                <AudioLines className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div><p className="text-sm font-semibold">Choose a library</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Manage source recordings or review cached speech reused by workflows. Playback controls stay available on each item.</p></div>
            </div>

            <Tabs defaultValue="calls" key={`${user.id}:${"selectedTeam" in user ? user.selectedTeam?.id : user.organizationId}`}>
                <TabsList className="mb-4">
                    <TabsTrigger value="calls">Call recordings</TabsTrigger>
                    <TabsTrigger value="recordings">Uploaded recordings</TabsTrigger>
                    <TabsTrigger value="tts-cache">TTS cache</TabsTrigger>
                </TabsList>
                <TabsContent value="calls">
                    <Card>
                        <CardHeader>
                            <CardTitle>Call recordings</CardTitle>
                            <CardDescription>
                                Recordings from completed phone and browser calls. Calls without saved audio are not listed here.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <CallRecordingsList />
                        </CardContent>
                    </Card>
                </TabsContent>
                <TabsContent value="recordings">
                    <Card>
                        <CardHeader>
                            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                                <div>
                                    <CardTitle>All Recordings</CardTitle>
                                    <CardDescription>
                                        Audio recordings shared across all agents in your organization
                                    </CardDescription>
                                </div>
                                <span className="text-xs text-muted-foreground">Organization library</span>
                            </div>
                        </CardHeader>
                        <CardContent>
                            <RecordingsList refreshKey={refreshKey} />
                        </CardContent>
                    </Card>
                </TabsContent>
                <TabsContent value="tts-cache">
                    <Card>
                        <CardHeader>
                            <CardTitle>Cached speech</CardTitle>
                            <CardDescription>
                                Speech reused across your organization’s workflows. Listen to a phrase and invalidate it to generate fresh audio on its next request.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <TtsCacheList />
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            <RecordingsUploadDialog
                open={isUploadOpen}
                onOpenChange={setIsUploadOpen}
                onUploadComplete={() => setRefreshKey((k) => k + 1)}
            />
        </div>
    );
}
