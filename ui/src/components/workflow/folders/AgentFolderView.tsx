'use client';

import { useState } from 'react';
import { Search, AudioLines, FolderOpen, ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import chrome from '@/components/layout/WorkspaceChrome.module.css';

import type { FolderResponse, WorkflowListResponse } from '@/client/types.gen';

import { WorkflowTable } from '../WorkflowTable';
import { FolderSection } from './FolderSection';

interface AgentFolderViewProps {
    /** Active (non-archived) agents only. */
    workflows: WorkflowListResponse[];
    folders: FolderResponse[];
}

/**
 * Renders active agents grouped into collapsible folder sections.
 *
 * When the organization has no folders yet, this falls back to the original
 * flat table so the feature stays invisible until someone creates a folder.
 */
export function AgentFolderView({ workflows, folders }: AgentFolderViewProps) {
    const [query, setQuery] = useState('');
    const isSearching = query.trim().length > 0;
    const visibleWorkflows = workflows.filter(workflow => workflow.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
    const totalRuns = workflows.reduce((total, workflow) => total + (workflow.total_runs ?? 0), 0);
    const summary = <><section className={chrome.agentOverview} aria-label="Agent library summary"><div><AudioLines size={25} /><span>AGENT LIBRARY</span><strong>{workflows.length}<small>active agents</small></strong></div><div><span>CONVERSATION RECORDS</span><strong>{totalRuns.toLocaleString()}<small>total runs</small></strong><Link href="/usage">Review activity <ArrowUpRight size={14} /></Link></div><div><FolderOpen size={20} /><span>ORGANISATION</span><strong>{folders.length}<small>folders</small></strong></div></section><div className={chrome.agentToolbar}><div><h2>All agents</h2><p>{query ? `${visibleWorkflows.length} matching agents` : 'Open an agent to configure, test or publish its workflow.'}</p></div><label className={chrome.agentSearch}><Search size={16} /><span className="sr-only">Search agents</span><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by agent name" /></label></div></>;
    if (isSearching && visibleWorkflows.length === 0) {
        return <>{summary}<div role="status" className="rounded-xl border border-dashed border-border bg-card px-6 py-10 text-center"><h3 className="text-base font-semibold">No agents match your search</h3><p className="mt-2 text-sm text-muted-foreground">Try another agent name, or clear the search to see your library.</p><Button variant="outline" className="mt-5" onClick={() => setQuery('')}>Clear search</Button></div></>;
    }
    // No folders → keep the original flat list (no folder chrome, nowhere to move to).
    if (folders.length === 0) {
        return <>{summary}<WorkflowTable workflows={visibleWorkflows} showArchived={false} /></>;
    }

    // Group agents by folder. Agents whose folder_id is null — or points at a
    // folder we didn't get back — fall into "Uncategorized".
    const folderIds = new Set(folders.map((f) => f.id));
    const byFolder = new Map<number, WorkflowListResponse[]>();
    const uncategorized: WorkflowListResponse[] = [];

    for (const wf of visibleWorkflows) {
        if (wf.folder_id != null && folderIds.has(wf.folder_id)) {
            const bucket = byFolder.get(wf.folder_id) ?? [];
            bucket.push(wf);
            byFolder.set(wf.folder_id, bucket);
        } else {
            uncategorized.push(wf);
        }
    }

    return (
        <><div>{summary}</div><div className="space-y-1">
            {folders.filter(folder => !isSearching || byFolder.has(folder.id)).map((folder) => (
                <FolderSection
                    key={`${folder.id}:${isSearching}`}
                    kind="folder"
                    folder={folder}
                    workflows={byFolder.get(folder.id) ?? []}
                    allFolders={folders}
                    defaultOpen={isSearching}
                />
            ))}
            {uncategorized.length > 0 && (
                <FolderSection
                    kind="uncategorized"
                    workflows={uncategorized}
                    allFolders={folders}
                />
            )}
        </div></>
    );
}
