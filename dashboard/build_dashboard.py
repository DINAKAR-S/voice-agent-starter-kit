#!/usr/bin/env python3
"""Build a single static call dashboard (dashboard.html) -- stdlib only.

Reads one JSONL file per call from  transcripts/  and matching audio in
recordings/ (<call_id>.mp3 or .wav), then renders:

  * a summary bar: total calls, minutes, cost, and average cost/min
  * one card per call: caller, time, cost + flags, and (expanded) an AI summary,
    a per-provider cost breakdown, an inline audio player + download, per-stage
    latency, and the full transcript.

    python build_dashboard.py                 # build from ./transcripts + ./recordings
    python build_dashboard.py --demo          # write a 3-call sample from fake data
    python build_dashboard.py --self-check    # run the colour/flag assertions

Expected JSONL per call (one object per line, order preserved):
    {"type":"meta","call_id":"maya-2201","phone":"+91 90000 00001","direction":"INBOUND",
     "language":"hi","started_at":"21 Jul 2026, 04:21 PM IST","duration_min":1.2,
     "summary":"Caller booked a site visit ...",
     "cost":{"total":3.12,"per_min":2.60,"vobiz":0.40,"sarvam":1.90,"gpt":0.30}}
    {"role":"user","text":"..."}
    {"role":"assistant","text":"...","latency_ms":{"eou":150,"stt":95,"llm":560,"tts":330}}
Anything missing is tolerated -- the dashboard is a debugging aid, not a schema.
"""

import argparse
import html
import json
import statistics
from pathlib import Path

# Per-stage latency budget in ms: (green_max, amber_max). Above amber_max = red.
STAGE_BUDGET = {"eou": (300, 500), "stt": (300, 500), "llm": (800, 1200), "tts": (500, 800)}
STAGE_LABEL = {"eou": "EOU", "stt": "STT", "llm": "LLM", "tts": "TTS"}

AGENT_NAME = "Maya"
CLIENT_NAME = "Acme Realty"


def colour_for(stage: str, ms: float) -> str:
    """green within budget, amber stretched, red over. Unknown stage -> grey."""
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
    if len(assistant_texts) - len(set(assistant_texts)) >= 2:
        flags.add("RECOVERY-LOOP")
    return sorted(flags)


def _avg(turns, stage):
    vals = [t["latency_ms"][stage] for t in turns
            if t.get("role") == "assistant" and stage in t.get("latency_ms", {})]
    return statistics.mean(vals) if vals else None


def _find_recording(recordings_dir: Path, call_id: str):
    for ext in (".mp3", ".wav"):
        p = recordings_dir / f"{call_id}{ext}"
        if p.exists():
            return p
    return None


