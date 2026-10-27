import { useEffect, useRef, useState } from "react";
import type { GenerationMetadata } from "./ai-contracts";

type Mode = "fan" | "analyst";
type Topic =
  | "score"
  | "shots"
  | "passes"
  | "possession"
  | "key_moments"
  | "unsupported";
export type CopilotAnswer = {
  question: string;
  answer: string;
  as_of_minute: number;
  topic: Topic;
  source: "foundry" | "template";
  metadata: GenerationMetadata;
  evidence_event_ids: string[];
  facts: { label: string; value: string | number }[];
  limitations: string[];
  synthetic: true;
};
type AnswerState = {
  context: string;
  question: string;
  loading: boolean;
  answer?: CopilotAnswer;
  error?: string;
};
const suggestions = [
  "Who's leading?",
  "Compare the shots",
  "Who has more possession?",
  "Show the key moments",
];
const topics: Topic[] = [
  "score",
  "shots",
  "passes",
  "possession",
  "key_moments",
  "unsupported",
];

function isAnswer(
  value: unknown,
  question: string,
  minute: number,
): value is CopilotAnswer {
  if (!value || typeof value !== "object") return false;
  const result = value as CopilotAnswer;
  return (
    result.synthetic === true &&
    result.question === question &&
    result.as_of_minute === minute &&
    typeof result.answer === "string" &&
    result.answer.length > 0 &&
    result.answer.length <= 8000 &&
    topics.includes(result.topic) &&
    ["foundry", "template"].includes(result.source) &&
    !!result.metadata &&
    result.metadata.source === result.source &&
    (result.source !== "foundry" ||
      result.metadata.provider_attempted === true) &&
    Array.isArray(result.evidence_event_ids) &&
    result.evidence_event_ids.length <= 1000 &&
    result.evidence_event_ids.every(
      (id) => typeof id === "string" && id.length <= 512,
    ) &&
    Array.isArray(result.facts) &&
    result.facts.length <= 100 &&
    result.facts.every(
      (fact) =>
        fact &&
        typeof fact.label === "string" &&
        fact.label.length <= 512 &&
        ((typeof fact.value === "string" && fact.value.length <= 4000) ||
          (typeof fact.value === "number" && Number.isFinite(fact.value))),
    ) &&
    Array.isArray(result.limitations) &&
    result.limitations.length <= 30 &&
    result.limitations.every(
      (item) => typeof item === "string" && item.length <= 2000,
    )
  );
}

