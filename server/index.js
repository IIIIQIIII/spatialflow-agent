import cors from "cors";
import express from "express";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appRoot = path.resolve(__dirname, "..");
const distDir = path.join(appRoot, "dist");
const bundledDataRoot = path.join(appRoot, "demo-data");
const externalPipelineRoot = process.env.SPATIALFLOW_PIPELINE_ROOT;
const externalPipelineOutputs = externalPipelineRoot ? path.join(externalPipelineRoot, "outputs") : null;
const port = Number(process.env.PORT || 4188);
const app = express();

const externalPreferred = {
  rootRun: process.env.SPATIALFLOW_ROOT_RUN || "spatialflow-real-latest",
  baseRun: process.env.SPATIALFLOW_BASE_RUN || "base",
  reviewRun: process.env.SPATIALFLOW_REVIEW_RUN || "review",
  hitlRun: process.env.SPATIALFLOW_HITL_RUN || "hitl-v2",
};

const bundledPreferred = {
  rootRun: "default-run",
  baseRun: "base",
  reviewRun: "review",
  hitlRun: "hitl-v2",
};

function safeReadJson(file, fallback = {}) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

async function pickRun(outputsRoot, name, prefix) {
  const direct = path.join(outputsRoot, name);
  if (fs.existsSync(direct)) return name;
  const entries = await fsp.readdir(outputsRoot, { withFileTypes: true });
  const dirs = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith(prefix)) continue;
    const full = path.join(outputsRoot, entry.name);
    dirs.push({ name: entry.name, mtime: (await fsp.stat(full)).mtimeMs });
  }
  dirs.sort((a, b) => b.mtime - a.mtime);
  return dirs[0]?.name;
}

function artifact(rootDir, file, scope = "app") {
  if (!file) return null;
  const full = path.isAbsolute(file) ? file : path.join(rootDir, file);
  const rel = path.relative(rootDir, full).split(path.sep).join("/");
  return scope === "external" ? `/artifact-external/${rel}` : `/artifact/${rel}`;
}

function tsOf(data, fallback = null) {
  return typeof data?.ts_unix === "number" ? data.ts_unix : fallback;
}

function scaleDelta(rawSeconds) {
  if (rawSeconds <= 2) return 1.0;
  return Math.max(1.0, Math.min(5.8, Math.sqrt(rawSeconds) * 0.3));
}

function buildTimeline({ rootRun, spatial, depth, plan, baseEdit, baseVerify, review, revisedPlan, hitlEdit, hitlVerify }) {
  const runStarted = Number(rootRun.split("-").pop()) || tsOf(spatial, 0) || 0;
  const rawEvents = [
    { id: "intake", title: "Task intake", rawTs: runStarted, artifact: "input" },
    { id: "parse", title: "Room understanding", rawTs: tsOf(spatial, runStarted), artifact: "masks" },
    { id: "depth", title: "Depth and layout", rawTs: tsOf(depth, tsOf(spatial, runStarted)), artifact: "depth" },
    { id: "plan", title: "Action plan", rawTs: tsOf(plan, tsOf(depth, tsOf(spatial, runStarted))), artifact: "depth" },
    { id: "edit_v1", title: "Image edit v1", rawTs: tsOf(baseEdit, tsOf(plan, runStarted)), artifact: "v1" },
    { id: "verify_v1", title: "Verifier v1", rawTs: tsOf(baseVerify, tsOf(baseEdit, runStarted)), artifact: "v1" },
    { id: "review", title: "Visual review", rawTs: tsOf(review, tsOf(baseVerify, runStarted)), artifact: "v1" },
    { id: "user_feedback", title: "Human feedback", rawTs: Math.max(tsOf(review, runStarted) + 16, tsOf(revisedPlan, runStarted) - 8), artifact: "v1" },
    { id: "revise_plan", title: "Revision plan", rawTs: tsOf(revisedPlan, tsOf(review, runStarted)), artifact: "v1" },
    { id: "edit_v2", title: "Image edit v2", rawTs: tsOf(hitlEdit, tsOf(revisedPlan, runStarted)), artifact: "v2" },
    { id: "verify_v2", title: "Verifier v2", rawTs: tsOf(hitlVerify, tsOf(hitlEdit, runStarted)), artifact: "v2" },
  ];

  let cursor = 0;
  const events = rawEvents.map((event, index) => {
    if (index === 0) {
      return { ...event, atSeconds: 0, rawSeconds: 0 };
    }
    const rawDelta = Math.max(0, event.rawTs - rawEvents[index - 1].rawTs);
    cursor += scaleDelta(rawDelta);
    return {
      ...event,
      rawSeconds: Math.max(0, event.rawTs - runStarted),
      atSeconds: Number(cursor.toFixed(1)),
    };
  });

  const artifactReady = {};
  for (const event of events) {
    artifactReady[event.artifact] = event.atSeconds;
  }
  artifactReady.input = 0;

  return {
    runStarted,
    totalSeconds: Number((events.at(-1)?.atSeconds || 0).toFixed(1)),
    artifactReady,
    events,
  };
}

