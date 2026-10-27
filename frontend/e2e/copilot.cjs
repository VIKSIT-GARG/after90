/* Real HTTP/browser coverage for the evidence-grounded match question desk. */
const { chromium } = require("playwright");
const AxeBuilder = require("@axe-core/playwright").default;
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const output = process.env.AFTER90_ARTIFACTS || "/tmp/after90-browser-evidence";
(async () => {
  await fs.mkdir(output, { recursive: true });
  let launch = { headless: true };
  if (process.env.AFTER90_CHROMIUM_MODULE) {
    const runtime = (
      await import(pathToFileURL(process.env.AFTER90_CHROMIUM_MODULE).href)
    ).default;
    launch = {
      ...launch,
      executablePath:
        process.env.AFTER90_CHROMIUM_EXECUTABLE ||
        (await runtime.executablePath()),
      args: runtime.args,
    };
  } else if (process.env.AFTER90_CHROMIUM_EXECUTABLE) {
    launch.executablePath = process.env.AFTER90_CHROMIUM_EXECUTABLE;
  }
  const browser = await chromium.launch(launch);
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const errors = [],
    requests = [],
    accessibility = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/copilot"))
      requests.push(request.postDataJSON());
  });
  const answer = page.getByTestId("copilot-answer");
  const question = page.getByLabel("Your question about the match", {
    exact: true,
  });
  const submit = page.getByRole("button", {
    name: "Ask the match",
    exact: true,
  });
  async function seek(minute) {
    await page.locator("#minute-slider").evaluate((input, value) => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      ).set.call(input, String(value));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }, minute);
    await page.waitForFunction(
      (value) =>
        document.querySelector(".clock")?.textContent ===
        (value === 90 ? "Full time" : String(value).padStart(2, "0") + ":00"),
      minute,
    );
    await submit.waitFor();
    await page.waitForFunction(
      () => !document.querySelector("#match-question")?.disabled,
    );
  }
  async function ask(text) {
    await question.fill(text);
    const pending = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/copilot"),
    );
    await submit.click();
    const response = await pending;
    assert.equal(response.status(), 200);
    await answer.waitFor();
    return response.json();
  }
  async function audit(label) {
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    accessibility.push({
      label,
      violations: result.violations.map((item) => ({
        id: item.id,
        impact: item.impact,
        nodes: item.nodes.map((node) => ({
          target: node.target,
          failureSummary: node.failureSummary,
        })),
      })),
    });
  }
  try {
    await page.goto(process.env.AFTER90_BASE_URL || "http://127.0.0.1:8000");
    await page.locator(".clock").waitFor();
    await seek(29);
    await page
      .getByRole("button", { name: "Who's leading?", exact: true })
      .click();
    assert.equal(
      requests.length,
      0,
      "suggestion selection should not request generation",
    );
    await page
      .getByRole("button", { name: "Play replay", exact: true })
      .click();
    const first = await ask("Who's leading?");
    assert.equal(first.as_of_minute, 29);
    assert.equal(first.topic, "score");
    assert.equal(
      first.source,
      "template",
      "offline browser check must not claim a real model request",
    );
    assert.equal(first.metadata.provider_attempted, false);
    assert.match(first.answer, /Northstar Quay 1–0 Copper Vale/);
    assert.match(await answer.textContent(), /Evidence-based answer/);
    assert.doesNotMatch(await answer.textContent(), /AI-routed answer/);
    await page
      .getByRole("button", { name: "Play replay", exact: true })
      .waitFor();
    assert.equal(
      await page.locator(".clock").textContent(),
      "29:00",
      "Ask should pause playback at its cutoff",
    );
    await answer.locator("summary").click();
    assert.match(await answer.textContent(), /Supporting event IDs/);
    assert.ok(first.evidence_event_ids.length > 0);
    await page.screenshot({
      path: path.join(output, "copilot-desktop.png"),
      fullPage: true,
    });
    await audit("copilot desktop score evidence open");

    await seek(90);
    assert.equal(
      await answer.count(),
      0,
      "seeking must immediately hide the older answer",
    );
    assert.equal(
      requests.length,
      1,
      "clock changes must not automatically generate answers",
    );
    await page.getByRole("button", { name: "Analyst", exact: true }).click();
    assert.equal(
      requests.length,
      1,
      "audience switches must not automatically generate answers",
    );
    const shots = await ask("Compare the shots");
    assert.equal(shots.topic, "shots");
    assert.equal(shots.as_of_minute, 90);
    assert.equal(requests.at(-1).mode, "analyst");
    assert.match(shots.answer, /10.*6.*shots/);
    assert.equal(await answer.locator("details").getAttribute("open"), "");
    assert.match(await answer.textContent(), /Difference/);
    await audit("copilot desktop full-time Analyst evidence open");
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await answer.scrollIntoViewIfNeeded();
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `copilot overflow at ${width}`,
      );
      await page.screenshot({
        path: path.join(output, `copilot-mobile-${width}.png`),
        fullPage: true,
      });
      await audit(`copilot mobile ${width} answer evidence open`);
    }
    await question.focus();
    await page.keyboard.press("Tab");
    assert.equal(
      await submit.evaluate((button) => button === document.activeElement),
      true,
      "question should tab to its submit control",
    );
    assert.deepEqual(errors, []);
    const report = {
      status: accessibility.some((item) => item.violations.length)
        ? "failed"
        : "passed",
      browser: browser.version(),
      requests: requests.length,
      assertions: [
        "explicit generation",
        "playback pause",
        "29-minute score",
        "90-minute shots",
        "honest source",
        "canonical evidence",
        "replay stale clearing",
        "keyboard",
        "390/320px overflow",
      ],
      runtime_errors: errors,
      accessibility,
    };
    await fs.writeFile(
      path.join(output, "copilot-report.json"),
      JSON.stringify(report, null, 2),
    );
    assert.equal(
      report.status,
      "passed",
      "inspect copilot-report.json for accessibility violations",
    );
    console.log(
      JSON.stringify({
        status: "passed",
        browser: browser.version(),
        copilot_accessibility_states: accessibility.length,
        requests: requests.length,
        runtime_errors: errors.length,
      }),
    );
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(async (error) => {
  let report = {};
  try {
    report = JSON.parse(
      await fs.readFile(path.join(output, "copilot-report.json"), "utf8"),
    );
  } catch {}
  await fs.writeFile(
    path.join(output, "copilot-report.json"),
    JSON.stringify(
      { ...report, status: "failed", error: error.message },
      null,
      2,
    ),
  );
  console.error(error);
  process.exitCode = 1;
});
