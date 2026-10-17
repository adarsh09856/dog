/** A minimal, editable agent that can greet without an LLM round trip. */
export const BLANK_WORKFLOW_DEFINITION = {
    nodes: [
        {
            id: '1',
            type: 'startCall',
            position: { x: 175, y: 60 },
            data: {
                prompt: '# Goal\nYou are a helpful voice agent. Listen to the caller and answer their request.\n\n## Rules\n- Reply in the caller’s language. If they switch between an Indian language and English, follow naturally.\n- Keep spoken replies short and clear.\n- If the transcript is unclear, ask one brief clarification instead of guessing.\n- Do not repeat your previous answer when the caller asks a new question.',
                greeting: 'Hello! How can I help you?',
                name: 'start call',
                allow_interrupt: false,
                invalid: false,
                validationMessage: null,
                add_global_prompt: false,
                delayed_start: false,
                is_start: true,
                selected_through_edge: false,
                hovered_through_edge: false,
                extraction_enabled: false,
                selected: false,
                dragging: false,
            },
        },
    ],
    edges: [],
    viewport: { x: 808, y: 269, zoom: 0.75 },
};
