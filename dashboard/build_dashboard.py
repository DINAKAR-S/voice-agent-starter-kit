#!/usr/bin/env python3
"""Build a single static call dashboard (dashboard.html) — stdlib only.

Reads one JSONL file per call from  transcripts/  and matches audio in
recordings/, then writes one HTML card per call: per-stage latency (colour
coded), auto-flag chips, an expandable transcript, and an inline <audio> player
when a recording exists.

    python build_dashboard.py                 # build from ./transcripts + ./recordings
    python build_dashboard.py --demo          # write one sample card from fake data
    python build_dashboard.py --self-check    # run the colour-coding assertions

Expected JSONL per call (one object per line, order preserved):
    {"type":"meta","call_id":"call-abc","did":"09000000000","language":"hi","started_at":"2026-07-22T10:11:12"}
    {"role":"user","text":"do you have 2 BHK flats?"}
    {"role":"assistant","text":"Yes! ...","latency_ms":{"eou":180,"stt":120,"llm":650,"tts":340}}
Anything missing is tolerated — the dashboard is a debugging aid, not a schema.
"""

import argparse
import html
import json
import os
import statistics
from pathlib import Path

# Per-stage latency budget in ms: (green_max, amber_max). Above amber_max = red.
STAGE_BUDGET = {
    "eou": (300, 500),
    "stt": (300, 500),
    "llm": (800, 1200),
    "tts": (500, 800),
}
STAGE_LABEL = {"eou": "EOU", "stt": "STT", "llm": "LLM", "tts": "TTS"}


def colour_for(stage: str, ms: float) -> str:
    """green if within budget, amber if stretched, red if over. Unknown stage → grey."""
    if stage not in STAGE_BUDGET:
        return "grey"
    green_max, amber_max = STAGE_BUDGET[stage]
    if ms <= green_max:
        return "green"
    if ms <= amber_max:
        return "amber"
    return "red"


def compute_flags(turns: list[dict]) -> list[str]:
    """Auto-flags from the assistant turns of one call."""
    flags = set()
    assistant_texts = []
    for t in turns:
        if t.get("role") != "assistant":
            continue
        lat = t.get("latency_ms", {})
        if lat.get("llm", 0) > 1000:
            flags.add("LLM-SLOW>1s")
        if lat.get("tts", 0) > 500:
            flags.add("TTS-SLOW>0.5s")
        text = (t.get("text") or "").strip()
        if not text:
            flags.add("EMPTY-REPLY")
        elif len(text) > 280:
            flags.add("VERBOSE")
        assistant_texts.append(text.lower())
    # RECOVERY-LOOP: the agent repeats itself (e.g. "sorry, I didn't catch that").
    if len(assistant_texts) - len(set(assistant_texts)) >= 2:
        flags.add("RECOVERY-LOOP")
    return sorted(flags)


def _avg(turns, stage):
    vals = [t["latency_ms"][stage] for t in turns
            if t.get("role") == "assistant" and stage in t.get("latency_ms", {})]
    return statistics.mean(vals) if vals else None


