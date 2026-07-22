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

# Four demo calls chosen to show the whole range: all-green, stretched-amber,
# over-budget-red with flags, and a healthy-but-verbose one.
_DEMO_CALLS = [
    {  # 1) healthy call — every stage green, no flags
        "meta": {"call_id": "call-1042", "did": "09000000000", "language": "hi",
                 "started_at": "2026-07-22T09:58:04"},
        "turns": [
            {"role": "user", "text": "Namaste, 2 BHK flat chahiye Whitefield mein."},
            {"role": "assistant", "text": "Namaste! Whitefield mein 2 BHK 45 se 60 lakh ke beech "
             "hain. Aapka budget kya hai?", "latency_ms": {"eou": 150, "stt": 95, "llm": 560, "tts": 330}},
            {"role": "user", "text": "50 lakh tak. Saturday visit ho sakta hai?"},
            {"role": "assistant", "text": "Bilkul, Saturday 11 baje site visit book kar diya. Naam?",
             "latency_ms": {"eou": 170, "stt": 110, "llm": 590, "tts": 340}},
        ],
    },
    {  # 2) stretched — amber LLM/TTS, still no hard flags
        "meta": {"call_id": "call-1043", "did": "09000000000", "language": "ta",
                 "started_at": "2026-07-22T10:22:41"},
        "turns": [
            {"role": "user", "text": "Vanakkam, 3 BHK plot iruka?"},
            {"role": "assistant", "text": "Vanakkam! 3 BHK flats iruku, plots-um iruku. Ungaloda "
             "budget evvalavu?", "latency_ms": {"eou": 260, "stt": 210, "llm": 980, "tts": 560}},
            {"role": "user", "text": "80 lakh. Chennai la enga iruku?"},
            {"role": "assistant", "text": "OMR-la 3 BHK 78 lakh-ku iruku. Site visit venuma?",
             "latency_ms": {"eou": 240, "stt": 190, "llm": 910, "tts": 520}},
        ],
    },
    {  # 3) over budget + flags: LLM-SLOW, TTS-SLOW, EMPTY-REPLY, RECOVERY-LOOP
        "meta": {"call_id": "call-1044", "did": "09000000000", "language": "en",
                 "started_at": "2026-07-22T11:03:19"},
        "turns": [
            {"role": "user", "text": "Hi, I'm looking for a villa."},
            {"role": "assistant", "text": "Sorry, I didn't catch that — could you repeat?",
             "latency_ms": {"eou": 320, "stt": 280, "llm": 1410, "tts": 720}},
            {"role": "user", "text": "A villa. Do you have any?"},
            {"role": "assistant", "text": "Sorry, I didn't catch that — could you repeat?",
             "latency_ms": {"eou": 300, "stt": 260, "llm": 1360, "tts": 690}},
            {"role": "user", "text": "V-I-L-L-A."},
            {"role": "assistant", "text": "Sorry, I didn't catch that — could you repeat?",
             "latency_ms": {"eou": 310, "stt": 270, "llm": 1290, "tts": 700}},
            {"role": "user", "text": "Villa!"},
            {"role": "assistant", "text": "", "latency_ms": {"eou": 290, "stt": 250, "llm": 1180, "tts": 0}},
        ],
    },
    {  # 4) healthy but VERBOSE (reply > 280 chars)
        "meta": {"call_id": "call-1045", "did": "09000000000", "language": "hi",
                 "started_at": "2026-07-22T11:40:55"},
        "turns": [
            {"role": "user", "text": "Amenities kya kya hain society mein?"},
            {"role": "assistant", "text": "Society mein swimming pool, gym, clubhouse, children's "
             "play area, 24x7 security, power backup, covered parking, indoor games, jogging track, "
             "aur ek chhota garden bhi hai. Iske alawa paas mein school aur hospital dono hain, metro "
             "station bhi sirf do kilometre door hai, toh family ke liye yeh location kaafi convenient "
             "hai aur daily commute bhi bahut aasan ho jaata hai.",
             "latency_ms": {"eou": 180, "stt": 120, "llm": 640, "tts": 480}},
        ],
    },
]
_DEMO_CALL = _DEMO_CALLS[2]  # the flagged one, used by the self-check


def _self_check() -> None:
    assert colour_for("llm", 500) == "green"
    assert colour_for("llm", 1000) == "amber"
    assert colour_for("llm", 1500) == "red"
    assert colour_for("tts", 400) == "green" and colour_for("tts", 900) == "red"
    assert colour_for("unknown", 10) == "grey"
    flags = compute_flags(_DEMO_CALL["turns"])
    for expected in ("LLM-SLOW>1s", "TTS-SLOW>0.5s", "EMPTY-REPLY", "RECOVERY-LOOP"):
        assert expected in flags, f"missing {expected} in {flags}"
    assert "VERBOSE" in compute_flags(_DEMO_CALLS[3]["turns"])
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
        cards = "".join(render_card(c, Path(args.recordings)) for c in _DEMO_CALLS)
        out.write_text(_PAGE.format(n=len(_DEMO_CALLS), cards=cards), encoding="utf-8")
        print(f"Wrote {out} (demo, {len(_DEMO_CALLS)} calls). Open it in a browser.")
        return
    build(Path(args.transcripts), Path(args.recordings), Path(args.out))


if __name__ == "__main__":
    main()
