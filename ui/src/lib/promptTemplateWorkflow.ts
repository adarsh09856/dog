/** Preserve a saved prompt and greeting while inheriting the workspace models. */
export function promptTemplateWorkflow(template: { system_prompt: string; first_message?: string }) {
  const prompt = template.system_prompt;
  return {
    nodes: [
      { id: '1', type: 'startCall', position: { x: 175, y: 60 }, data: {
        name: 'Start call', prompt, greeting_type: 'text', greeting: template.first_message || '',
        is_start: true, allow_interrupt: true, add_global_prompt: false,
      } },
      { id: '2', type: 'agentNode', position: { x: 175, y: 300 }, data: {
        name: 'Assist caller', prompt, allow_interrupt: true, add_global_prompt: false,
      } },
      { id: '3', type: 'endCall', position: { x: 175, y: 540 }, data: {
        name: 'Closing', prompt: 'Thank the caller briefly in the conversation language and end the call. Do not claim unfinished actions succeeded.',
        is_end: true, allow_interrupt: true, add_global_prompt: false,
      } },
    ],
    edges: [
      { id: 'template-assist', source: '1', target: '2', data: {
        label: 'assist_caller', condition: 'The caller has replied to the greeting and described what they need.',
      } },
      { id: 'template-finish', source: '2', target: '3', data: {
        label: 'finish_call', condition: 'The caller explicitly says they are finished or wants to end the call. Requested actions must have returned their actual results.',
      } },
    ],
    viewport: { x: 0, y: 0, zoom: 0.8 },
  };
}
