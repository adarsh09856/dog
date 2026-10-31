import {
  ArrowRight,
  AudioLines,
  Check,
  Database,
  FileText,
  Globe2,
  Headphones,
  PhoneIncoming,
  PhoneOutgoing,
  Workflow,
  Wrench,
} from "lucide-react";

/** Product schematic, deliberately labelled rather than presented as live data. */
export function VoiceOperationsIllustration() {
  return (
    <div className="voice-console" aria-label="Illustration of inbound, outbound and browser voice calls flowing through speech recognition, an AI agent and speech synthesis">
      <div className="voice-console-top"><span className="voice-console-mark"><AudioLines size={17} /> KODEWAVES / VOICE AGENT</span><span>CONFIGURED FLOW</span></div>
      <div className="voice-console-body">
        <div className="voice-console-sources" aria-label="Supported call entry points">
          <div><PhoneIncoming aria-hidden size={16} /><span><strong>Inbound</strong><small>Phone call</small></span></div>
          <div><PhoneOutgoing aria-hidden size={16} /><span><strong>Outbound</strong><small>Campaign or callback</small></span></div>
          <div><Globe2 aria-hidden size={16} /><span><strong>Browser</strong><small>Web voice</small></span></div>
        </div>
        <div className="voice-pipeline-label"><span>THE REAL-TIME CONVERSATION</span><span>01 — 03</span></div>
        <div className="voice-route" aria-label="Speech-to-response pipeline">
          <div className="voice-route-step"><span className="voice-route-icon"><AudioLines aria-hidden size={17} /></span><div><span>01 / STT</span><strong>Recognize</strong><small>Caller audio → text</small></div></div>
          <ArrowRight className="voice-route-arrow" aria-hidden size={16} />
          <div className="voice-route-step voice-route-step-featured"><span className="voice-route-icon"><Workflow aria-hidden size={17} /></span><div><span>02 / LLM</span><strong>Understand & act</strong><small>Context · knowledge · tools</small></div></div>
          <ArrowRight className="voice-route-arrow" aria-hidden size={16} />
          <div className="voice-route-step"><span className="voice-route-icon"><Headphones aria-hidden size={17} /></span><div><span>03 / TTS</span><strong>Speak</strong><small>Text → natural audio</small></div></div>
        </div>
        <div className="voice-console-outcomes">
          <div className="voice-action"><span className="voice-action-icon"><Wrench aria-hidden size={17} /></span><span><strong>Complete the next step</strong><small>Workflow branch or connected action</small></span><Check aria-hidden size={16} /></div>
          <div className="voice-action"><span className="voice-action-icon"><Database aria-hidden size={17} /></span><span><strong>Review the conversation</strong><small>Run details, transcript and recording</small></span><FileText aria-hidden size={16} /></div>
        </div>
      </div>
      <div className="voice-console-bottom"><span>ONE AGENT / MULTIPLE CHANNELS</span><span>Illustrative flow · provider setup varies</span></div>
    </div>
  );
}
