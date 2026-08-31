// Captures screenshots of the running app, so you can eyeball a UI change
// without deploying it anywhere. Called automatically by scripts/verify.sh;
// can also be run directly:
//
//   BASE_URL=http://localhost:8000 OUT_DIR=./shots node tests/screenshot.mjs
//
// Writes: login.png, dashboard.png, dashboard-mobile.png, board.png,
//         board-mobile.png
import { chromium } from "playwright";
import { writeFileSync, unlinkSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL || "http://localhost:8000";
const OUT_DIR = process.env.OUT_DIR || ".verify-artifacts";
mkdirSync(OUT_DIR, { recursive: true });

const email = `shot${Date.now()}@example.com`;

const SAMPLE_RESUME = `Jordan Example
Senior Software Engineer, 8+ years of experience

Skills: Java, Spring Boot, Python, TypeScript, React, AWS, Kafka, Docker,
Kubernetes, PostgreSQL, LangChain, RAG.

Experience: Built microservices and distributed systems at scale.
`;
const resumePath = join(tmpdir(), `shot-resume-${Date.now()}.txt`);
writeFileSync(resumePath, SAMPLE_RESUME);

const launchOpts = { headless: true };
if (process.env.PLAYWRIGHT_CHROMIUM_PATH) launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;

const browser = await chromium.launch(launchOpts);

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForURL("**/login");
  await page.screenshot({ path: join(OUT_DIR, "login.png") });

  await page.click("text=Create an account");
  await page.waitForURL("**/register");
  await page.fill("#fullName", "Screenshot Tester");
  await page.fill("#email", email);
  await page.fill("#password", "supersecure123");
  await page.click('button:has-text("Create account")');

  // Targets are asked for on the dashboard's onboarding banner, not on the
  // register form -- the same fields the smoke test drives.
  await page.waitForURL(BASE + "/");
  await page.fill("#onboard-city", "Seattle, WA");
  await page.fill("#onboard-titles", "Software Engineer, Backend Engineer");
  const fileInput = await page.$("#resume-file");
  await fileInput.setInputFiles(resumePath);
  await page.waitForSelector("text=Upload your resume to get matched jobs", { state: "detached", timeout: 15000 });

  await page.waitForSelector(".card");
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(OUT_DIR, "dashboard.png") });

  // Phone-sized viewport -- the layout is responsive and regressions here
  // are easy to miss when you only ever look at a desktop window.
  await page.setViewportSize({ width: 390, height: 1200 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: join(OUT_DIR, "dashboard-mobile.png") });

  // A single board's page, reached the way a user reaches it: by picking the
  // board out of the dropdown. Captured at both sizes because it carries the
  // same controls bar as the feed, plus one more control.
  await page.setViewportSize({ width: 1280, height: 1400 });
  const board = await page.$eval(".board-select option:not([value='all'])", (o) => o.value);
  await page.selectOption(".board-select", board);
  await page.waitForURL("**/boards/" + board + "*");
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(OUT_DIR, "board.png") });

  await page.setViewportSize({ width: 390, height: 1200 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: join(OUT_DIR, "board-mobile.png") });

  console.log(`Screenshots written to ${OUT_DIR}/`);
} finally {
  await browser.close();
  try {
    unlinkSync(resumePath);
  } catch {
    /* already gone */
  }
}