export default function MatchCopilot({
  minute,
  mode,
  disabled = false,
  onAsk,
}: {
  minute: number;
  mode: Mode;
  disabled?: boolean;
  onAsk?: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<AnswerState | null>(null);
  const active = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const context = `${minute}:${mode}`;
  const visible = state?.context === context && !disabled ? state : null;
  const loading = visible?.loading === true;
  const answer = visible?.answer;
  const trimmed = question.trim();

  useEffect(() => {
    sequence.current += 1;
    active.current?.abort();
    active.current = null;
    setState(null);
    return () => {
      sequence.current += 1;
      active.current?.abort();
    };
  }, [context, disabled]);

  function cancel() {
    sequence.current += 1;
    active.current?.abort();
    active.current = null;
    setState(null);
  }

  async function ask() {
    if (disabled || loading || !trimmed || trimmed.length > 600) return;
    onAsk?.();
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const request = ++sequence.current;
    const asked = trimmed;
    setState({ context, question: asked, loading: true });
    try {
      const response = await fetch("/api/matches/demo/copilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ question: asked, minute, mode }),
      });
      if (!response.ok) throw new Error("request_failed");
      const value: unknown = await response.json();
      if (controller.signal.aborted || sequence.current !== request) return;
      if (!isAnswer(value, asked, minute)) throw new Error("invalid_answer");
      setState({ context, question: asked, loading: false, answer: value });
    } catch {
      if (controller.signal.aborted || sequence.current !== request) return;
      setState({
        context,
        question: asked,
        loading: false,
        error:
          "We couldn’t retrieve a verified answer. Your match facts remain available above. Try again.",
      });
    } finally {
      if (sequence.current === request) active.current = null;
    }
  }

  return (
    <section
      className="copilot-panel"
      aria-labelledby="copilot-title"
      data-testid="match-copilot"
    >
      <div className="copilot-heading">
        <div className="copilot-heading-main">
          <span className="copilot-mark" aria-hidden="true">
            ?
          </span>
          <div>
            <span className="copilot-kicker">YOUR MATCH DESK</span>
            <h2 id="copilot-title">Ask the match.</h2>
            <p>Your question. The match facts. A clear answer.</p>
          </div>
        </div>
        <span className="copilot-context">
          {minute}′ · {mode === "fan" ? "Fan" : "Analyst"} view
        </span>
      </div>
      <div
        className="copilot-suggestions"
        role="group"
        aria-label="Suggested match questions"
      >
        {suggestions.map((suggestion) => (
          <button
            type="button"
            key={suggestion}
            disabled={disabled || loading}
            onClick={() => setQuestion(suggestion)}
          >
            {suggestion}
            <span aria-hidden="true">↗</span>
          </button>
        ))}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask();
        }}
      >
        <label htmlFor="match-question" className="sr-only">
          Your question about the match
        </label>
        <div className="copilot-compose">
          <textarea
            id="match-question"
            name="question"
            rows={2}
            maxLength={600}
            value={question}
            disabled={disabled}
            onChange={(event) => setQuestion(event.target.value)}
            aria-describedby="copilot-help copilot-count"
            placeholder="What has happened in the match so far?"
          />
          <div className="copilot-compose-footer">
            <span id="copilot-count">{question.length} / 600</span>
            {loading ? (
              <button className="copilot-cancel" type="button" onClick={cancel}>
                Cancel
              </button>
            ) : (
              <button
                className="copilot-submit"
                type="submit"
                disabled={disabled || !trimmed || trimmed.length > 600}
              >
                Ask the match <span aria-hidden="true">↗</span>
              </button>
            )}
          </div>
        </div>
        <p id="copilot-help" className="copilot-help">
          {disabled
            ? "Waiting for this replay snapshot…"
            : "Submitting pauses the replay. Answers use recorded evidence through minute " +
              minute +
              "."}
        </p>
      </form>
      {loading && (
        <div className="copilot-loading" role="status">
          <span aria-hidden="true" />
          Checking the recorded match facts…
        </div>
      )}
      {visible?.error && (
        <div className="copilot-error" role="alert">
          <p>{visible.error}</p>
          <button
            type="button"
            className="text-button"
            onClick={() => void ask()}
          >
            Retry question
          </button>
        </div>
      )}
      {answer && (
        <article
          className="copilot-answer"
          aria-live="polite"
          data-testid="copilot-answer"
        >
          <div className="copilot-answer-top">
            <span className="source-tag">
              {answer.source === "foundry"
                ? "AI-routed answer"
                : "Evidence-based answer"}
            </span>
            <span>Through {answer.as_of_minute}′</span>
          </div>
          <h3>{answer.question}</h3>
          <p className="copilot-answer-text">{answer.answer}</p>
          <p className="copilot-provenance">
            {answer.source === "foundry"
              ? "Foundry interpreted your question. The answer is rendered from verified match facts."
              : "This answer uses the evidence-based question matcher and recorded match facts."}
          </p>
          {(answer.facts.length > 0 ||
            answer.evidence_event_ids.length > 0) && (
            <details className="copilot-evidence" open={mode === "analyst"}>
              <summary>
                Inspect the evidence{" "}
                <span>{answer.evidence_event_ids.length} recorded events</span>
              </summary>
              {answer.facts.length > 0 && (
                <dl>
                  {answer.facts.map((fact, index) => (
                    <div key={index}>
                      <dt>{fact.label}</dt>
                      <dd>{fact.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {answer.evidence_event_ids.length > 0 && (
                <p
                  className="copilot-event-ids"
                  tabIndex={0}
                  aria-label="Supporting event IDs"
                >
                  <strong>Supporting event IDs</strong>
                  {answer.evidence_event_ids.join(", ")}
                </p>
              )}
            </details>
          )}
          {answer.limitations.length > 0 && (
            <div className="copilot-limitations">
              <strong>Evidence limits</strong>
              <ul>
                {answer.limitations.map((limitation, index) => (
                  <li key={index}>{limitation}</li>
                ))}
              </ul>
            </div>
          )}
        </article>
      )}
    </section>
  );
}
