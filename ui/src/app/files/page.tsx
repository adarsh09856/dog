"use client";
import { WorkspacePageHeader } from "@/components/layout/WorkspacePageHeader";

import { FileText, Layers3, Upload } from "lucide-react";
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
            <div className="container mx-auto px-4 py-8">
                <div className="space-y-4">
                    <Skeleton className="h-12 w-64" />
                    <Skeleton className="h-64 w-full" />
                </div>
            </div>
        );
    }

    return (
        <div key={`${user.id}:${"selectedTeam" in user ? user.selectedTeam?.id : user.organizationId}`} className="container mx-auto px-4 py-8">
            <WorkspacePageHeader
                area="BUILD / KNOWLEDGE"
                title="Knowledge base"
                description="Give your agents verified source material. Upload documents once, monitor processing, and attach the right knowledge to each workflow."
                actions={<Button onClick={() => setIsUploadOpen(true)}><Upload className="mr-2 h-4 w-4" />Upload files</Button>}
            />

            <section aria-label="Knowledge base workflow" className="mb-6 grid gap-3 md:grid-cols-3">
                <div className="flex gap-3 rounded-xl border border-border bg-card p-4">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Upload className="h-4 w-4" /></span>
                    <div><h2 className="text-sm font-semibold">Add source material</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Upload PDFs and supported documents for your workspace.</p></div>
                </div>
                <div className="flex gap-3 rounded-xl border border-border bg-card p-4">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><FileText className="h-4 w-4" /></span>
                    <div><h2 className="text-sm font-semibold">Track processing</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Review document status before relying on it in a conversation.</p></div>
                </div>
                <div className="flex gap-3 rounded-xl border border-border bg-card p-4">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Layers3 className="h-4 w-4" /></span>
                    <div><h2 className="text-sm font-semibold">Reuse across agents</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Keep shared reference files organized in one library.</p></div>
                </div>
            </section>

            <Card>
                <CardHeader>
                    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                        <div>
                            <CardTitle>Your Documents</CardTitle>
                            <CardDescription>
                                Documents shared across all agents in your organization
                            </CardDescription>
                        </div>
                        <span className="text-xs text-muted-foreground">Shared at the organization level</span>
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
        </div>
    );
}
