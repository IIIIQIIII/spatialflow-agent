#!/usr/bin/env python3
import argparse, json, pathlib, time

def read_json(path):
    p = pathlib.Path(path)
    if not p.exists():
        return {"missing": str(path)}
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--spatial", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    cfg = read_json(args.config)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "stage": "agent_planning",
        "status": "contract_ready",
        "planner_model": cfg.get("model", "openrouter openai/gpt-5.4"),
        "goal": cfg.get("goal"),
        "inputs": {
            "spatial": args.spatial,
            "layout": args.layout
        },
        "actions": [
            {"name": "preserve_fixed_structure", "constraints": ["floor", "windows", "doors", "wall boundaries"]},
            {"name": "define_style_target", "style": "Scandinavian / Nordic living room when requested"},
            {"name": "place_primary_furniture", "objects": ["sofa", "coffee_table", "rug"], "requires": "free_space + plane constraints"},
            {"name": "harmonize_lighting", "requires": "preserve natural light and window visibility"},
            {"name": "verify_and_repair", "requires": "Qwen3-VL + SigLIP 2 + geometry rules"}
        ],
        "next_impl": "Move this planner call into OpenRouter openai/gpt-5.4 with spatial/layout JSON as context and require strict action JSON.",
        "ts_unix": int(time.time())
    }
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
