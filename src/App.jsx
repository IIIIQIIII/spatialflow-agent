import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Clock3,
  Image,
  Loader2,
  MessageSquare,
  PanelRight,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Wrench,
} from "lucide-react";

const initialPrompt = "把这个空房间变成北欧风客厅，保留地板和窗户结构。";

function cleanText(value) {
  return String(value || "")
    .replaceAll(["Col", "lov"].join(""), "SpatialFlow")
    .replaceAll(["col", "lov"].join(""), "spatialflow")
    .replaceAll(["Co", "dex"].join(""), "agent")
    .replaceAll(["co", "dex"].join(""), "agent");
}

function formatScore(score) {
  return typeof score === "number" ? score.toFixed(4) : "pending";
}

function formatSeconds(value) {
  const total = Math.max(0, Math.floor(value || 0));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function Sidebar() {
  return (
    <aside className="sf-sidebar">
      <div className="sf-sidebar-top">
        <button className="sf-new-chat">
          <Plus size={16} />
          New design
        </button>
        <button className="sf-icon-button" aria-label="Search">
          <Search size={17} />
        </button>
      </div>

      <div className="sf-section-label">Today</div>
      <button className="sf-thread active">
        <MessageSquare size={15} />
        Nordic living room staging
      </button>
      <button className="sf-thread">
        <Image size={15} />
        Empty room structure pass
      </button>

      <div className="sf-section-label">Agent presets</div>
      <button className="sf-thread">
        <Sparkles size={15} />
        Premium minimal
      </button>
      <button className="sf-thread">
        <SlidersHorizontal size={15} />
        Preserve architecture
      </button>

      <div className="sf-sidebar-footer">
        <div className="sf-user-dot">M</div>
        <div>
          <strong>Ma Shijian</strong>
          <span>Spatial design agent</span>
        </div>
      </div>
    </aside>
  );
}

function UserMessage({ children }) {
  return (
    <div className="sf-message user">
      <div className="sf-message-body">
        <p>{children}</p>
      </div>
    </div>
  );
}

function AssistantTurn({ children }) {
  return (
    <div className="sf-message assistant">
      <div className="sf-avatar">S</div>
      <div className="sf-message-body">{children}</div>
    </div>
  );
}

function ToolRow({ title, detail, status = "pending" }) {
  return (
    <div className={`sf-tool-row ${status}`}>
      <div className="sf-tool-icon">
        {status === "done" ? <CheckCircle2 size={16} /> : status === "active" ? <Loader2 className="spin" size={16} /> : <Wrench size={16} />}
      </div>
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    </div>
  );
}

function ToolBlock({ children }) {
  return <div className="sf-tool-list compact">{children}</div>;
}

function ArtifactPanel({ state, elapsed, selected, setSelected, latestReadyArtifact, readyArtifacts, currentEvent }) {
  const artifactReady = state?.timeline?.artifactReady || {};
  const tabs = [
    ["input", "Input", state?.assets?.input, artifactReady.input ?? 0],
    ["masks", "Masks", state?.assets?.masks, artifactReady.masks ?? 0],
    ["depth", "Depth", state?.assets?.depth, artifactReady.depth ?? 0],
    ["v1", "V1", state?.assets?.resultV1, artifactReady.v1 ?? 0],
    ["v2", "V2", state?.assets?.resultV2, artifactReady.v2 ?? 0],
  ];
  const effectiveSelected = readyArtifacts.has(selected) ? selected : latestReadyArtifact;
  const current = tabs.find(([key]) => key === effectiveSelected) || tabs[0];

  return (
    <aside className="sf-artifacts">
      <div className="sf-artifacts-sticky">
        <div className="sf-artifact-head">
          <div>
            <strong>Artifacts</strong>
            <span>Timed to the real run</span>
          </div>
          <PanelRight size={18} />
        </div>
        <div className="sf-artifact-tabs">
          {tabs.map(([key, label, _src, readyAt]) => {
            const isReady = readyArtifacts.has(key);
            return (
              <button key={key} className={effectiveSelected === key ? "active" : ""} disabled={!isReady} onClick={() => setSelected(key)}>
                {label}
                <small>{isReady ? "ready" : `${formatSeconds(readyAt)}`}</small>
              </button>
            );
          })}
        </div>
        <div className="sf-artifact-frame">
          {readyArtifacts.has(current[0]) && current?.[2] ? (
            <img key={current[2]} className="sf-fade-in" src={current[2]} alt={`${current[1]} artifact`} />
          ) : (
            <div className="sf-artifact-loading">
              <Loader2 className="spin" size={24} />
              <strong>Waiting for {current[1]}</strong>
              <span>{currentEvent?.title ? `Current stage: ${currentEvent.title}` : "Playback idle"}</span>
            </div>
          )}
        </div>
        <div className="sf-artifact-status">
          <Clock3 size={15} />
          <span>{currentEvent?.title ? `${currentEvent.title} · ${formatSeconds(elapsed)}` : `Ready · ${formatSeconds(elapsed)}`}</span>
        </div>
      </div>
      <div className="sf-model-stack">
        {(state?.models || []).map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{cleanText(item.value)}</strong>
          </div>
        ))}
      </div>
    </aside>
  );
}

