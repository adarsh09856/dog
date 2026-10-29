import type { ReactNode } from "react";

import panel from "./PanelWorkspace.module.css";

export function WorkspacePageHeader({ area, title, description, actions }: { area: string; title: string; description: ReactNode; actions?: ReactNode }) {
  return <header className={panel.collectionHeader}><div><span className={panel.eyebrow}>{area}</span><h1>{title}</h1><p>{description}</p></div>{actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}</header>;
}
