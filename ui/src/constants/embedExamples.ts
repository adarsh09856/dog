export const HEADLESS_CHAT_EXAMPLE = `let chatState = 'idle';

function withKodewavesWidget(callback) {
  const existing = window.KodewavesWidget || window.DograhWidget;
  if (existing) {
    callback(existing);
    return;
  }

  const script = document.getElementById('kodewaves-widget') || document.getElementById('dograh-widget');
  if (!script) {
    console.error('Kodewaves embed script not found');
    return;
  }

  script.addEventListener('load', () => {
    const loaded = window.KodewavesWidget || window.DograhWidget;
    if (loaded) callback(loaded);
  }, { once: true });
}

withKodewavesWidget((widget) => {
  widget.onChatStateChange((state) => {
    chatState = state; // idle | starting | ready | waiting | ended | expired | error
  });

  widget.onMessage((text, turn) => {
    appendAgentBubble(text); // render however you want
  });

  document.getElementById('open-chat').addEventListener('click', () => {
    widget.startChat();
  });

  document.getElementById('send-btn').addEventListener('click', async () => {
    const input = document.getElementById('chat-input');
    appendVisitorBubble(input.value);
    const transcript = await widget.sendMessage(input.value);
    if (transcript !== null) input.value = '';
  });

  document.getElementById('end-chat')?.addEventListener('click', async () => {
    await widget.endChat();
  });
});`;
