
import ModelConfigurationV2 from "@/components/ModelConfigurationV2";
import { AudioLines } from "lucide-react";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";
import styles from "./ModelConfigurationWorkspace.module.css";

export default function ServiceConfigurationPage() {
    return (
        <div className={styles.workspace}>
            <div className={styles.content}>
                <div className="mb-6 flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-start gap-3">
                        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-primary shadow-sm">
                            <AudioLines className="size-5" aria-hidden="true" />
                        </span>
                        <div>
                            <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-primary">Build / speech stack</p>
                            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                                Set the organization defaults for language models, speech recognition, and voice generation.
                            </p>
                        </div>
                    </div>
                    <span className="w-fit rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground">Organization defaults</span>
                </div>
                <div className={styles.editor}>
                    <ModelConfigurationV2 docsUrl={SETTINGS_DOCUMENTATION_URLS.modelOverrides} />
                </div>
            </div>
        </div>
    );
}
