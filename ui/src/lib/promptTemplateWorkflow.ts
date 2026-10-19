/** Build a usable agent from a saved prompt without inventing connected tools. */
export function promptTemplateWorkflow(template: {
  system_prompt: string;
  first_message?: string;
  is_featured?: boolean;
}) {
  // The shared gallery has no business name field. Missing template variables
  // otherwise render as empty strings in both web and telephone greetings.
  const prompt = template.system_prompt
    .replace(/for\s+\{\{\s*company_name\s*\}\}\s+clinic/gi, 'at the clinic')
    .replace(/\{\{\s*company_name\s*\}\}/gi, 'the organization you represent')
    + (template.is_featured ? (
      ' A matching connected tool is required before checking live records, '
      + 'making bookings, changing orders, or transferring a call. If that tool '
      + 'is not connected, explain the limitation and offer to collect details '
      + 'for staff. Never claim an action is underway or complete without its result.'
    ) : '');
  const greeting = (template.first_message || '')
    .replace(/this is\s+\{\{\s*company_name\s*\}\}\s+clinic/gi, "You've reached the clinic")
    .replace(/welcome to\s+\{\{\s*company_name\s*\}\}/gi, 'Welcome to our')
    .replace(/thank you for calling\s+\{\{\s*company_name\s*\}\}/gi, 'Thank you for calling')
    .replace(/\{\{\s*company_name\s*\}\}/gi, 'our team')
    .replace(/so I can look up your shipment/gi, 'so I can guide you')
    .replace(/\s+([.!?,])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
  return {
    nodes: [
      { id: '1', type: 'startCall', position: { x: 175, y: 60 }, data: {
        name: 'Start call', prompt, greeting_type: 'text', greeting,
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
