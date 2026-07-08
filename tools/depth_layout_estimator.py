#!/usr/bin/env python3
import argparse
import json
import pathlib
import time
import traceback

import numpy as np
from PIL import Image

MODELS = [
    "Depth Anything 3 / DA3METRIC-LARGE",
    "Apple Depth Pro",
    "UniDepthV2",
    "Depth Anything V2 Large fallback",
    "RANSAC/vanishing-line geometry",
]


def normalize_depth(depth):
    arr = np.asarray(depth, dtype=np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = np.percentile(arr, [2, 98])
    if hi <= lo:
        hi = float(arr.max() or 1.0)
        lo = float(arr.min())
    norm = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1)
    return arr, norm


def save_depth_outputs(depth, out_dir):
    depth_arr, norm = normalize_depth(depth)
    npy_path = out_dir / "depth.npy"
    png_path = out_dir / "depth_vis.png"
    np.save(npy_path, depth_arr)
    Image.fromarray((norm * 255).astype(np.uint8), mode="L").save(png_path)
    return depth_arr, npy_path, png_path


def coarse_layout_from_depth(depth_arr):
    h, w = depth_arr.shape[:2]
    top = float(np.median(depth_arr[: max(1, h // 5), :]))
    mid = float(np.median(depth_arr[h // 3 : max(h // 3 + 1, 2 * h // 3), :]))
    bottom = float(np.median(depth_arr[max(0, 4 * h // 5) :, :]))
    center = float(np.median(depth_arr[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]))
    return {
        "image_size": {"width": w, "height": h},
        "room_envelope": {
            "type": "single_view_coarse_layout",
            "floor_region_hint": [0, int(h * 0.58), w, h],
            "back_wall_region_hint": [0, 0, w, int(h * 0.62)],
            "left_wall_region_hint": [0, 0, int(w * 0.28), h],
            "right_wall_region_hint": [int(w * 0.72), 0, w, h],
            "depth_medians": {
                "top": top,
                "middle": mid,
                "bottom": bottom,
                "center": center,
            },
        },
        "free_space": {
            "type": "heuristic_floor_band",
            "bbox_xyxy": [int(w * 0.12), int(h * 0.62), int(w * 0.88), int(h * 0.96)],
            "purpose": "candidate furniture placement region before segmentation refinement",
        },
        "constraints": [
            "preserve windows and wall boundaries",
            "preserve floor material and perspective",
            "avoid placing objects outside the floor/free-space band",
            "verify furniture grounding against depth discontinuities",
        ],
    }


def run_da3(image_path, out_dir):
    import torch
    from depth_anything_3.api import DepthAnything3

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = DepthAnything3.from_pretrained("depth-anything/DA3METRIC-LARGE")
    model = model.to(device=device)
    pred = model.inference(
        [str(image_path)],
        export_dir=str(out_dir / "da3_export"),
        export_format="npz",
    )
    depth = np.asarray(pred.depth[0], dtype=np.float32)
    conf = np.asarray(pred.conf[0], dtype=np.float32) if getattr(pred, "conf", None) is not None else None
    return {
        "selected_model": "depth-anything/DA3METRIC-LARGE",
        "depth": depth,
        "confidence": conf,
        "intrinsics": np.asarray(pred.intrinsics[0]).tolist()
        if getattr(pred, "intrinsics", None) is not None
        else None,
        "extrinsics": np.asarray(pred.extrinsics[0]).tolist()
        if getattr(pred, "extrinsics", None) is not None
        else None,
    }


def run_depth_pro(image_path):
    import torch
    from transformers import pipeline

    pipe = pipeline(
        "depth-estimation",
        model="apple/DepthPro-hf",
        device=0 if torch.cuda.is_available() else -1,
        dtype=torch.float16 if torch.cuda.is_available() else None,
    )
    result = pipe(Image.open(image_path).convert("RGB"))
    depth = result.get("predicted_depth", result.get("depth"))
    if hasattr(depth, "detach"):
        depth = depth.detach().cpu().float().numpy()
    elif isinstance(depth, Image.Image):
        depth = np.asarray(depth, dtype=np.float32)
    return {
        "selected_model": "apple/DepthPro-hf",
        "depth": np.asarray(depth, dtype=np.float32),
        "confidence": None,
        "intrinsics": None,
        "extrinsics": None,
    }


def run_depth_anything_v2(image_path):
    import torch
    from transformers import pipeline

    pipe = pipeline(
        "depth-estimation",
        model="depth-anything/Depth-Anything-V2-Large-hf",
        device=0 if torch.cuda.is_available() else -1,
        dtype=torch.float16 if torch.cuda.is_available() else None,
    )
    result = pipe(Image.open(image_path).convert("RGB"))
    depth = result.get("predicted_depth", result.get("depth"))
    if hasattr(depth, "detach"):
        depth = depth.detach().cpu().float().numpy()
    elif isinstance(depth, Image.Image):
        depth = np.asarray(depth, dtype=np.float32)
    return {
        "selected_model": "depth-anything/Depth-Anything-V2-Large-hf",
        "depth": np.asarray(depth, dtype=np.float32),
        "confidence": None,
        "intrinsics": None,
        "extrinsics": None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--spatial", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    image_path = pathlib.Path(args.image)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    result = None

    for name, fn in [
        ("Depth Anything 3 / DA3METRIC-LARGE", lambda: run_da3(image_path, out.parent)),
        ("Apple Depth Pro", lambda: run_depth_pro(image_path)),
        ("Depth Anything V2 Large fallback", lambda: run_depth_anything_v2(image_path)),
    ]:
        try:
            started = time.time()
            result = fn()
            attempts.append({"model": name, "status": "ok", "seconds": round(time.time() - started, 3)})
            break
        except Exception as exc:
            attempts.append(
                {
                    "model": name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace_tail": traceback.format_exc().splitlines()[-6:],
                }
            )

    if result is None:
        raise SystemExit(json.dumps({"stage": "depth_plane_layout", "status": "failed", "attempts": attempts}, indent=2))

    depth_arr, npy_path, png_path = save_depth_outputs(result["depth"], out.parent)
    conf_path = None
    if result.get("confidence") is not None:
        conf_path = out.parent / "depth_confidence.npy"
        np.save(conf_path, result["confidence"])

    data = {
        "stage": "depth_plane_layout",
        "status": "ok",
        "target_models": MODELS,
        "selected_model": result["selected_model"],
        "attempts": attempts,
        "input_image": str(image_path),
        "spatial_input": args.spatial,
        "depth_npy": str(npy_path),
        "depth_visualization": str(png_path),
        "confidence_npy": str(conf_path) if conf_path else None,
        "intrinsics": result.get("intrinsics"),
        "extrinsics": result.get("extrinsics"),
        "layout": coarse_layout_from_depth(depth_arr),
        "ts_unix": int(time.time()),
    }
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