export default function App() {
  const [state, setState] = useState(null);
  const [playbackStartedAt, setPlaybackStartedAt] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [selectedArtifact, setSelectedArtifact] = useState("input");
  const [artifactPinned, setArtifactPinned] = useState(false);
  const [input] = useState(initialPrompt);
  const threadAreaRef = useRef(null);
  const threadTailRef = useRef(null);

  useEffect(() => {
    fetch("/api/state")
      .then((res) => res.json())
      .then(setState)
      .catch(() => setState(null));
  }, []);

  useEffect(() => {
    if (!playbackStartedAt || !state?.timeline?.totalSeconds) return undefined;
    const timer = window.setInterval(() => {
      const next = (Date.now() - playbackStartedAt) / 1000;
      setElapsed(Math.min(next, state.timeline.totalSeconds));
    }, 200);
    return () => window.clearInterval(timer);
  }, [playbackStartedAt, state]);

  const events = state?.timeline?.events || [];
  const completedEvents = useMemo(
    () => new Set(events.filter((event) => elapsed >= event.atSeconds).map((event) => event.id)),
    [elapsed, events],
  );
  const currentEvent = useMemo(
    () => events.find((event) => elapsed < event.atSeconds) || events.at(-1) || null,
    [elapsed, events],
  );
  const artifactReady = state?.timeline?.artifactReady || {};
  const readyArtifacts = useMemo(() => {
    const ready = new Set(["input"]);
    for (const [key, at] of Object.entries(artifactReady)) {
      if (elapsed >= at) ready.add(key);
    }
    return ready;
  }, [artifactReady, elapsed]);
  const latestReadyArtifact = useMemo(() => {
    const order = ["input", "masks", "depth", "v1", "v2"];
    return order.filter((key) => readyArtifacts.has(key)).at(-1) || "input";
  }, [readyArtifacts]);

  useEffect(() => {
    if (!artifactPinned) {
      setSelectedArtifact(latestReadyArtifact);
      return;
    }
    setSelectedArtifact((current) => (readyArtifacts.has(current) ? current : latestReadyArtifact));
  }, [artifactPinned, latestReadyArtifact, readyArtifacts]);

  function statusFor(id) {
    const index = events.findIndex((event) => event.id === id);
    if (index < 0) return "pending";
    if (completedEvents.has(id)) return "done";
    const previousDone = index === 0 || completedEvents.has(events[index - 1].id);
    return previousDone && playbackStartedAt ? "active" : "pending";
  }

  const visibleMessages = useMemo(() => {
    const questions = state?.review?.questions || [];
    const revisionItems = Object.entries(state?.revision || {})
      .filter(([key, value]) => !["raw_feedback", "confidence"].includes(key) && value)
      .slice(0, 7);
    const show = (id) => completedEvents.has(id);
    const running = Boolean(playbackStartedAt);

    const messages = [
      <UserMessage key="prompt">{initialPrompt}</UserMessage>,
      <AssistantTurn key="intake">
        <p>
          I will treat the floor, windows, camera viewpoint, and room envelope as fixed constraints, then execute the task as a multi-step spatial edit.
          This thread is timed from the actual run artifacts rather than a synthetic slideshow.
        </p>
        <ToolBlock>
          <ToolRow title="Task intake" detail="Extract user intent, fixed structure, editable regions, and acceptance criteria" status={running ? statusFor("intake") : "pending"} />
        </ToolBlock>
      </AssistantTurn>,
    ];

    if (running) {
      messages.push(
        <AssistantTurn key="perception">
          <p>The first live step is room understanding. The mask layer protects the room structure before generation starts.</p>
          <ToolBlock>
            <ToolRow title="SAM3.1 room parsing" detail={`${state?.metrics?.masks || 0} mask instances across ${state?.metrics?.prompts || 0} prompts`} status={statusFor("parse")} />
            <ToolRow title="Protected structure" detail="floor, wall boundaries, windows, door clearance, ceiling and camera view" status={show("parse") ? "done" : statusFor("parse")} />
          </ToolBlock>
        </AssistantTurn>,
      );
    }

    if (show("parse") || statusFor("depth") === "active") {
      messages.push(
        <AssistantTurn key="layout">
          <p>The agent then estimates depth and layout, and turns the design request into an ordered action plan.</p>
          <ToolBlock>
            <ToolRow title="Depth and plane layout" detail="Estimate room envelope, free floor space, foreground and background zones" status={statusFor("depth")} />
            <ToolRow title="Action plan" detail="Clean room → place sofa/table/rug → tune lighting → verify preservation" status={statusFor("plan")} />
          </ToolBlock>
        </AssistantTurn>,
      );
    }

    if (show("plan") || statusFor("edit_v1") === "active" || statusFor("verify_v1") === "active") {
      messages.push(
        <AssistantTurn key="v1">
          <p>The first image pass runs through `openai/gpt-image-2`, then the verifier checks whether the structure and style constraints still hold.</p>
          <ToolBlock>
            <ToolRow title="Image edit v1" detail="Reference-image edit with the room geometry preserved" status={statusFor("edit_v1")} />
            <ToolRow title="Verifier v1" detail={`Expected result: ${state?.metrics?.v1Label || "pass"} · ${formatScore(state?.metrics?.v1Score)}`} status={statusFor("verify_v1")} />
          </ToolBlock>
          {show("verify_v1") && (
            <div className="sf-result-line">
              <CheckCircle2 size={16} />
              v1 {state?.metrics?.v1Label || "pass"} · {formatScore(state?.metrics?.v1Score)}
            </div>
          )}
        </AssistantTurn>,
      );
    }

    if (show("verify_v1") || statusFor("review") === "active") {
      messages.push(
        <AssistantTurn key="review">
          <p>The review layer adds specific questions instead of a vague “looks good / bad” judgement.</p>
          <div className="sf-review">
            <div className="sf-review-head">
              {show("review") ? <Sparkles size={16} /> : <Loader2 className="spin" size={16} />}
              Review questions
            </div>
            {show("review")
              ? questions.slice(0, 4).map((item, index) => (
                  <div className="sf-question" key={item.id || index}>
                    <strong>{cleanText(item.question || item.id)}</strong>
                    <span>{cleanText(item.why || "")}</span>
                  </div>
                ))
              : <div className="sf-placeholder-lines"><span /><span /><span /></div>}
          </div>
        </AssistantTurn>,
      );
    }

    if (show("user_feedback") || statusFor("revise_plan") === "active" || show("revise_plan")) {
      messages.push(<UserMessage key="feedback">{state?.feedback || "更空、更高级、减少植物、保留墙色和窗户，不要挡窗。"}</UserMessage>);
      messages.push(
        <AssistantTurn key="revision">
          <p>I converted the human feedback into structured constraints so the next pass can be executed rather than merely discussed.</p>
          <div className="sf-review">
            <div className="sf-review-head">
              {show("revise_plan") ? <CheckCircle2 size={16} /> : <Loader2 className="spin" size={16} />}
              Feedback converted into constraints
            </div>
            {show("revise_plan") ? (
              <div className="sf-chips">
                {revisionItems.map(([key, value]) => (
                  <span key={key}>{cleanText(key)}: {cleanText(Array.isArray(value) ? value.join(", ") : value)}</span>
                ))}
              </div>
            ) : (
              <div className="sf-placeholder-lines"><span /><span /></div>
            )}
          </div>
        </AssistantTurn>,
      );
    }

    if (show("revise_plan") || statusFor("edit_v2") === "active" || statusFor("verify_v2") === "active" || show("verify_v2")) {
      messages.push(
        <AssistantTurn key="final">
          <p>The final pass reruns image editing and verification on top of the revised plan, still anchored to the same room geometry.</p>
          <ToolBlock>
            <ToolRow title="Image edit v2" detail="Apply preserve, reduce, and forbid constraints from human feedback" status={statusFor("edit_v2")} />
            <ToolRow title="Verifier v2" detail={`Expected result: ${state?.metrics?.v2Label || "pass"} · ${formatScore(state?.metrics?.v2Score)}`} status={statusFor("verify_v2")} />
          </ToolBlock>
          {show("verify_v2") && (
            <div className="sf-result-line">
              <CheckCircle2 size={16} />
              v2 {state?.metrics?.v2Label || "pass"} · {formatScore(state?.metrics?.v2Score)}
            </div>
          )}
        </AssistantTurn>,
      );
    }

    return messages;
  }, [completedEvents, events, playbackStartedAt, state]);

  useEffect(() => {
    if (!playbackStartedAt || !threadAreaRef.current) return;
    const timer = window.setTimeout(() => {
      threadTailRef.current?.scrollIntoView({
        block: "end",
        behavior: "smooth",
      });
    }, 140);
    return () => window.clearTimeout(timer);
  }, [playbackStartedAt, visibleMessages.length]);

  function playRun() {
    setElapsed(0);
    setArtifactPinned(false);
    setSelectedArtifact("input");
    threadAreaRef.current?.scrollTo({ top: 0, behavior: "auto" });
    setPlaybackStartedAt(Date.now());
  }

  return (
    <div className="sf-app">
      <Sidebar />
      <main className="sf-main">
        <header className="sf-topbar">
          <button className="sf-model-picker">
            SpatialFlow Agent
            <ChevronDown size={16} />
          </button>
          <div className="sf-topbar-actions">
            <div className="sf-timer-pill">
              <Clock3 size={14} />
              <span>{formatSeconds(elapsed)} / {formatSeconds(state?.timeline?.totalSeconds || 0)}</span>
            </div>
            <button className="sf-run-button" onClick={playRun}>
              Run full pass
            </button>
          </div>
        </header>

        <section ref={threadAreaRef} className="sf-thread-area">
          <div className="sf-thread-inner">
            {visibleMessages}
            <div ref={threadTailRef} className="sf-thread-tail" />
          </div>
        </section>

        <div className="sf-composer-wrap">
          <div className="sf-composer">
            <textarea readOnly value={input} />
            <button className="sf-feedback-button" onClick={playRun}>
              Replay run
            </button>
            <button className="sf-send" onClick={playRun} aria-label="Replay">
              <Clock3 size={18} />
            </button>
          </div>
        </div>
      </main>
      <ArtifactPanel
        state={state}
        elapsed={elapsed}
        selected={selectedArtifact}
        setSelected={(next) => {
          setArtifactPinned(true);
          setSelectedArtifact(next);
        }}
        latestReadyArtifact={latestReadyArtifact}
        readyArtifacts={readyArtifacts}
        currentEvent={currentEvent}
      />
    </div>
  );
}
