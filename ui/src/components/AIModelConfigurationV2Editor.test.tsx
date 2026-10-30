import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ModelConfigurationDefaultsV2 } from "./AIModelConfigurationV2Editor";
import { AIModelConfigurationV2Editor } from "./AIModelConfigurationV2Editor";

const { getAvailableCatalog, getVoices } = vi.hoisted(() => ({
    getAvailableCatalog: vi.fn(),
    getVoices: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "test-user" }, loading: false }) }));
vi.mock("@/lib/kodewavesApi", () => ({ catalogApi: { getAvailableCatalog } }));
vi.mock("@/client/sdk.gen", () => ({ getVoicesApiV1UserConfigurationsVoicesProviderGet: getVoices }));
vi.mock("@/components/VoiceSelectorModal", () => ({
    VoiceSelectorModal: ({ value }: { value: string }) => <span>Voice: {value}</span>,
}));
vi.mock("@/components/ServiceConfigurationForm", () => ({ ServiceConfigurationForm: () => null }));

vi.mock("@/components/ui/select", async () => {
    const React = await import("react");
    type ItemProps = { value: string; disabled?: boolean; children: ReactNode };
    const SelectItem = ({ value, disabled, children }: ItemProps) => <option value={value} disabled={disabled}>{children}</option>;
    const collect = (children: ReactNode): ReactNode[] => {
        const options: ReactNode[] = [];
        React.Children.forEach(children, (child) => {
            if (!React.isValidElement<{ children?: ReactNode } & Partial<ItemProps>>(child)) return;
            if (child.type === SelectItem) {
                options.push(<option key={child.props.value} value={child.props.value} disabled={child.props.disabled}>{child.props.children}</option>);
            } else {
                options.push(...collect(child.props.children));
            }
        });
        return options;
    };
    return {
        Select: ({ value, onValueChange, children }: { value?: string; onValueChange?: (value: string) => void; children: ReactNode }) => (
            <select value={value ?? ""} onChange={(event) => onValueChange?.(event.target.value)}>{collect(children)}</select>
        ),
        SelectTrigger: () => null,
        SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
        SelectValue: () => null,
        SelectItem,
    };
});

vi.mock("@/components/ui/tabs", async () => {
    const React = await import("react");
    const TabsContext = React.createContext<{ value?: string; onValueChange?: (value: string) => void }>({});
    return {
        Tabs: ({ value, onValueChange, children }: { value?: string; onValueChange?: (value: string) => void; children: ReactNode }) => (
            <TabsContext.Provider value={{ value, onValueChange }}>{children}</TabsContext.Provider>
        ),
        TabsList: ({ children }: { children: ReactNode }) => <div>{children}</div>,
        TabsTrigger: ({ value, children }: { value: string; children: ReactNode }) => {
            const tabs = React.useContext(TabsContext);
            return <button type="button" onClick={() => tabs.onValueChange?.(value)}>{children}</button>;
        },
        TabsContent: ({ value, children }: { value: string; children: ReactNode }) => {
            const tabs = React.useContext(TabsContext);
            return tabs.value === value ? <div>{children}</div> : null;
        },
    };
});

