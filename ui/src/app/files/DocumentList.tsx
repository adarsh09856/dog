'use client';

import { FileText, Pencil, RefreshCw, Search, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import {
  deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete,
} from '@/client/sdk.gen';
import type { DocumentResponseSchema } from '@/client/types.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrganizationTimezone } from '@/hooks/useOrganizationTimezone';
import { detailFromError } from '@/lib/apiError';
import { formatDateTime } from '@/lib/dateTime';
import { apiFetch } from '@/lib/kodewavesApi';
import logger from '@/lib/logger';

import DocumentEditor, { isEditableDocument } from './DocumentEditor';
import styles from './FilesWorkspace.module.css';

interface DocumentListProps {
  refreshTrigger: number;
}

export default function DocumentList({ refreshTrigger }: DocumentListProps) {
  const organizationTimezone = useOrganizationTimezone();
  const [documents, setDocuments] = useState<DocumentResponseSchema[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [editingDoc, setEditingDoc] = useState<DocumentResponseSchema | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  const fetchDocuments = useCallback(async (offset = 0, append = false) => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      if (append) setIsLoadingMore(true);
      else {
        setIsLoading(true);
        setIsLoadingMore(false);
      }
      setError(null);
      setLoadMoreError(null);

      const query = new URLSearchParams({ limit: '100', offset: String(offset) });
      if (searchQuery.trim()) query.set('search', searchQuery.trim());
      const response = await apiFetch<{
        documents: DocumentResponseSchema[];
        total: number;
        limit: number;
        offset: number;
      }>(`/knowledge-base/documents?${query.toString()}`, {
        signal: controller.signal,
      });

      if (controller.signal.aborted) return;
      setDocuments((current) => append ? [...current, ...response.documents] : response.documents);
      setTotalDocuments(response.total);
    } catch (err) {
      if (controller.signal.aborted) return;
      const message = err instanceof Error ? err.message : 'Failed to fetch documents';
      if (append) setLoadMoreError(message);
      else setError(message);
      logger.error('Error fetching documents:', err);
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    }
  }, [searchQuery]);

  const refreshLoadedDocuments = useCallback(async () => {
    if (isLoading || isLoadingMore) return;
    const offsets = Array.from(
      { length: Math.max(1, Math.ceil(documents.length / 100)) },
      (_unused, index) => index * 100,
    );
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const pages = await Promise.all(offsets.map(async (offset) => {
        const query = new URLSearchParams({ limit: '100', offset: String(offset) });
        if (searchQuery.trim()) query.set('search', searchQuery.trim());
        return apiFetch<{
          documents: DocumentResponseSchema[];
          total: number;
          limit: number;
          offset: number;
        }>(`/knowledge-base/documents?${query.toString()}`, { signal: controller.signal });
      }));
      if (controller.signal.aborted) return;
      setDocuments(pages.flatMap((page) => page.documents));
      setTotalDocuments(pages[0]?.total || 0);
    } catch (err) {
      if (!controller.signal.aborted) logger.error('Error refreshing documents:', err);
    }
  }, [documents.length, isLoading, isLoadingMore, searchQuery]);

  // Fetch documents on mount and when refreshTrigger changes
  useEffect(() => {
    const timer = window.setTimeout(() => void fetchDocuments(), searchQuery.trim() ? 250 : 0);
    return () => {
      window.clearTimeout(timer);
      activeRequest.current?.abort();
    };
  }, [fetchDocuments, refreshTrigger, searchQuery]);

  // Poll for documents that are processing
  useEffect(() => {
    const processingDocs = documents.filter(
      (doc) => doc.processing_status === 'processing' || doc.processing_status === 'pending'
    );

    if (processingDocs.length === 0) return;

    const pollInterval = setInterval(() => {
      logger.info(`Polling for ${processingDocs.length} processing documents...`);
      void refreshLoadedDocuments();
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(pollInterval);
  }, [documents, refreshLoadedDocuments]);

  const handleDelete = async (documentUuid: string, filename: string) => {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) return;

    try {
      const response = await deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete({
        path: {
          document_uuid: documentUuid,
        },
      });

      if (response.error) {
        throw new Error(detailFromError(response.error, 'Failed to delete document'));
      }

      toast.success(`Deleted "${filename}"`);
      fetchDocuments();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete document');
      logger.error('Error deleting document:', err);
    }
  };

  const isBusy = (doc: DocumentResponseSchema) =>
    doc.processing_status === 'processing' || doc.processing_status === 'pending';

  const canOpen = (doc: DocumentResponseSchema) =>
    isEditableDocument(doc.filename) && !isBusy(doc);

  const getStatusBadge = (doc: DocumentResponseSchema) => {
    // A previously indexed document keeps serving agents while it is re-indexed
    // after an edit, and after that re-index fails.
    if (doc.has_live_content && isBusy(doc)) {
      return (
        <Badge variant="secondary" className="animate-pulse">
          Updating
        </Badge>
      );
    }
    if (doc.has_live_content && doc.processing_status === 'failed') {
      return <Badge variant="destructive">Update failed</Badge>;
    }
    switch (doc.processing_status) {
      case 'completed':
        return <Badge className="bg-green-500">Completed</Badge>;
      case 'processing':
        return (
          <Badge variant="secondary" className="animate-pulse">
            Processing
          </Badge>
        );
      case 'pending':
        return <Badge variant="outline">Pending</Badge>;
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>;
      default:
        return <Badge variant="outline">{doc.processing_status}</Badge>;
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const filteredDocuments = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchQuery.trim().toLowerCase())
  );

  if (isLoading && documents.length === 0) {
    return (
      <div className={styles.list}>
        {[1, 2, 3].map((i) => (
          <div key={i} className={styles.skeletonRow}>
            <div className="space-y-2 flex-1">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-64" />
            </div>
            <Skeleton className="h-8 w-24" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className={styles.error}>
        {error}
        <Button variant="outline" className="ml-3" onClick={fetchDocuments}>Retry</Button>
      </div>
    );
  }

  return (
    <div className={styles.list}>
      {/* Search and Refresh */}
      <div className={styles.toolbar}>
        <div className={styles.search}>
          <Search />
          <Input
            aria-label="Search documents"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className=""
          />
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={fetchDocuments}
          disabled={isLoading}
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Document List */}
      {filteredDocuments.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}><FileText className="h-6 w-6" /></span>
          <p className="text-muted-foreground">
            {searchQuery
              ? 'No documents match your search'
              : 'No documents uploaded yet'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredDocuments.map((doc) => (
            <div
              key={doc.document_uuid}
              role={canOpen(doc) ? 'button' : undefined}
              tabIndex={canOpen(doc) ? 0 : undefined}
              aria-label={canOpen(doc) ? `Edit ${doc.filename}` : undefined}
              className={`${styles.row} ${canOpen(doc) ? styles.rowClickable : ""} ${
                canOpen(doc)
                  ? 'cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring'
                  : ''
              }`}
              onClick={canOpen(doc) ? () => setEditingDoc(doc) : undefined}
              onKeyDown={(event) => {
                if (!canOpen(doc) || event.target !== event.currentTarget) return;
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setEditingDoc(doc);
                }
              }}
            >
              <div className="flex items-center gap-4 flex-1">
                <div className={styles.fileIcon}>
                  <FileText className="w-5 h-5 text-primary" />
                </div>
                <div className={styles.fileDetails}>
                  <div className={styles.fileTitle}>
                    <span className="font-medium truncate">{doc.filename}</span>
                    {getStatusBadge(doc)}
                    {doc.retrieval_mode === 'full_document' ? (
                      <Badge variant="outline" className="text-xs">Full Document</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">Chunked</Badge>
                    )}
                  </div>
                  <div className={styles.fileMeta}>
                    <span>{formatFileSize(doc.file_size_bytes)}</span>
                    {doc.processing_status === 'completed' && doc.retrieval_mode !== 'full_document' && (
                      <span>{doc.total_chunks} chunks</span>
                    )}
                    <span>{formatDateTime(doc.created_at, organizationTimezone)}</span>
                  </div>
                  {doc.has_live_content && isBusy(doc) && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Agents keep using the previous version until the update finishes.
                    </p>
                  )}
                  {doc.processing_error && (
                    <p className="text-xs text-destructive mt-1">
                      Error: {doc.processing_error}
                      {doc.has_live_content && ' Agents are still using the previous version.'}
                    </p>
                  )}
                  {doc.processing_status === 'failed' &&
                   doc.docling_metadata &&
                   typeof doc.docling_metadata === 'object' &&
                   'duplicate_of' in doc.docling_metadata && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Duplicate of another document
                    </p>
                  )}
                </div>
              </div>
              <div
                className={styles.rowActions}
                onClick={(event) => event.stopPropagation()}
              >
                {isEditableDocument(doc.filename) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Edit ${doc.filename}`}
                    onClick={() => setEditingDoc(doc)}
                    disabled={isBusy(doc)}
                    title={isBusy(doc) ? 'Available once processing finishes' : 'Edit'}
                  >
                    <Pencil className="w-4 h-4" />
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Delete ${doc.filename}`}
                  onClick={() => handleDelete(doc.document_uuid, doc.filename)}
                  className="text-destructive hover:text-destructive/90"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {totalDocuments > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <span className="text-xs text-muted-foreground">
            Showing {documents.length.toLocaleString()} of {totalDocuments.toLocaleString()} documents
          </span>
          {documents.length < totalDocuments && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchDocuments(documents.length, true)}
              disabled={isLoading || isLoadingMore}
            >
              {isLoadingMore ? <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
              {isLoadingMore ? 'Loading older documents…' : 'Load older documents'}
            </Button>
          )}
        </div>
      )}
      {loadMoreError && <div role="alert" className={styles.error}>{loadMoreError}</div>}

      <DocumentEditor
        doc={editingDoc}
        onClose={() => setEditingDoc(null)}
        onSaved={() => {
          setEditingDoc(null);
          fetchDocuments();
        }}
      />
    </div>
  );
}
