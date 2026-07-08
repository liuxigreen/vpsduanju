#!/usr/bin/env python3
"""Translate Chinese SRT to English with character/emotion analysis via DeepSeek API."""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = os.environ.get("DEEPSEEK_URL", "https://api.edgefn.net/v1/chat/completions")
MODEL = os.environ.get("DEEPSEEK_MODEL", "DeepSeek-V4-Flash")

SRT_PATH = Path.home() / "Desktop/youtube/末日倒计时_en/sub_zh.srt"
OUT_PATH = Path.home() / "Desktop/youtube/末日倒计时_en/analysis_en.json"


def call_deepseek(messages, max_tokens=4000, temperature=0.3):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    for attempt in range(5):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  API attempt {attempt+1} failed: {e}")
            if attempt < 4:
                time.sleep(2 ** attempt)
    return ""


def parse_srt(content):
    """Parse SRT into list of {idx, start, end, zh}."""
    blocks = re.split(r'\n\n+', content.strip())
    subs = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        idx_match = re.match(r'(\d+)', lines[0])
        if not idx_match:
            continue
        ts_match = re.match(r'([\d:,\.]+)\s*-->\s*([\d:,\.]+)', lines[1])
        if not ts_match:
            continue
        text = ' '.join(lines[2:]).strip()
        if text:
            subs.append({
                "idx": int(idx_match.group(1)),
                "start": ts_match.group(1),
                "end": ts_match.group(2),
                "zh": text,
            })
    return subs


def identify_characters(subs):
    """Send first 80 subtitle lines to identify characters."""
    sample_lines = [f"[{s['idx']}] {s['zh']}" for s in subs[:80]]
    sample_text = "\n".join(sample_lines)

    prompt = f"""Analyze these Chinese subtitle lines from a short drama. Identify all speaking characters.

For each character, provide:
- name: their name as used in subtitles
- gender: male/female
- voice: English voice description (e.g., "young woman, warm and gentle", "middle-aged man, authoritative")

Return ONLY valid JSON (no markdown):
{{
  "characters": {{
    "CharacterName": {{"gender": "male/female", "voice": "description"}},
    ...
  }}
}}

Subtitle lines:
{sample_text}"""

    result = call_deepseek([{"role": "user", "content": prompt}], max_tokens=1000)
    # Extract JSON
    m = re.search(r'\{.*\}', result, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            return data.get("characters", data)
        except json.JSONDecodeError:
            pass
    return {}


def translate_batch(batch, characters_info):
    """Translate a batch of subtitles with character/emotion tagging."""
    char_names = ", ".join(characters_info.keys()) if characters_info else "Unknown"

    lines_text = "\n".join(f"[{s['idx']}] {s['zh']}" for s in batch)

    prompt = f"""You are translating Chinese subtitles from a short drama to English.

Known characters: {char_names}
Emotions: angry, sad, happy, tender, scared, surprised, cold, anxious, normal

Translate each line. For each, identify the speaker (char) and emotion.

Return ONLY valid JSON array (no markdown):
[
  {{"idx": 1, "tr": "English translation", "char": "CharacterName or Unknown", "emotion": "normal"}},
  ...
]

Subtitles:
{lines_text}"""

    result = call_deepseek([{"role": "user", "content": prompt}], max_tokens=4000)

    # Extract JSON array
    m = re.search(r'\[.*\]', result, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []


def main():
    if not API_KEY:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)

    print(f"Reading SRT: {SRT_PATH}")
    content = SRT_PATH.read_text(encoding="utf-8", errors="ignore")
    subs = parse_srt(content)
    print(f"Parsed {len(subs)} subtitle segments")

    # Step 1: Identify characters
    print("\nStep 1: Identifying characters from first 80 lines...")
    characters = identify_characters(subs)
    print(f"Found {len(characters)} characters: {list(characters.keys())}")

    # Step 2: Batch translate
    print(f"\nStep 2: Translating {len(subs)} subtitles in batches of 30...")
    all_translations = []
    batch_size = 30

    for i in range(0, len(subs), batch_size):
        batch = subs[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(subs) + batch_size - 1) // batch_size
        print(f"  Batch {batch_num}/{total_batches} (lines {batch[0]['idx']}-{batch[-1]['idx']})...")

        translations = translate_batch(batch, characters)

        # Merge translations back
        tr_map = {t["idx"]: t for t in translations if "idx" in t}
        for s in batch:
            t = tr_map.get(s["idx"], {})
            s["tr"] = t.get("tr", "")
            s["char"] = t.get("char", "Unknown")
            s["emotion"] = t.get("emotion", "normal")
            all_translations.append(s)

        # Be nice to the API
        if i + batch_size < len(subs):
            time.sleep(1)

    # Step 3: Save
    output = {
        "characters": characters,
        "subtitles": all_translations,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(all_translations)} translated subtitles to {OUT_PATH}")
    print(f"Characters identified: {list(characters.keys())}")


if __name__ == "__main__":
    main()
