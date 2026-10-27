const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const { JSDOM } = require("jsdom");

function answer(question, minute, overrides = {}) {
  return {
    question,
    answer: "Northstar Quay leads 1–0 at minute 29.",
    as_of_minute: minute,
    topic: "score",
    source: "template",
    metadata: {
      source: "template",
      provider_attempted: false,
      fallback_reason: "not_configured",
      model_version: "private-model-name",
      prompt_version: "test",
      latency_ms: 1,
    },
    evidence_event_ids: ["e071", "e072"],
    facts: [
      { label: "Northstar Quay goals", value: 1 },
      { label: "Copper Vale goals", value: 0 },
    ],
    limitations: ["Recorded synthetic events only."],
    synthetic: true,
    ...overrides,
  };
}
async function mount(props = {}) {
  const dom = new JSDOM('<div id="root"></div>');
  global.window = dom.window;
  global.document = dom.window.document;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const { createRoot } = require("react-dom/client");
  const requests = [];
  const context = {
    exports: {},
    require,
    AbortController,
    fetch: (url, options) =>
      new Promise((resolve, reject) =>
        requests.push({ url, options, resolve, reject }),
      ),
  };
  const source = fs.readFileSync("src/MatchCopilot.tsx", "utf8");
  vm.runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
      },
    }).outputText,
    context,
  );
  const Component = context.exports.default;
  const root = createRoot(document.querySelector("#root"));
  let current = { minute: 29, mode: "fan", ...props };
  const render = async (next) => {
    current = { ...current, ...next };
    await React.act(async () =>
      root.render(React.createElement(Component, current)),
    );
  };
  await render({});
  const click = async (target) => {
    assert.ok(target);
    await React.act(async () => target.click());
  };
  const button = (text) =>
    [...document.querySelectorAll("button")].find((node) =>
      node.textContent.includes(text),
    );
  const ask = async (suggestion = "Who's leading?") => {
    await click(button(suggestion));
    await click(button("Ask the match"));
  };
  const respond = async (request, value, ok = true) =>
    React.act(async () => request.resolve({ ok, json: async () => value }));
  return {
    dom,
    requests,
    render,
    click,
    button,
    ask,
    respond,
    close: async () => {
      await React.act(async () => root.unmount());
      dom.window.close();
      delete global.window;
      delete global.document;
      delete global.IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

test("only explicit submission requests an answer with the current cutoff and audience", async () => {
  let paused = 0;
  const app = await mount({ onAsk: () => paused++ });
  try {
    assert.equal(app.requests.length, 0);
    assert.equal(document.querySelector("textarea").maxLength, 600);
    await app.click(app.button("Who's leading?"));
    assert.equal(
      app.requests.length,
      0,
      "choosing a question must not spend provider budget",
    );
    assert.equal(document.querySelector("textarea").value, "Who's leading?");
    await app.click(app.button("Ask the match"));
    assert.equal(paused, 1);
    assert.equal(app.requests.length, 1);
    const request = app.requests[0];
    assert.equal(request.url, "/api/matches/demo/copilot");
    assert.equal(request.options.method, "POST");
    assert.deepEqual(JSON.parse(request.options.body), {
      question: "Who's leading?",
      minute: 29,
      mode: "fan",
    });
    assert.match(
      document.querySelector('[role="status"]').textContent,
      /Checking/,
    );
    await app.respond(request, answer("Who's leading?", 29));
    const result = document.querySelector('[data-testid="copilot-answer"]');
    assert.match(result.textContent, /Evidence-based answer/);
    assert.match(result.textContent, /Northstar Quay leads 1–0/);
    assert.match(result.textContent, /e071, e072/);
    assert.doesNotMatch(result.textContent, /private-model-name/);
    assert.equal(result.querySelector("details").open, false);
  } finally {
    await app.close();
  }
});

test("replay and mode changes abort requests, ignore late responses and hide accepted answers without new calls", async () => {
  const app = await mount();
  try {
    await app.ask();
    const stale = app.requests[0];
    await app.render({ minute: 28, mode: "analyst" });
    assert.equal(stale.options.signal.aborted, true);
    assert.equal(app.requests.length, 1);
    await app.respond(
      stale,
      answer("Who's leading?", 29, { answer: "STALE FUTURE ANSWER" }),
    );
    assert.doesNotMatch(document.body.textContent, /STALE FUTURE ANSWER/);
    await app.ask("Compare the shots");
    const current = app.requests[1];
    assert.deepEqual(JSON.parse(current.options.body), {
      question: "Compare the shots",
      minute: 28,
      mode: "analyst",
    });
    await app.respond(
      current,
      answer("Compare the shots", 28, {
        topic: "shots",
        answer: "RECORDED SHOT COMPARISON",
      }),
    );
    assert.match(document.body.textContent, /RECORDED SHOT COMPARISON/);
    assert.equal(document.querySelector(".copilot-evidence").open, true);
    await app.render({ mode: "fan" });
    assert.equal(
      document.querySelector('[data-testid="copilot-answer"]'),
      null,
    );
    assert.equal(app.requests.length, 2);
    await app.render({ minute: 10 });
    assert.equal(app.requests.length, 2);
  } finally {
    await app.close();
  }
});

test("future or mismatched answers are rejected and retry can show proven AI routing", async () => {
  const app = await mount();
  try {
    await app.ask();
    await app.respond(
      app.requests[0],
      answer("Who's leading?", 90, { answer: "FUTURE FULL TIME RESULT" }),
    );
    assert.equal(
      document.querySelector('[data-testid="copilot-answer"]'),
      null,
    );
    assert.doesNotMatch(document.body.textContent, /FUTURE FULL TIME RESULT/);
    assert.ok(document.querySelector('[role="alert"]'));
    await app.click(app.button("Retry question"));
    await app.respond(
      app.requests[1],
      answer("Who's leading?", 29, {
        source: "foundry",
        metadata: {
          source: "foundry",
          provider_attempted: true,
          model_version: "private-model-name",
        },
      }),
    );
    assert.match(
      document.querySelector('[data-testid="copilot-answer"]').textContent,
      /AI-routed answer/,
    );
    assert.match(
      document.body.textContent,
      /answer is rendered from verified match facts/,
    );
    assert.doesNotMatch(document.body.textContent, /private-model-name/);
  } finally {
    await app.close();
  }
});

test("unproven AI source, failed transport and cancelled requests never display an invented answer", async () => {
  const app = await mount();
  try {
    await app.ask();
    await app.respond(
      app.requests[0],
      answer("Who's leading?", 29, {
        source: "foundry",
        metadata: { source: "foundry", provider_attempted: false },
      }),
    );
    assert.equal(
      document.querySelector('[data-testid="copilot-answer"]'),
      null,
    );
    await app.click(app.button("Retry question"));
    await React.act(async () =>
      app.requests[1].reject(new Error("SECRET provider exception")),
    );
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /Try again/,
    );
    assert.doesNotMatch(document.body.textContent, /SECRET/);
    await app.click(app.button("Retry question"));
    await app.click(app.button("Cancel"));
    assert.equal(app.requests[2].options.signal.aborted, true);
    await app.respond(
      app.requests[2],
      answer("Who's leading?", 29, { answer: "CANCELLED ANSWER" }),
    );
    assert.doesNotMatch(document.body.textContent, /CANCELLED ANSWER/);
    await app.render({ disabled: true });
    assert.equal(document.querySelector("textarea").disabled, true);
    assert.equal(app.button("Ask the match").disabled, true);
    assert.equal(app.requests.length, 3);
  } finally {
    await app.close();
  }
});
