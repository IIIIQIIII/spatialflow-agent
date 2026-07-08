import { spawn } from "node:child_process";
import { mkdir, readdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const outDir = path.join(appRoot, "outputs", "spatialflow-chat-demo");
const tmpDir = path.join(outDir, "tmp-video");
const finalVideo = path.join(outDir, "spatialflow_chat_style_demo.mp4");
const finalPoster = path.join(outDir, "spatialflow_chat_style_demo_frame.png");
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = 4188;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", ...options });
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`))));
  });
}

async function waitForServer() {
  for (let i = 0; i < 80; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/state`);
      if (res.ok) return;
    } catch {}
    await wait(250);
  }
  throw new Error("server did not become ready");
}

async function isServerUp() {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/state`);
    return res.ok;
  } catch {
    return false;
  }
}

async function main() {
  await rm(outDir, { recursive: true, force: true });
  await mkdir(tmpDir, { recursive: true });
  await run("npm", ["run", "build"], { cwd: appRoot });

  let server = null;
  if (!(await isServerUp())) {
    server = spawn("npm", ["run", "server"], {
      cwd: appRoot,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PORT: String(port) },
    });
    server.stdout.on("data", (chunk) => process.stdout.write(chunk));
    server.stderr.on("data", (chunk) => process.stderr.write(chunk));
  }

  try {
    await waitForServer();
    const state = await fetch(`http://127.0.0.1:${port}/api/state`).then((res) => res.json());
    const totalSeconds = Math.max(20, Number(state?.timeline?.totalSeconds || 42));
    const browser = await chromium.launch({
      headless: false,
      executablePath: existsSync(chromePath) ? chromePath : undefined,
      args: ["--window-size=1920,1080", "--hide-scrollbars"],
    });
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      deviceScaleFactor: 1,
      recordVideo: { dir: tmpDir, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();
    const recordedVideo = page.video();
    await page.goto(`http://127.0.0.1:${port}`, { waitUntil: "networkidle" });
    await wait(700);
    await page.click(".sf-run-button");
    await wait(totalSeconds * 1000 + 1800);
    await page.screenshot({ path: finalPoster, fullPage: false });
    await context.close();
    const recordedPath = await recordedVideo.path();
    await browser.close();

    const videos = (await readdir(tmpDir)).filter((name) => name.endsWith(".webm"));
    const fallbackPath = videos.sort().map((name) => path.join(tmpDir, name)).at(-1);
    const sourceVideo = recordedPath || fallbackPath;
    if (!sourceVideo) throw new Error("No video recorded");
    await run("ffmpeg", ["-y", "-i", sourceVideo, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", finalVideo]);
    console.log(finalVideo);
  } finally {
    if (server) server.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