# ---- HTML rendering (plain string templates, no deps) -----------------------

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{agent} - call dashboard ({client})</title>
<style>
 :root{{--bg:#0f1115;--card:#161922;--line:#262a35;--muted:#9aa0ab;--accent:#8b7bff}}
 *{{box-sizing:border-box}}
 body{{font:14px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:#e6e6e6}}
 .wrap{{max-width:1040px;margin:0 auto;padding:24px}}
 header{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:22px}}
 .brand{{display:flex;align-items:center;gap:12px}}
 .avatar{{width:44px;height:44px;border-radius:10px;background:var(--accent);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;color:#fff}}
 h1{{font-size:22px;margin:0;font-style:italic}}
 .sub{{color:var(--muted);font-size:13px;margin-top:2px}}
 .hmeta{{color:var(--muted);font-size:12px;text-align:right}}
 .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:26px}}
 .stat{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px}}
 .stat .k{{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase}}
 .stat .v{{font-size:30px;font-weight:800;margin-top:8px}}
 .stat .v.accent{{color:var(--accent)}}
 h2.section{{font-size:12px;letter-spacing:.1em;color:var(--muted);text-transform:uppercase;margin:0 0 12px}}
 details.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:0 0 14px;overflow:hidden}}
 summary{{list-style:none;cursor:pointer;padding:16px 18px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
 summary::-webkit-details-marker{{display:none}}
 .badge{{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.04em}}
 .in{{background:#20263a;color:#a9b7ff}}
 .phone{{font-size:16px;font-weight:700}}
 .who{{color:var(--accent);font-weight:600}} .when{{color:var(--muted)}}
 .spacer{{flex:1}}
 .tag{{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700}}
 .ok{{background:#123024;color:#5fe0a0}} .tr{{background:#191d33;color:#9aa9ff}}
 .cost{{background:#2a2410;color:#ffcc4d}} .flag{{background:#33201f;color:#ff9d9d}}
 .body{{padding:0 18px 18px;border-top:1px solid var(--line)}}
 .lbl{{font-size:12px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin:16px 0 8px;font-weight:700}}
 .panel{{background:#12151d;border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
 .costline{{background:#12151d;border:1px solid var(--line);border-radius:10px;padding:10px 14px;color:#cfd3db}}
 .costline b{{color:#ffcc4d}}
 .stage{{padding:3px 9px;border-radius:6px;font-weight:700;font-size:12px;color:#0f1115;margin-right:6px}}
 .green{{background:#3ddc84}} .amber{{background:#ffcc4d}} .red{{background:#ff6b6b}} .grey{{background:#5a6069;color:#e6e6e6}}
 audio{{width:100%;margin-top:6px}}
 .dl{{display:inline-block;margin-top:10px;padding:7px 14px;border-radius:8px;background:#20263a;color:#a9b7ff;text-decoration:none;font-weight:600;font-size:13px}}
 .turns{{border:1px solid var(--line);border-radius:10px;overflow:hidden}}
 .turn{{padding:8px 12px;border-top:1px solid var(--line)}} .turn:first-child{{border-top:none}}
 .turn .r{{font-weight:700;margin-right:6px}} .u .r{{color:#89c4ff}} .a .r{{color:#c8f7c5}}
 .copy{{float:right;padding:5px 12px;border-radius:8px;background:#20263a;color:#a9b7ff;border:none;cursor:pointer;font-weight:600;font-size:12px}}
</style></head><body>
<div class="wrap">
 <header>
  <div class="brand"><div class="avatar">{initial}</div>
   <div><h1>{agent}</h1><div class="sub">AI Voice Agent &middot; {agent} &middot; {client}</div></div></div>
  <div class="hmeta">{n} calls &middot; cost-attributed<br>{updated}</div>
 </header>
 <div class="stats">
  <div class="stat"><div class="k">Calls</div><div class="v">{calls}</div></div>
  <div class="stat"><div class="k">Total minutes</div><div class="v">{minutes}</div></div>
  <div class="stat"><div class="k">Total cost</div><div class="v accent">&#8377;{total_cost}</div></div>
  <div class="stat"><div class="k">Avg / min</div><div class="v accent">&#8377;{avg_min}</div></div>
 </div>
 <h2 class="section">Call history</h2>
 {cards}
</div>
<script>
function copyTranscript(btn){{
  var t = btn.parentElement.querySelector('.turns').innerText;
  navigator.clipboard.writeText(t).then(function(){{btn.textContent='Copied';setTimeout(function(){{btn.textContent='Copy';}},1200);}});
}}
</script>
</body></html>
"""


def _stage_pills(turns) -> str:
    pills = []
    for stage in ("eou", "stt", "llm", "tts"):
        avg = _avg(turns, stage)
        if avg is None:
            continue
        pills.append(f'<span class="stage {colour_for(stage, avg)}">{STAGE_LABEL[stage]} {avg:.0f}ms</span>')
    return "".join(pills) or '<span class="when">no latency data</span>'


def _transcript_html(turns) -> str:
    out = []
    for t in turns:
        role = t.get("role")
        if role not in ("user", "assistant"):
            continue
        cls = "u" if role == "user" else "a"
        who = "Caller" if role == "user" else AGENT_NAME
        out.append(f'<div class="turn {cls}"><span class="r">{who}:</span>{html.escape(t.get("text") or "")}</div>')
    return "".join(out) or '<div class="turn">no transcript</div>'


def render_card(call: dict, recordings_dir: Path) -> str:
    turns = call["turns"]
    meta = call.get("meta", {})
    call_id = meta.get("call_id", call.get("call_id", "unknown"))
    flags = compute_flags(turns)
    cost = meta.get("cost", {})
    total = cost.get("total")

    tags = ['<span class="tag ok">ANALYZED</span>', '<span class="tag tr">TRANSCRIPT</span>']
    if total is not None:
        tags.append(f'<span class="tag cost">&#8377;{total:.2f}</span>')
    if flags:
        tags.append(f'<span class="tag flag">{len(flags)} FLAG{"S" if len(flags) > 1 else ""}</span>')

    rec = _find_recording(recordings_dir, str(call_id))
    if rec is not None:
        audio = (f'<div class="lbl">&#128266; Recording</div>'
                 f'<audio controls preload="none" src="recordings/{html.escape(rec.name)}"></audio><br>'
                 f'<a class="dl" href="recordings/{html.escape(rec.name)}" download>&#11015; Download</a>')
    else:
        audio = ""

    summary_txt = meta.get("summary")
    ai = (f'<div class="lbl">&#129504; AI analysis</div><div class="panel">{html.escape(summary_txt)}</div>'
          if summary_txt else "")

    if cost:
        split = (f'Vobiz &#8377;{cost.get("vobiz",0):.2f} &middot; Sarvam &#8377;{cost.get("sarvam",0):.2f} '
                 f'&middot; GPT &#8377;{cost.get("gpt",0):.2f}')
        costline = (f'<div class="lbl">&#128176; Cost</div><div class="costline">'
                    f'<b>&#8377;{cost.get("total",0):.2f}</b> &middot; &#8377;{cost.get("per_min",0):.2f}/min '
                    f'({split})</div>')
    else:
        costline = ""

    flag_tags = "".join(f'<span class="tag flag">{f}</span>' for f in flags)
    nturns = sum(1 for t in turns if t.get("role") in ("user", "assistant"))

    return f"""<details class="card">
 <summary>
  <span class="badge in">{html.escape(str(meta.get("direction","INBOUND")))}</span>
  <span class="phone">{html.escape(str(meta.get("phone", meta.get("did","?"))))}</span>
  <span class="who">{AGENT_NAME} &middot; {CLIENT_NAME}</span>
  <span class="when">&middot; {html.escape(str(meta.get("started_at","")))} &middot; {html.escape(str(meta.get("language","")))}</span>
  <span class="spacer"></span>{"".join(tags)}
 </summary>
 <div class="body">
  {ai}
  {costline}
  {audio}
  <div class="lbl">&#9201; Latency (avg / stage)</div>{_stage_pills(turns)} {flag_tags}
  <div class="lbl">&#128172; Transcript &middot; {nturns} turns
   <button class="copy" onclick="copyTranscript(this)">Copy</button></div>
  <div class="turns">{_transcript_html(turns)}</div>
 </div>
</details>"""


def _fmt(n, d=2):
    return f"{n:.{d}f}"


def _render_page(calls, recordings_dir, updated="updated just now"):
    minutes = sum(c.get("meta", {}).get("duration_min", 0) for c in calls)
    total_cost = sum(c.get("meta", {}).get("cost", {}).get("total", 0) for c in calls)
    avg_min = (total_cost / minutes) if minutes else 0
    cards = "".join(render_card(c, recordings_dir) for c in calls) \
        or '<p class="when">No transcripts found. Drop *.jsonl files in transcripts/.</p>'
    return _PAGE.format(
        agent=AGENT_NAME, client=CLIENT_NAME, initial=AGENT_NAME[0], n=len(calls),
        calls=len(calls), minutes=_fmt(minutes, 1), total_cost=_fmt(total_cost),
        avg_min=_fmt(avg_min), updated=updated, cards=cards,
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
    out.write_text(_render_page(calls, recordings_dir), encoding="utf-8")
    print(f"Wrote {out} ({len(calls)} call(s)).")


# ---- demo + self-check -------------------------------------------------------

_DEMO_CALLS = [
    {  # healthy, all green, no flags
        "meta": {"call_id": "maya-2201", "phone": "+91 90000 00001", "direction": "INBOUND",
                 "language": "hi", "started_at": "21 Jul 2026, 04:21 PM IST", "duration_min": 1.2,
                 "summary": "Caller asked about 2 BHK flats in Whitefield under Rs 50L and booked a "
                            "Saturday 11 AM site visit. Name and phone captured.",
                 "cost": {"total": 3.12, "per_min": 2.60, "vobiz": 0.40, "sarvam": 1.90, "gpt": 0.30}},
        "turns": [
            {"role": "user", "text": "Namaste, 2 BHK flat chahiye Whitefield mein."},
            {"role": "assistant", "text": "Namaste! Whitefield mein 2 BHK 45 se 60 lakh ke beech "
             "hain. Aapka budget kya hai?", "latency_ms": {"eou": 150, "stt": 95, "llm": 560, "tts": 330}},
            {"role": "user", "text": "50 lakh tak. Saturday visit ho sakta hai?"},
            {"role": "assistant", "text": "Bilkul, Saturday 11 baje site visit book kar diya. Naam bata dijiye?",
             "latency_ms": {"eou": 170, "stt": 110, "llm": 590, "tts": 340}},
        ],
    },
    {  # stretched -> TTS-SLOW flag
        "meta": {"call_id": "maya-2202", "phone": "+91 90000 00002", "direction": "INBOUND",
                 "language": "ta", "started_at": "20 Jul 2026, 10:01 AM IST", "duration_min": 2.1,
                 "summary": "Caller enquired about 3 BHK on OMR, Chennai around Rs 80L; quoted Rs 78L "
                            "and offered a site visit. Slight TTS lag noted.",
                 "cost": {"total": 6.72, "per_min": 3.20, "vobiz": 0.40, "sarvam": 2.40, "gpt": 0.40}},
        "turns": [
            {"role": "user", "text": "Vanakkam, 3 BHK OMR la iruka?"},
            {"role": "assistant", "text": "Vanakkam! OMR-la 3 BHK iruku, 78 lakh. Site visit venuma?",
             "latency_ms": {"eou": 260, "stt": 210, "llm": 940, "tts": 560}},
            {"role": "user", "text": "Aama, Sunday morning."},
            {"role": "assistant", "text": "Sunday kaalai 10 maniku book pannirken. Peyar sollunga?",
             "latency_ms": {"eou": 240, "stt": 190, "llm": 910, "tts": 520}},
        ],
    },
    {  # over budget + flags: LLM-SLOW, TTS-SLOW, EMPTY-REPLY, RECOVERY-LOOP
        "meta": {"call_id": "maya-2203", "phone": "+91 90000 00003", "direction": "INBOUND",
                 "language": "en", "started_at": "20 Jul 2026, 06:35 PM IST", "duration_min": 2.8,
                 "summary": "Caller wanted a villa but STT repeatedly misheard; the agent looped on "
                            "'sorry, I didn't catch that' and then went silent. Needs a human follow-up.",
                 "cost": {"total": 9.24, "per_min": 3.30, "vobiz": 0.40, "sarvam": 2.50, "gpt": 0.40}},
        "turns": [
            {"role": "user", "text": "Hi, I'm looking for a villa."},
            {"role": "assistant", "text": "Sorry, I didn't catch that - could you repeat?",
             "latency_ms": {"eou": 320, "stt": 280, "llm": 1410, "tts": 720}},
            {"role": "user", "text": "A villa. Do you have any?"},
            {"role": "assistant", "text": "Sorry, I didn't catch that - could you repeat?",
             "latency_ms": {"eou": 310, "stt": 270, "llm": 1290, "tts": 700}},
            {"role": "user", "text": "V-I-L-L-A."},
            {"role": "assistant", "text": "Sorry, I didn't catch that - could you repeat?",
             "latency_ms": {"eou": 305, "stt": 265, "llm": 1240, "tts": 695}},
            {"role": "user", "text": "Villa!"},
            {"role": "assistant", "text": "", "latency_ms": {"eou": 290, "stt": 250, "llm": 1180, "tts": 0}},
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
    # stat maths
    minutes = sum(c["meta"]["duration_min"] for c in _DEMO_CALLS)
    total = sum(c["meta"]["cost"]["total"] for c in _DEMO_CALLS)
    assert round(minutes, 1) == 6.1 and round(total / minutes, 2) <= 4.0, (minutes, total)
    print(f"self-check OK: flags={flags} minutes={minutes:.1f} avg/min={total/minutes:.2f}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--transcripts", default="transcripts", help="dir of *.jsonl (default: transcripts)")
    p.add_argument("--recordings", default="recordings", help="dir of <call>.mp3/.wav (default: recordings)")
    p.add_argument("--out", default="dashboard.html", help="output HTML file")
    p.add_argument("--demo", action="store_true", help="render a 3-call sample from inline fake data")
    p.add_argument("--self-check", action="store_true", help="run colour/flag assertions and exit")
    args = p.parse_args()

    if args.self_check:
        _self_check()
        return
    if args.demo:
        out = Path(args.out)
        out.write_text(_render_page(_DEMO_CALLS, Path(args.recordings),
                                    updated="updated 22 Jul 2026, 11:51 AM IST"), encoding="utf-8")
        print(f"Wrote {out} (demo, {len(_DEMO_CALLS)} calls). Open it in a browser.")
        return
    build(Path(args.transcripts), Path(args.recordings), Path(args.out))


if __name__ == "__main__":
    main()