vi.mock("@/components/ui/button", () => ({
    Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));
vi.mock("@/components/ui/card", () => ({
    Card: ({ children }: { children: ReactNode }) => <section>{children}</section>,
    CardContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/ui/input", () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }));
vi.mock("@/components/ui/label", () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }));

const supportedLanguages = ["as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "hi-IN", "kn-IN", "mai-IN", "ml-IN", "mr-IN", "ne-IN", "pa-IN", "sa-IN", "ta-IN", "te-IN"];
const catalog = {
    active_providers: [],
    cloud_llm_models: [], cloud_stt_models: [], cloud_tts_models: [], cloud_s2s_models: [],
    local_llm_models: [{ value: "qwen3.5:2b-q4_K_M", label: "Qwen 3.5 2B" }],
    local_stt_models: [{
        value: "indicconformer-ctc-int8", label: "IndicConformer + Anuvani auto-detection", provider: "indicconformer",
        languages: supportedLanguages, supports_auto_detect: true, auto_detect_languages: supportedLanguages,
    }],
    local_tts_models: [{ value: "indic-vits-rasa-13", label: "Regional + Hindi + Indian English", provider: "speaches", languages: supportedLanguages }],
    local_engine_enabled: true, has_local_ai_access: true,
};

const defaults = {
    kodewaves: {
        voices: ["HIN_F"], speeds: [1], languages: ["multi", "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr", "ne", "pa", "sa", "ta", "te"],
        multilingual_languages: supportedLanguages,
        defaults: { voice: "HIN_F", speed: 1, language: "hi" },
        allow_custom_input: false, speed_range: { min: 0.5, max: 2, step: 0.1 },
    },
    dograh: {
        voices: ["HIN_F"], speeds: [1], languages: ["multi", "hi", "en"], defaults: { voice: "HIN_F", speed: 1, language: "hi" },
    },
    byok: {
        pipeline: { llm: {}, tts: {}, stt: {}, embeddings: {}, realtime: {}, default_providers: {} },
        realtime: { realtime: {}, llm: {}, embeddings: {}, default_providers: {} },
    },
} as unknown as ModelConfigurationDefaultsV2;

function savedConfig(language: string) {
    return {
        version: 2,
        mode: "kodewaves",
        kodewaves: {
            api_key: "sovereign-local-cpu", voice: "HIN_F", speed: 1, language,
            llm_engine_type: "local_cpu", llm_model: "qwen3.5:2b-q4_K_M",
            stt_engine_type: "local_cpu", stt_model: "indicconformer-ctc-int8",
            tts_engine_type: "local_cpu", tts_model: "indic-vits-rasa-13", is_realtime: false,
        },
    } as never;
}

describe("AIModelConfigurationV2Editor local Auto recognition", () => {
    it("selects Auto from the live STT manifest, saves it, and restores it after reload", async () => {
        getAvailableCatalog.mockResolvedValue(catalog);
        getVoices.mockResolvedValue({ data: { voices: [{ voice_id: "HIN_F" }] } });
        const onSave = vi.fn().mockResolvedValue(undefined);
        const view = render(<AIModelConfigurationV2Editor defaults={defaults} configuration={savedConfig("hi")} onSave={onSave} />);

        await waitFor(() => expect(getAvailableCatalog).toHaveBeenCalled());
        const languageSelect = await screen.findByRole("combobox", { name: "Recognition language (STT)" }).catch(() => null);
        const selects = screen.getAllByRole("combobox");
        const autoSelect = languageSelect || selects.find((select) =>
            Array.from((select as HTMLSelectElement).options).some((option) => option.value === "multi"),
        );
        expect(autoSelect).toBeTruthy();
        expect(Array.from((autoSelect as HTMLSelectElement).options).map((option) => option.value)).toContain("multi");

        fireEvent.change(autoSelect as HTMLSelectElement, { target: { value: "multi" } });
        expect((autoSelect as HTMLSelectElement).value).toBe("multi");
        fireEvent.click(screen.getByRole("button", { name: /Save Configuration/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
        const saved = onSave.mock.calls[0][0];
        expect(saved.kodewaves.language).toBe("multi");
        expect(saved.kodewaves.stt_engine_type).toBe("local_cpu");
        expect(saved.kodewaves.stt_model).toBe("indicconformer-ctc-int8");

        view.rerender(<AIModelConfigurationV2Editor defaults={defaults} configuration={saved} onSave={onSave} />);
        await waitFor(() => {
            const selectsAfterReload = screen.getAllByRole("combobox");
            const restoredLanguage = selectsAfterReload.find((select) =>
                Array.from((select as HTMLSelectElement).options).some((option) => option.value === "multi"),
            );
            expect((restoredLanguage as HTMLSelectElement | undefined)?.value).toBe("multi");
        });
        expect(screen.getByText(/Speech recognition auto-detects 15 installed STT languages/)).toBeTruthy();
    });

    it("does not expose Auto or save it when the selected recognizer does not advertise detection", async () => {
        getAvailableCatalog.mockResolvedValue({
            ...catalog,
            local_stt_models: [{ ...catalog.local_stt_models[0], supports_auto_detect: false, auto_detect_languages: [] }],
        });
        getVoices.mockResolvedValue({ data: { voices: [{ voice_id: "HIN_F" }] } });
        const onSave = vi.fn().mockResolvedValue(undefined);
        render(<AIModelConfigurationV2Editor defaults={defaults} configuration={savedConfig("hi")} onSave={onSave} />);

        await screen.findByText(/Automatic detection is unavailable for this installed CPU recognizer/i);
        let languageSelect: HTMLElement | undefined;
        await waitFor(() => {
            languageSelect = screen.getAllByRole("combobox").find((select) =>
                Array.from((select as HTMLSelectElement).options).some((option) => option.value === "hi"),
            );
            expect(languageSelect).toBeTruthy();
        });
        expect(languageSelect).toBeTruthy();
        const autoOption = Array.from((languageSelect as HTMLSelectElement).options).find((option) => option.value === "multi");
        expect(autoOption?.disabled).toBe(true);
        expect(autoOption?.textContent).toMatch(/Auto detection unavailable for this STT model/i);
    });
});