# ---- HTML rendering (plain string templates, no deps) -----------------------

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>voice-agent — call dashboard (Maya / Acme Realty)</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}}
 header{{padding:16px 24px;background:#161922;border-bottom:1px solid #262a35}}
 h1{{font-size:18px;margin:0}}
 .wrap{{max-width:920px;margin:0 auto;padding:24px}}
 .card{{background:#161922;border:1px solid #262a35;border-radius:10px;padding:16px;margin:0 0 18px}}
 .row{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
 .meta{{color:#9aa0ab;font-size:12px}}
 .stage{{padding:3px 9px;border-radius:6px;font-weight:600;font-size:12px;color:#0f1115}}
 .green{{background:#3ddc84}} .amber{{background:#ffcc4d}} .red{{background:#ff6b6b}} .grey{{background:#5a6069;color:#e6e6e6}}
 .chip{{padding:3px 9px;border-radius:12px;font-size:11px;font-weight:600;background:#3a2a2a;color:#ff9d9d;border:1px solid #5a3a3a}}
 details{{margin-top:12px}} summary{{cursor:pointer;color:#9aa0ab}}
 .turn{{padding:4px 0;border-top:1px solid #21252f}} .u{{color:#89c4ff}} .a{{color:#c8f7c5}}
 audio{{width:100%;margin-top:10px}}
</style></head><body>
<header><h1>Maya — call dashboard <span class="meta">· Acme Realty · {n} call(s)</span></h1></header>
<div class="wrap">{cards}</div></body></html>
"""

_CARD = """<div class="card">
 <div class="row"><strong>{call_id}</strong>
   <span class="meta">DID {did} · {lang} · {started}</span></div>
 <div class="row" style="margin-top:10px">{stages}</div>
 <div class="row" style="margin-top:10px">{chips}</div>
 {audio}
 <details><summary>Transcript ({nturns} turns)</summary>{transcript}</details>
</div>"""


def _stage_pills(turns) -> str:
    pills = []
    for stage in ("eou", "stt", "llm", "tts"):
        avg = _avg(turns, stage)
        if avg is None:
            continue
        pills.append(f'<span class="stage {colour_for(stage, avg)}">{STAGE_LABEL[stage]} {avg:.0f}ms</span>')
    return "".join(pills) or '<span class="meta">no latency data</span>'


def _transcript_html(turns) -> str:
    out = []
    for t in turns:
        role = t.get("role")
        if role not in ("user", "assistant"):
            continue
        cls = "u" if role == "user" else "a"
        who = "Caller" if role == "user" else "Maya"
        out.append(f'<div class="turn {cls}"><strong>{who}:</strong> {html.escape(t.get("text") or "")}</div>')
    return "".join(out)


def render_card(call: dict, recordings_dir: Path) -> str:
    turns = call["turns"]
    meta = call.get("meta", {})
    call_id = meta.get("call_id", call.get("call_id", "unknown"))
    rec = recordings_dir / f"{call_id}.mp3"
    audio = (f'<audio controls preload="none" src="recordings/{html.escape(rec.name)}"></audio>'
             if rec.exists() else "")
    chips = "".join(f'<span class="chip">{f}</span>' for f in compute_flags(turns)) \
        or '<span class="meta">no flags</span>'
    return _CARD.format(
        call_id=html.escape(str(call_id)),
        did=html.escape(str(meta.get("did", "?"))),
        lang=html.escape(str(meta.get("language", "?"))),
        started=html.escape(str(meta.get("started_at", ""))),
        stages=_stage_pills(turns),
        chips=chips,
        audio=audio,
        nturns=sum(1 for t in turns if t.get("role") in ("user", "assistant")),
        transcript=_transcript_html(turns),
    )


def load_call(path: Path) -> dict:
    meta, turns = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue  # skip malformed lines rather than crash the whole dashboard
        if obj.get("type") == "meta":
            meta = obj
        else:
            turns.append(obj)
    meta.setdefault("call_id", path.stem)
    return {"meta": meta, "turns": turns, "call_id": meta["call_id"]}


def build(transcripts_dir: Path, recordings_dir: Path, out: Path) -> None:
    calls = [load_call(p) for p in sorted(transcripts_dir.glob("*.jsonl"))]
    cards = "".join(render_card(c, recordings_dir) for c in calls) \
        or '<p class="meta">No transcripts found. Drop *.jsonl files in transcripts/.</p>'
    out.write_text(_PAGE.format(n=len(calls), cards=cards), encoding="utf-8")
    print(f"Wrote {out} ({len(calls)} call(s)).")


# ---- demo + self-check -------------------------------------------------------

_DEMO_CALL = {
    "meta": {"call_id": "call-demo", "did": "09000000000", "language": "hi",
             "started_at": "2026-07-22T10:11:12"},
    "turns": [
        {"role": "user", "text": "Namaste, do you have 2 BHK flats?"},
        {"role": "assistant", "text": "Namaste! Haan, humare paas 2 BHK flats hain in Whitefield, "
         "45 se 60 lakh ke beech. Aapka budget kya hai?",
         "latency_ms": {"eou": 190, "stt": 130, "llm": 1120, "tts": 610}},
        {"role": "user", "text": "Around 50 lakh. Can I visit on Saturday?"},
        {"role": "assistant", "text": "Bilkul! Saturday 11 baje site visit book kar diya. "
         "Aapka naam bata dijiye?", "latency_ms": {"eou": 210, "stt": 150, "llm": 680, "tts": 330}},
    ],
}


def _self_check() -> None:
    assert colour_for("llm", 500) == "green"
    assert colour_for("llm", 1000) == "amber"
    assert colour_for("llm", 1500) == "red"
    assert colour_for("tts", 400) == "green" and colour_for("tts", 900) == "red"
    assert colour_for("unknown", 10) == "grey"
    flags = compute_flags(_DEMO_CALL["turns"])
    assert "LLM-SLOW>1s" in flags and "TTS-SLOW>0.5s" in flags, flags
    print("self-check OK:", flags)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--transcripts", default="transcripts", help="dir of *.jsonl (default: transcripts)")
    p.add_argument("--recordings", default="recordings", help="dir of <call>.mp3 (default: recordings)")
    p.add_argument("--out", default="dashboard.html", help="output HTML file")
    p.add_argument("--demo", action="store_true", help="render one sample card from inline fake data")
    p.add_argument("--self-check", action="store_true", help="run colour/flag assertions and exit")
    args = p.parse_args()

    if args.self_check:
        _self_check()
        return
    if args.demo:
        out = Path(args.out)
        card = render_card(_DEMO_CALL, Path(args.recordings))
        out.write_text(_PAGE.format(n=1, cards=card), encoding="utf-8")
        print(f"Wrote {out} (demo). Open it in a browser.")
        return
    build(Path(args.transcripts), Path(args.recordings), Path(args.out))


if __name__ == "__main__":
    main()
