import {
    Activity,
    Circle,
    ClipboardCheck,
    CreditCard,
    Globe,
    Headset,
    Link2,
    type LucideIcon,
    OctagonX,
    Play,
    Webhook,
} from "lucide-react";

// Keep this list aligned with the core and built-in integration NodeSpecs.
// Resolving arbitrary names from the lucide-react namespace pulls thousands
// of icon modules into every workflow-editor server bundle.
const NODE_ICON_BY_NAME: Readonly<Record<string, LucideIcon>> = {
    Activity,
    ClipboardCheck,
    CreditCard,
    Globe,
    Headset,
    Link2,
    OctagonX,
    Play,
    Webhook,
};

export function resolveNodeIcon(name: string): LucideIcon {
    return NODE_ICON_BY_NAME[name] ?? Circle;
}
