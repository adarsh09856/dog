"use client";
import { WorkspacePageHeader } from "@/components/layout/WorkspacePageHeader";

import { ExternalLink, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";

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
            <WorkspacePageHeader area="OPERATIONS / AUDIO LIBRARY" title="Recordings" description="Manage audio recordings for your organization." />

            <Tabs defaultValue="recordings" key={`${user.id}:${"selectedTeam" in user ? user.selectedTeam?.id : user.organizationId}`}>
                <TabsList className="mb-4">
                    <TabsTrigger value="recordings">Uploaded recordings</TabsTrigger>
                    <TabsTrigger value="tts-cache">TTS cache</TabsTrigger>
                </TabsList>
                <TabsContent value="recordings">
                    <Card>
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <div>
                                    <CardTitle>All Recordings</CardTitle>
                                    <CardDescription>
                                        Audio recordings shared across all agents in your organization
                                    </CardDescription>
                                </div>
                                <Button onClick={() => setIsUploadOpen(true)}>
                                    <Upload className="w-4 h-4 mr-2" />
                                    Upload Recording
                                </Button>
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
