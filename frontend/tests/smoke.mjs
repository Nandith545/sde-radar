// A minimal end-to-end smoke test exercising the full user journey against
// a running instance of the app (register -> upload resume -> see matches ->
// update status -> reload -> persisted -> sign out).
//
// Usage:
//   npm run build && (cd ../backend && uvicorn app.main:app --port 8000 &)
//   BASE_URL=http://localhost:8000 npm run test:e2e
//
// Requires the `playwright` devDependency (already in package.json) and a
// Chromium build available to it -- `npx playwright install chromium` if
// you don't already have one.
import { chromium } from "playwright";
import { writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL || "http://localhost:8000";
const email = `friend${Date.now()}@example.com`;

const SAMPLE_RESUME = `Jordan Example
Senior Software Engineer, 8+ years of experience

Skills: Java, Spring Boot, Python, TypeScript, React, AWS, Kafka, Docker,
Kubernetes, PostgreSQL, LangChain, RAG.

Experience: Built microservices and distributed systems at scale, led
migration to Kubernetes, implemented CI/CD pipelines.
`;
const resumePath = join(tmpdir(), `sample-resume-${Date.now()}.txt`);
writeFileSync(resumePath, SAMPLE_RESUME);

const launchOpts = { headless: true };
if (process.env.PLAYWRIGHT_CHROMIUM_PATH) launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;

const browser = await chromium.launch(launchOpts);
const page = await browser.newPage();
const consoleErrors = [];
page.on("pageerror", (err) => consoleErrors.push("pageerror: " + err.message));

try {
  console.log("1. Load app, should redirect to /login");
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForURL("**/login");

  console.log("2. Go to register, fill form, submit");
  await page.click("text=Create an account");
  await page.waitForURL("**/register");
  await page.waitForTimeout(300);

  // Auth affordances, checked here rather than in a separate spec so they
  // ride the same real browser against the real backend.
  // Caps Lock is deliberately absent: Chromium does not emulate the modifier
  // state through CDP, so getModifierState("CapsLock") is always false in
  // Playwright and any assertion on it would pass for the wrong reason.
  if ((await page.evaluate(() => document.activeElement?.id)) !== "fullName") {
    throw new Error("Register form did not autofocus its first field");
  }
  await page.fill("#email", "not-an-email");
  await page.locator("#email").blur();
  await page.waitForTimeout(200);
  if (!(await page.textContent("body")).includes("doesn't look like an email")) {
    throw new Error("Inline email validation did not fire");
  }
  if (!(await page.isDisabled('button:has-text("Create account")'))) {
    throw new Error("Submit stayed enabled with an invalid email");
  }
  await page.fill("#password", "secret123");
  if ((await page.getAttribute("#password", "type")) !== "password") {
    throw new Error("Password field is not masked by default");
  }
  await page.click('button[aria-label="Show password"]');
  if ((await page.getAttribute("#password", "type")) !== "text") {
    throw new Error("Reveal toggle did not unmask the password");
  }
  await page.click('button[aria-label="Hide password"]');

  await page.fill("#fullName", "Friend Tester");
  await page.fill("#email", email);
  await page.fill("#password", "supersecure123");
  await page.click('button:has-text("Create account")');

  console.log("3. Should land on dashboard, resume banner visible");
  await page.waitForURL(BASE + "/");
  await page.waitForSelector("text=Upload your resume to get matched jobs");

  console.log("4. Set search targets, then upload resume file");
  await page.fill("#onboard-city", "Seattle, WA");
  await page.fill("#onboard-titles", "Software Engineer, Backend Engineer");
  const fileInput = await page.$("#resume-file");
  await fileInput.setInputFiles(resumePath);
  await page.waitForSelector("text=Upload your resume to get matched jobs", { state: "detached", timeout: 15000 });

  console.log("5. Job cards should render with scores");
  await page.waitForSelector(".card");
  const cardCount = await page.$$eval(".card", (els) => els.length);
  console.log("   card count:", cardCount);
  if (cardCount === 0) throw new Error("Expected at least one job card");

  console.log("6. Change status of first card to Applied");
  await page.selectOption(".status-select >> nth=0", "applied");
  await page.waitForTimeout(500);

  console.log("7. Check stats updated");
  const appliedStat = await page.$eval(".stats .stat:nth-child(3) .n", (el) => el.textContent);
  if (appliedStat !== "1") throw new Error(`Expected applied stat to be 1, got ${appliedStat}`);

  console.log("8. Reload page, confirm session + data persist");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".card");
  const statusAfterReload = await page.$eval(".status-select", (el) => el.value);
  if (statusAfterReload !== "applied") throw new Error("Status did not persist across reload");

  console.log("9. Sign out returns to login");
  await page.click('button:has-text("Sign out")');
  await page.waitForURL("**/login");

  // Registering and logging in take different code paths -- register posts
  // JSON, login posts an OAuth2 password form. Only exercising register let
  // a broken Content-Type on the login request ship to production.
  console.log("10. Log back in with the same credentials");
  const loginStatuses = [];
  page.on("response", (r) => {
    if (r.url().includes("/api/auth/login")) loginStatuses.push(r.status());
  });
  await page.fill("#email", email);
  await page.fill("#password", "supersecure123");
  // Unchecked, so this also asserts "keep me signed in" actually routes the
  // token to sessionStorage rather than just rendering a checkbox.
  await page.uncheck("#remember");
  await page.click('button:has-text("Sign in")');
  await page.waitForURL(BASE + "/", { timeout: 15000 });
  if (loginStatuses.some((s) => s !== 200)) {
    throw new Error(`Login request did not return 200: ${loginStatuses.join(", ")}`);
  }
  const stored = await page.evaluate(() => ({
    local: localStorage.getItem("sde_radar_token"),
    session: sessionStorage.getItem("sde_radar_token"),
  }));
  if (stored.local || !stored.session) {
    throw new Error("Unchecked 'keep me signed in' did not confine the token to sessionStorage");
  }

  console.log("11. Session is real: data still there after login");
  await page.waitForSelector(".card");
  const statusAfterLogin = await page.$eval(".status-select", (el) => el.value);
  if (statusAfterLogin !== "applied") {
    throw new Error("Status did not survive a fresh login");
  }

  if (consoleErrors.length) console.log("Non-fatal console errors:", consoleErrors);
  console.log("\nSMOKE TEST PASSED");
} catch (err) {
  console.error("SMOKE TEST FAILED:", err);
  process.exitCode = 1;
} finally {
  await browser.close();
  unlinkSync(resumePath);
}
