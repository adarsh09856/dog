import { ArrowUpRight, AudioLines, Check, Globe2, Phone, Workflow } from "lucide-react";

/** Product schematic, deliberately labelled rather than presented as live data. */
export function VoiceOperationsIllustration() {
  return (
    <div className="voice-console" aria-label="Illustration of a voice workflow from caller to action">
      <div className="voice-console-top"><span className="voice-console-mark"><AudioLines size={17} /> VOICE WORKSPACE</span><span>WORKFLOW PREVIEW</span></div>
      <div className="voice-console-body">
        <div className="voice-console-channel"><span><Phone size={15} /> Telephone</span><span><Globe2 size={15} /> Browser</span><span className="voice-console-channel-note">One conversation layer <ArrowUpRight size={14} /></span></div>
        <div className="voice-conversation">
          <div className="voice-avatar"><AudioLines size={23} /></div>
          <div><span className="voice-eyebrow">A NATURAL START</span><p>“How can I help you today?”</p></div>
        </div>
        <div className="voice-wave" aria-hidden="true">{Array.from({ length: 42 }, (_, i) => <i key={i} style={{ height: `${12 + ((i * 17 + 7) % 43)}px`, animationDelay: `${i * -0.09}s` }} />)}</div>
        <div className="voice-route"><div><span>01</span><strong>Listen</strong><small>Speech recognition</small></div><b aria-hidden="true">→</b><div><span>02</span><strong>Understand</strong><small>Reasoning & context</small></div><b aria-hidden="true">→</b><div><span>03</span><strong>Respond</strong><small>Voice synthesis</small></div></div>
        <div className="voice-action"><span className="voice-action-icon"><Workflow size={19} /></span><div><strong>Move the conversation forward</strong><small>Connect a tool, follow a branch, or hand off.</small></div><Check size={18} /></div>
      </div>
      <div className="voice-console-bottom"><span>DESIGN → TEST → DEPLOY</span><span>Illustrative workflow</span></div>
    </div>
  );
}
