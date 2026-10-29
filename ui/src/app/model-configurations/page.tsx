
import ModelConfigurationV2 from "@/components/ModelConfigurationV2";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";
import styles from "./ModelConfigurationWorkspace.module.css";

export default function ServiceConfigurationPage() {
    return (
        <div className={styles.workspace}>
            <div className={styles.content}>
                <div className={styles.editor}>
                    <ModelConfigurationV2 docsUrl={SETTINGS_DOCUMENTATION_URLS.modelOverrides} />
                </div>
            </div>
        </div>
    );
}
