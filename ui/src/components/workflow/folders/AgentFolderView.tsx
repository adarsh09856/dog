'use client';

import { Activity,ArrowUpRight, AudioLines, FolderOpen, Search } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import library from '@/app/workflow/AgentFolderView.module.css';
import type { FolderResponse, WorkflowListResponse } from '@/client/types.gen';
import chrome from '@/components/layout/WorkspaceChrome.module.css';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

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
    const summary = <><section className={`${chrome.agentOverview} ${library.summary}`} aria-label="Agent library summary"><div className={library.metric}><div className={library.metricIcon}><AudioLines size={18} /></div><span>AGENT LIBRARY</span><strong>{workflows.length}<small>active agents</small></strong><Link href="/workflow/create">Create a new agent <ArrowUpRight size={14} /></Link></div><div className={library.metric}><div className={library.metricIcon}><Activity size={18} /></div><span>CONVERSATION RECORDS</span><strong>{totalRuns.toLocaleString()}<small>total runs</small></strong><Link href="/usage">Review activity <ArrowUpRight size={14} /></Link></div><div className={library.metric}><div className={library.metricIcon}><FolderOpen size={18} /></div><span>ORGANISATION</span><strong>{folders.length}<small>folders</small></strong><span className={library.metricNote}>Group agents by team or purpose</span></div></section><div className={`${chrome.agentToolbar} ${library.toolbar}`}><div><span className={library.sectionLabel}>YOUR WORKSPACE</span><h2>Agent library</h2><p>{query ? `${visibleWorkflows.length} matching agents` : 'Find, organize, and manage your conversation workflows.'}</p></div><label className={`${chrome.agentSearch} ${library.search}`}><Search size={16} /><span className="sr-only">Search agents</span><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by agent name" /></label></div></>;
    if (isSearching && visibleWorkflows.length === 0) {
        return <div className={library.library}>{summary}<div role="status" className={library.emptySearch}><h3 className="text-base font-semibold">No agents match your search</h3><p className="mt-2 text-sm text-muted-foreground">Try another agent name, or clear the search to see your library.</p><Button variant="outline" className="mt-5" onClick={() => setQuery('')}>Clear search</Button></div></div>;
    }
    // No folders → keep the original flat list (no folder chrome, nowhere to move to).
    if (folders.length === 0) {
        return <div className={library.library}>{summary}<WorkflowTable workflows={visibleWorkflows} showArchived={false} /></div>;
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
        <div className={library.library}>{summary}<div className={library.folderList}>
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
        </div></div>
    );
}
