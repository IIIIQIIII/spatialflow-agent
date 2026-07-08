#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import time
import traceback

import cv2
import numpy as np
import torch
from PIL import Image

MODELS = [
    "Qwen3.5-9B / Qwen3.5-27B",
    "SigLIP 2 giant/SO400M",
    "Qwen3-VL fallback",
    "mask/depth/box geometry rules",
]


def load_image_rgb(path, max_side=1280):
    image = Image.open(path).convert("RGB")
    w, h = image.size
    scale = min(max_side / max(w, h), 1.0)
    if scale < 1.0:
        image = image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return image


def extract_json(text):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def qwen35_review(before, after):
    from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration

    model_id = "Qwen/Qwen3.5-9B"
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
    )
    processor = AutoProcessor.from_pretrained(model_id)
    prompt = """
You are a strict visual verifier for an interior design agent. Compare image A (before) and image B (after).
Return ONLY valid JSON with this schema:
{
  "structure_preservation": {"score": 0-1, "notes": "..."},
  "style_alignment": {"score": 0-1, "notes": "..."},
  "object_plausibility": {"score": 0-1, "notes": "..."},
  "artifact_quality": {"score": 0-1, "notes": "..."},
  "floor_window_wall_preserved": boolean,
  "major_failures": [string],
  "verdict": "pass" | "repair" | "fail"
}
Task: transform an empty room into a realistic Nordic / Scandinavian living room while preserving floor, windows, walls, camera viewpoint, and room structure.
"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": before},
                {"type": "image", "image": after},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[before, after], return_tensors="pt").to("cuda")
    generated = model.generate(**inputs, max_new_tokens=512, do_sample=False)
    trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated)]
    decoded = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
    return model_id, decoded, extract_json(decoded)


def siglip2_scores(before, after):
    from transformers import AutoModel, AutoProcessor

    model_id = "google/siglip2-so400m-patch14-384"
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id, torch_dtype=torch.bfloat16, device_map="cuda")
    texts = [
        "a realistic Nordic Scandinavian living room with sofa, coffee table, rug, plants, warm natural light",
        "an empty room with wood floors and windows",
        "a distorted interior image with broken geometry and artifacts",
    ]
    inputs = processor(text=texts, images=[after], padding=True, return_tensors="pt").to("cuda")
    with torch.no_grad():
        outputs = model(**inputs)
    logits = outputs.logits_per_image[0].float().softmax(dim=-1).detach().cpu().numpy()
    return {
        "model": model_id,
        "scores": {
            "nordic_living_room": float(logits[0]),
            "empty_room": float(logits[1]),
            "distorted_artifacts": float(logits[2]),
        },
    }


def geometry_rules(before_path, after_path):
    before = cv2.imread(str(before_path), cv2.IMREAD_COLOR)
    after = cv2.imread(str(after_path), cv2.IMREAD_COLOR)
    if before is None or after is None:
        return {"status": "missing_image"}
    after = cv2.resize(after, (before.shape[1], before.shape[0]))
    gray_b = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    gray_a = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    h, w = gray_b.shape
    mask_structure = np.zeros_like(gray_b, dtype=np.uint8)
    mask_structure[: int(h * 0.58), :] = 255
    edges_b = cv2.Canny(gray_b, 80, 160)
    edges_a = cv2.Canny(gray_a, 80, 160)
    eb = (edges_b[mask_structure > 0] > 0).astype(np.float32)
    ea = (edges_a[mask_structure > 0] > 0).astype(np.float32)
    edge_similarity = float(1.0 - abs(eb.mean() - ea.mean()))
    floor_b = before[int(h * 0.62) :, :, :].astype(np.float32)
    floor_a = after[int(h * 0.62) :, :, :].astype(np.float32)
    floor_delta = float(np.mean(np.abs(floor_b - floor_a)) / 255.0)
    return {
        "status": "ok",
        "structure_edge_density_similarity": max(0.0, min(1.0, edge_similarity)),
        "floor_region_mean_delta": floor_delta,
        "floor_preservation_pass": floor_delta < 0.42,
    }


def verdict(qwen_json, siglip, geom):
    scores = []
    if qwen_json:
        for key in ["structure_preservation", "style_alignment", "object_plausibility", "artifact_quality"]:
            val = qwen_json.get(key, {}).get("score")
            if isinstance(val, (int, float)):
                scores.append(float(val))
    if siglip:
        scores.append(siglip["scores"]["nordic_living_room"])
    if geom.get("status") == "ok":
        scores.append(geom["structure_edge_density_similarity"])
    avg = float(np.mean(scores)) if scores else 0.0
    if avg >= 0.72 and geom.get("floor_preservation_pass", False):
        label = "pass"
    elif avg >= 0.55:
        label = "repair"
    else:
        label = "fail"
    return {"score": avg, "label": label}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--spatial", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    before_path = pathlib.Path(args.before)
    after_path = pathlib.Path(args.after)
    before = load_image_rgb(before_path)
    after = load_image_rgb(after_path)
    attempts = []
    qwen_raw = None
    qwen_json = None
    qwen_model = None
    siglip = None

    try:
        started = time.time()
        qwen_model, qwen_raw, qwen_json = qwen35_review(before, after)
        attempts.append({"model": qwen_model, "status": "ok", "seconds": round(time.time() - started, 3)})
    except Exception as exc:
        attempts.append(
            {
                "model": "Qwen/Qwen3.5-9B",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "trace_tail": traceback.format_exc().splitlines()[-8:],
            }
        )

    try:
        started = time.time()
        siglip = siglip2_scores(before, after)
        attempts.append({"model": siglip["model"], "status": "ok", "seconds": round(time.time() - started, 3)})
    except Exception as exc:
        attempts.append(
            {
                "model": "google/siglip2-so400m-patch14-384",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "trace_tail": traceback.format_exc().splitlines()[-8:],
            }
        )

    geom = geometry_rules(before_path, after_path)
    final = verdict(qwen_json, siglip, geom)
    data = {
        "stage": "verifier_loop",
        "status": "ok" if attempts else "failed",
        "target_models": MODELS,
        "inputs": {
            "before": args.before,
            "after": args.after,
            "spatial": args.spatial,
            "layout": args.layout,
        },
        "attempts": attempts,
        "qwen_review_model": qwen_model,
        "qwen_review_raw": qwen_raw,
        "qwen_review_json": qwen_json,
        "siglip2": siglip,
        "geometry_rules": geom,
        "final_verdict": final,
        "ts_unix": int(time.time()),
    }
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
