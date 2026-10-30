"use client";
import { AudioLines, Mic2, Upload, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";

import RecordingsList from "./RecordingsList";
import { RecordingsUploadDialog } from "./RecordingsUploadDialog";
import styles from "./RecordingsWorkspace.module.css";
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
            <main className={styles.page}>
                <div className="space-y-4">
                    <Skeleton className="h-12 w-64" />
                    <Skeleton className="h-64 w-full" />
                </div>
            </main>
        );
    }

    return (
        <main className={styles.page}>
            <header className={styles.hero}>
                <div className={styles.glow} aria-hidden="true" />
                <div className={styles.heroCopy}>
                    <span className={styles.eyebrow}><AudioLines className="h-3.5 w-3.5" /> Operations / Audio library</span>
                    <h1>Audio library</h1>
                    <p>Keep original recordings and reusable generated speech organized. Each library has its own playback and cleanup controls.</p>
                </div>
                <Button className={styles.heroAction} onClick={() => setIsUploadOpen(true)}><Upload className="h-4 w-4" />Upload recording</Button>
            </header>

            <section className={styles.libraryRail} aria-label="Audio library guide">
                <div className={styles.libraryNote}><span className={styles.noteIcon}><Mic2 className="h-4 w-4" /></span><div><strong>Original recordings</strong><p>Browse, play, rename, and remove source audio.</p></div></div>
                <div className={styles.libraryNote}><span className={styles.noteIcon}><Volume2 className="h-4 w-4" /></span><div><strong>Generated speech</strong><p>Review cached phrases and invalidate them when needed.</p></div></div>
                <div className={styles.libraryNote}><span className={styles.noteIcon}><AudioLines className="h-4 w-4" /></span><div><strong>Organization library</strong><p>Audio assets and cache are scoped to your organization.</p></div></div>
            </section>

            <Tabs defaultValue="recordings" className={styles.tabs} key={`${user.id}:${"selectedTeam" in user ? user.selectedTeam?.id : user.organizationId}`}>
                <TabsList className={styles.tabList}>
                    <TabsTrigger value="recordings">Uploaded recordings</TabsTrigger>
                    <TabsTrigger value="tts-cache">TTS cache</TabsTrigger>
                </TabsList>
                <TabsContent value="recordings">
                    <Card className={styles.panel}>
                        <CardHeader className={styles.panelHeader}>
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
                    <Card className={styles.panel}>
                        <CardHeader className={styles.panelHeader}>
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
        </main>
    );
}
