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
    .replace(/Help callers track their shipments, report delivery issues, and reschedule deliveries\./gi,
      'Help callers with delivery questions and policies. You have no live tracking or rescheduling access unless a matching tool is connected.')
    .replace(/Always ask for the order ID or tracking number first\./gi,
      'Ask for an order ID or tracking number only when a connected tool needs it or the caller chooses to include it in this conversation. Without a live tracking tool, say you cannot see the current shipment status. Without a connected storage or handoff tool, never claim to record, save, or pass details to staff; direct the caller to the seller\'s official support channel.')
    + (template.is_featured ? (
      ' A matching connected tool is required before checking live records, '
      + 'making bookings, changing orders, or transferring a call. If that tool '
      + 'is not connected, explain the limitation and direct the caller to an '
      + 'official support channel you actually know. Do not claim to store or '
      + 'forward caller details without a successful connected tool. Do not '
      + 'invent prices, availability, eligibility, inventory, '
      + 'or shipment status. Never claim an action is underway or complete '
      + 'without its result. Use details the caller has already provided, '
      + 'including IDs and contact information; never ask for the same detail again.'
    ) : '');
  const greeting = (template.first_message || '')
    .replace(/this is\s+\{\{\s*company_name\s*\}\}\s+clinic/gi, "You've reached the clinic")
    .replace(/welcome to\s+\{\{\s*company_name\s*\}\}/gi, 'Welcome to our')
    .replace(/thank you for calling\s+\{\{\s*company_name\s*\}\}/gi, 'Thank you for calling')
    .replace(/\{\{\s*company_name\s*\}\}/gi, 'our team')
    .replace(/so I can look up your shipment/gi, 'so I can guide you')
    .replace(/I can help you schedule an appointment/gi, 'I can collect details for an appointment')
    .replace(/\s+([.!?,])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
  return {
    nodes: [
      { id: '1', type: 'startCall', position: { x: 175, y: 60 }, data: {
        name: 'Start call', prompt, greeting_type: 'text', greeting,
        is_start: true, allow_interrupt: true, add_global_prompt: false,
      } },
      { id: '2', type: 'endCall', position: { x: 175, y: 300 }, data: {
        name: 'Closing', prompt: 'Thank the caller briefly in the conversation language and end the call. Do not claim unfinished actions succeeded.',
        is_end: true, allow_interrupt: true, add_global_prompt: false,
      } },
    ],
    edges: [
      // The start node owns this prompt for the whole conversation. An extra
      // identical agent node would require a routing completion before replying.
      { id: 'template-finish', source: '1', target: '2', data: {
        label: 'finish_call', condition: 'The caller explicitly says they are finished or wants to end the call. Requested actions must have returned their actual results.',
      } },
    ],
    viewport: { x: 0, y: 0, zoom: 0.8 },
  };
}