function sanitizeForDisplay(value) {
  return String(value || "")
    .replaceAll("default-run/base", "sample-run/base")
    .replaceAll("demo-data/default-run/base", "demo-data/sample-run/base")
    .replaceAll("<workspace>/", "")
    .replaceAll("<workspace>", "");
}

function bundledConfig() {
  const manifest = safeReadJson(path.join(bundledDataRoot, bundledPreferred.rootRun, "manifest.json"));
  return {
    mode: "bundled",
    rootDir: bundledDataRoot,
    outputsDir: bundledDataRoot,
    prompt: manifest.prompt || "把这个空房间变成北欧风客厅，保留地板和窗户结构。",
    feedback: manifest.feedback || "更空、更高级、减少植物、保留墙色和窗户，不要挡窗，地板颜色也尽量不要变",
    input: manifest.input || "demo-data/inputs/room-dataset.png",
    preferred: {
      rootRun: bundledPreferred.rootRun,
      baseRun: manifest?.dirs?.base || bundledPreferred.baseRun,
      reviewRun: manifest?.dirs?.review || bundledPreferred.reviewRun,
      hitlRun: manifest?.dirs?.hitl || bundledPreferred.hitlRun,
    },
  };
}

function externalConfig() {
  return {
    mode: "external",
    rootDir: externalPipelineRoot,
    outputsDir: externalPipelineOutputs,
    prompt: "把这个空房间变成北欧风客厅，保留地板和窗户结构。",
    feedback: "更空、更高级、减少植物、保留墙色和窗户，不要挡窗，地板颜色也尽量不要变",
    input: "inputs/room-dataset.png",
    preferred: externalPreferred,
  };
}

