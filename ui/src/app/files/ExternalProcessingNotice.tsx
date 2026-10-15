'use client';

import { Info } from 'lucide-react';

export default function ExternalProcessingNotice() {
  return (
    <div className="flex gap-3 rounded-lg border border-border/60 bg-muted/30 p-3">
      <Info className="h-4 w-4 flex-shrink-0 text-primary mt-0.5" />
      <div className="text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Sovereign Knowledge Base</p>
        <p className="mt-1">
          Uploads are saved in the configured file storage. Text extraction and embedding use the configured services, which can be local or external. Full Document retrieval provides the complete text; Chunked retrieval searches relevant sections.
        </p>
      </div>
    </div>
  );
}
