"use client";
import { BookOpenCheck, FileText, Layers3, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

import DocumentList from "./DocumentList";
import DocumentUpload from "./DocumentUpload";
import styles from "./FilesWorkspace.module.css";

export default function FilesPage() {
    const { user, redirectToLogin, loading } = useAuth();
    const [refreshKey, setRefreshKey] = useState(0);
    const [isUploadOpen, setIsUploadOpen] = useState(false);

    // Redirect if not authenticated
    useEffect(() => {
        if (!loading && !user) {
            redirectToLogin();
        }
    }, [loading, user, redirectToLogin]);

    const handleUploadSuccess = () => {
        setRefreshKey(prev => prev + 1);
        setIsUploadOpen(false);
    };

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
        <main key={`${user.id}:${"selectedTeam" in user ? user.selectedTeam?.id : user.organizationId}`} className={styles.page}>
            <header className={styles.hero}>
                <div className={styles.glow} aria-hidden="true" />
                <div className={styles.heroCopy}>
                    <span className={styles.eyebrow}><BookOpenCheck className="h-3.5 w-3.5" /> Build / Knowledge</span>
                    <h1>Knowledge base</h1>
                    <p>Give agents dependable source material. Upload documents once, track indexing, and reuse verified knowledge across workflows.</p>
                </div>
                <Button className={styles.heroAction} onClick={() => setIsUploadOpen(true)}><Upload className="h-4 w-4" />Upload files</Button>
            </header>

            <section aria-label="Knowledge base workflow" className={styles.stepRail}>
                <div className={styles.step}>
                    <span className={styles.stepIcon}><Upload className="h-4 w-4" /></span>
                    <div><h2>Add source material</h2><p>Upload supported documents to your organization library.</p></div>
                </div>
                <div className={styles.step}>
                    <span className={styles.stepIcon}><FileText className="h-4 w-4" /></span>
                    <div><h2>Track processing</h2><p>Check indexing status before agents rely on a document.</p></div>
                </div>
                <div className={styles.step}>
                    <span className={styles.stepIcon}><Layers3 className="h-4 w-4" /></span>
                    <div><h2>Reuse across agents</h2><p>Share approved reference files across your workflows.</p></div>
                </div>
            </section>

            <Card className={styles.documentsPanel}>
                <CardHeader className={styles.panelHeader}>
                    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                        <div>
                            <CardTitle>Your Documents</CardTitle>
                            <CardDescription>
                                Documents shared across all agents in your organization
                            </CardDescription>
                        </div>
                        <span className={styles.scopePill}>Shared at the organization level</span>
                    </div>
                </CardHeader>
                <CardContent>
                    <DocumentList refreshTrigger={refreshKey} />
                </CardContent>
            </Card>

            <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Upload Document</DialogTitle>
                        <DialogDescription>
                            Upload a PDF or document file to add to your knowledge base
                        </DialogDescription>
                    </DialogHeader>
                    <DocumentUpload onUploadSuccess={handleUploadSuccess} />
                </DialogContent>
            </Dialog>
        </main>
    );
}