async function buildState() {
  const config = externalPipelineRoot ? externalConfig() : bundledConfig();
  const outputsRoot = config.outputsDir;
  const preferred = config.preferred;
  const rootRun = config.mode === "external"
    ? (fs.existsSync(path.join(outputsRoot, preferred.rootRun))
      ? preferred.rootRun
      : await pickRun(outputsRoot, preferred.rootRun, "spatialflow-real-"))
    : preferred.rootRun;
  const rootRunDir = path.join(outputsRoot, rootRun);
  const baseDir = path.join(rootRunDir, preferred.baseRun);
  const reviewDir = path.join(rootRunDir, preferred.reviewRun);
  const hitlDir = path.join(rootRunDir, preferred.hitlRun);

  const spatial = safeReadJson(path.join(baseDir, "room_spatial_parser.json"));
  const depth = safeReadJson(path.join(baseDir, "depth_layout.json"));
  const plan = safeReadJson(path.join(baseDir, "action_plan.json"));
  const baseEdit = safeReadJson(path.join(baseDir, "visual_edit_executor.json"));
  const hitlEdit = safeReadJson(path.join(hitlDir, "visual_edit_executor.json"));
  const baseVerify = safeReadJson(path.join(baseDir, "verification.json"));
  const hitlVerify = safeReadJson(path.join(hitlDir, "verification.json"));
  const review = safeReadJson(path.join(reviewDir, "review_points.json"), safeReadJson(path.join(baseDir, "review_points.json")));
  const revision = safeReadJson(path.join(hitlDir, "feedback_revision.json"));
  const revisedPlan = safeReadJson(path.join(hitlDir, "revised_action_plan.json"));
  const maskResults = spatial?.sam31_masks?.results || [];
  const timeline = buildTimeline({
    rootRun,
    spatial,
    depth,
    plan,
    baseEdit,
    baseVerify,
    review,
    revisedPlan,
    hitlEdit,
    hitlVerify,
  });

  return {
    run: {
      mode: config.mode,
      rootRun,
      baseRun: preferred.baseRun,
      reviewRun: preferred.reviewRun,
      hitlRun: preferred.hitlRun,
    },
    prompt: config.prompt,
    feedback: config.feedback,
    assets: {
      input: artifact(config.mode === "external" ? config.rootDir : appRoot, config.input, config.mode),
      resultV1: artifact(config.mode === "external" ? config.rootDir : appRoot, config.mode === "external" ? path.relative(config.rootDir, path.join(baseDir, "edited_room.png")) : path.relative(appRoot, path.join(baseDir, "edited_room.png")), config.mode),
      resultV2: artifact(config.mode === "external" ? config.rootDir : appRoot, config.mode === "external" ? path.relative(config.rootDir, path.join(hitlDir, "edited_room.png")) : path.relative(appRoot, path.join(hitlDir, "edited_room.png")), config.mode),
      masks: artifact(config.mode === "external" ? config.rootDir : appRoot, config.mode === "external" ? path.relative(config.rootDir, path.join(baseDir, "sam3_overlay.png")) : path.relative(appRoot, path.join(baseDir, "sam3_overlay.png")), config.mode),
      depth: artifact(config.mode === "external" ? config.rootDir : appRoot, config.mode === "external" ? path.relative(config.rootDir, path.join(baseDir, "depth_vis.png")) : path.relative(appRoot, path.join(baseDir, "depth_vis.png")), config.mode),
    },
    models: [
      { label: "Planner", value: "openai/gpt-5.4" },
      { label: "Primary image edit", value: "openai/gpt-image-2" },
      { label: "Segmentation", value: spatial?.sam31_masks?.model || "jetjodh/sam3.1" },
      { label: "Verifier", value: "gpt-5.4 + visual rules" },
    ],
    metrics: {
      masks: maskResults.reduce((sum, item) => sum + (item.instances?.length || 0), 0),
      prompts: maskResults.length,
      v1Score: baseVerify?.final_verdict?.score,
      v1Label: baseVerify?.final_verdict?.label,
      v2Score: hitlVerify?.final_verdict?.score,
      v2Label: hitlVerify?.final_verdict?.label,
      editModelV1: baseEdit?.selected_model,
      editModelV2: hitlEdit?.selected_model,
    },
    review: {
      model: review?.review_model || "openai/gpt-5.4",
      questions: (review?.questions || []).slice(0, 6),
      critique: review?.visual_critique || [],
    },
    revision: JSON.parse(JSON.stringify(revision), (_key, value) => (typeof value === "string" ? sanitizeForDisplay(value) : value)),
    timeline,
  };
}

app.use(cors());
app.use(express.json());

app.get("/api/state", async (_req, res) => {
  res.json(await buildState());
});

app.post("/api/refine", async (req, res) => {
  res.json({ status: "ready", feedback: req.body?.feedback || "", state: await buildState() });
});

app.get("/artifact/*", (req, res) => {
  const rel = decodeURIComponent(req.params[0] || "");
  const full = path.resolve(appRoot, rel);
  if (!full.startsWith(appRoot) || !fs.existsSync(full)) {
    res.status(404).send("not found");
    return;
  }
  res.sendFile(full);
});

app.get("/artifact-external/*", (req, res) => {
  if (!externalPipelineRoot) {
    res.status(404).send("not found");
    return;
  }
  const rel = decodeURIComponent(req.params[0] || "");
  const full = path.resolve(externalPipelineRoot, rel);
  if (!full.startsWith(externalPipelineRoot) || !fs.existsSync(full)) {
    res.status(404).send("not found");
    return;
  }
  res.sendFile(full);
});

app.use(express.static(distDir));
app.get("*", (_req, res) => {
  res.sendFile(path.join(distDir, "index.html"));
});

app.listen(port, "127.0.0.1", () => {
  console.log(`SpatialFlow Agent UI listening on http://127.0.0.1:${port}`);
});
