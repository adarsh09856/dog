"use client";
import { AudioLines, Mic2, PhoneCall, Upload, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";

import CallRecordingsList from "./CallRecordingsList";
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
                <div className={styles.libraryNote}><span className={styles.noteIcon}><PhoneCall className="h-4 w-4" /></span><div><strong>Call recordings</strong><p>Listen to and download audio captured from completed calls.</p></div></div>
                <div className={styles.libraryNote}><span className={styles.noteIcon}><Mic2 className="h-4 w-4" /></span><div><strong>Uploaded audio</strong><p>Manage short audio clips that agents can play in workflows.</p></div></div>
                <div className={styles.libraryNote}><span className={styles.noteIcon}><Volume2 className="h-4 w-4" /></span><div><strong>TTS cache</strong><p>Reuse generated speech to avoid synthesizing the same phrase again.</p></div></div>
            </section>

            <Tabs defaultValue="calls" className={styles.tabs} key={`${user.id}:${"selectedTeam" in user ? user.selectedTeam?.id : user.organizationId}`}>
                <TabsList className={styles.tabList}>
                    <TabsTrigger value="calls">Call recordings</TabsTrigger>
                    <TabsTrigger value="recordings">Uploaded audio</TabsTrigger>
                    <TabsTrigger value="tts-cache">TTS cache</TabsTrigger>
                </TabsList>
                <TabsContent value="calls">
                    <Card className={styles.panel}>
                        <CardHeader className={styles.panelHeader}>
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
                    <Card className={styles.panel}>
                        <CardHeader className={styles.panelHeader}>
                            <CardTitle>Uploaded workflow audio</CardTitle>
                            <CardDescription>
                                Reusable audio clips uploaded for agent workflows. These are separate from completed call recordings.
                            </CardDescription>
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
                                Generated speech is cached so repeated phrases can play without a new TTS request. Listen to a phrase or invalidate it to regenerate on its next request.
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
