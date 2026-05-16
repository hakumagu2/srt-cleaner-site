from flask import Flask, render_template, request, send_file
import io
import re
from datetime import datetime

app = Flask(__name__)

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
MAX_CHARS_PER_LINE = 22
MIN_DURATION_SEC = 0.10
MIN_GAP_SEC = 0.001


COMMON_REPLACE = {
    "youtube": "YouTube",
    "ユーチューブ": "YouTube",
    "ＹｏｕＴｕｂｅ": "YouTube",
    "tiktok": "TikTok",
    "ティックトック": "TikTok",
    "インスタグラム": "Instagram",
    "ツイッター": "X",
    "受 講生": "受講生",
    "聞えますか": "聞こえますか",
    "聞えます か": "聞こえますか",
    "聞こえます か": "聞こえますか",
    "です ね": "ですね",
    "そうです ね": "そうですね",
    "なんです ね": "なんですね",
    "なるほどです ね": "なるほどですね",
}

VIDEO_REPLACE = {
    "プレミアプロ": "Premiere Pro",
    "プレミア プロ": "Premiere Pro",
    "アドビ": "Adobe",
    "フォトショップ": "Photoshop",
    "アフターエフェクト": "After Effects",
    "アフターエフェクツ": "After Effects",
    "ダビンチリゾルブ": "DaVinci Resolve",
    "ファイナルカット": "Final Cut Pro",
    "サムネ": "サムネイル",
}

BUSINESS_REPLACE = {
    "博業": "副業",
    "注入": "収入",
    "日頭": "日当",
    "テレアっぽ": "テレアポ",
    "テレアップ": "テレアポ",
    "残量": "残業",
    "体育会計": "体育会系",
    "報連争": "報連相",
    "法連争": "報連相",
}

JOB_REPLACE = {
    "昼食活動": "就職活動",
    "プレジェント": "エージェント",
    "エイジェント": "エージェント",
    "起業理解": "企業理解",
}

PRESETS = {
    "common": COMMON_REPLACE,
    "video": {**COMMON_REPLACE, **VIDEO_REPLACE},
    "business": {**COMMON_REPLACE, **BUSINESS_REPLACE},
    "job": {**COMMON_REPLACE, **JOB_REPLACE},
    "all": {**COMMON_REPLACE, **VIDEO_REPLACE, **BUSINESS_REPLACE, **JOB_REPLACE},
    "none": {},
}

DROP_IF_ALONE = {
    "えー", "あー", "うーん", "えっと", "えっとね",
    "はいはい", "はい", "うん", "まあ", "まぁ",
}

FILLERS_AT_START = [
    "えー", "あー", "えっと", "えっとね", "うーん",
    "そのー", "あのー", "まあ", "まぁ",
]

KANJI_DIGIT = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}

KANJI_SMALL_UNIT = {
    "十": 10,
    "百": 100,
    "千": 1000,
}

KANJI_BIG_UNIT = {
    "万": 10000,
}

QUESTION_END_PATTERNS = [
    r"ですか$",
    r"ますか$",
    r"ましたか$",
    r"ませんか$",
    r"でしょうか$",
    r"なんですか$",
    r"なんでしょうか$",
    r"いいですか$",
    r"大丈夫ですか$",
    r"よろしいですか$",
    r"聞こえますか$",
    r"見えますか$",
    r"分かりますか$",
    r"わかりますか$",
    r"どうですか$",
    r"どう思いますか$",
    r"どう感じますか$",
    r"どうしますか$",
    r"どうしたんですか$",
    r"どうなりましたか$",
    r"どこですか$",
    r"誰ですか$",
    r"いつですか$",
    r"なんでですか$",
    r"なぜですか$",
    r"どれですか$",
    r"どっちですか$",
    r"いくらですか$",
    r"どう$",
    r"どこ$",
    r"誰$",
    r"いつ$",
    r"なんで$",
    r"なぜ$",
    r"どれ$",
    r"どっち$",
    r"いくら$",
    r"本当$",
    r"ほんと$",
    r"マジ$",
    r"まじ$",
]


def normalize_spaces(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\ufeff", "")
    s = s.replace("\u3000", " ")
    s = s.replace("\xa0", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def cleanup_noise(s: str) -> str:
    if not s:
        return ""

    s = s.replace("【", "").replace("】", "")
    s = s.replace("///", "")
    s = s.replace("ｑ", "q")

    s = re.sub(r"(?<![A-Za-z])q(?![A-Za-z])", "?", s)
    s = re.sub(r"\?{2,}", "?", s)
    s = re.sub(r"？{2,}", "？", s)
    s = re.sub(r"[!！]{2,}", "！", s)
    s = re.sub(r"[。]{2,}", "。", s)
    s = re.sub(r"[、]{2,}", "、", s)

    s = re.sub(r"(?mi)^\s*de\s*$", "", s)
    s = re.sub(r"(?m)^\s*で、?\s*$", "", s)
    s = re.sub(r"(?m)^\?+\s*$", "", s)
    s = re.sub(r"(?m)^？+\s*$", "", s)
    s = re.sub(r"(?m)^[ぁ-んァ-ンー]?\s*$", "", s)

    s = re.sub(r"\s+([、。！？?])", r"\1", s)
    s = re.sub(r"\s*,\s*", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def remove_punctuation(s: str) -> str:
    return s.replace("、", "").replace("。", "")


def remove_fillers(text: str) -> str:
    lines = text.split("\n")
    out = []

    for line in lines:
        line = line.strip()
        changed = True

        while changed:
            changed = False
            for f in FILLERS_AT_START:
                pattern = rf"^{re.escape(f)}[、。,\s]*"
                new_line = re.sub(pattern, "", line)
                if new_line != line:
                    line = new_line.strip()
                    changed = True

        out.append(line)

    return "\n".join(out).strip()


def apply_replace(s: str, replace_dict: dict) -> str:
    for a, b in sorted(replace_dict.items(), key=lambda x: len(x[0]), reverse=True):
        s = s.replace(a, b)
    return s


def kanji_number_to_int(token: str):
    if not token:
        return None

    total = 0
    section = 0
    number = 0
    used = False

    for ch in token:
        if ch in KANJI_DIGIT:
            number = KANJI_DIGIT[ch]
            used = True
        elif ch in KANJI_SMALL_UNIT:
            unit = KANJI_SMALL_UNIT[ch]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
            used = True
        elif ch in KANJI_BIG_UNIT:
            unit = KANJI_BIG_UNIT[ch]
            if number == 0 and section == 0:
                section = 1
            section += number
            total += section * unit
            section = 0
            number = 0
            used = True
        else:
            return None

    section += number
    total += section
    return total if used else None


def convert_kanji_numbers(text: str) -> str:
    units_after = "円人個本枚回社件年ヶ月日時間分秒代歳番台"
    pattern = r"[零〇一二三四五六七八九十百千万]+"

    def repl(m):
        token = m.group(0)
        end = m.span()[1]
        next_char = text[end:end + 1]

        contains_unit = any(u in token for u in "十百千万")
        followed_by_unit = next_char in units_after

        if len(token) == 1 and not followed_by_unit:
            return token

        if not contains_unit and not followed_by_unit:
            return token

        num = kanji_number_to_int(token)
        return str(num) if num is not None else token

    return re.sub(pattern, repl, text)


def is_question_sentence(text: str) -> bool:
    t = normalize_spaces(text)
    t = t.replace("。", "").replace("、", "").strip()

    if not t:
        return False

    if t.endswith(("?", "？")):
        return True

    if re.search(r"(してください|下さい|ください|お願いします|してくださいね)$", t):
        return False

    if re.search(r"(というか|なんか|だから|ていうか)$", t):
        return False

    for pattern in QUESTION_END_PATTERNS:
        if re.search(pattern, t):
            return True

    return False


def add_question_mark_if_needed(text: str, enabled: bool) -> str:
    t = text.strip()

    if not t:
        return t

    if not enabled:
        return t

    if t.endswith(("?", "？")):
        return t

    if is_question_sentence(t):
        return t + "？"

    return t


# =========================================================
# SRT読み取り
# =========================================================

def parse_srt_blocks(srt_text: str):
    srt_text = srt_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    raw_blocks = re.split(r"\n\s*\n", srt_text, flags=re.MULTILINE)
    out = []

    for block in raw_blocks:
        lines = [x.rstrip() for x in block.splitlines()]
        lines = [x for x in lines if x.strip() != ""]

        if len(lines) < 2:
            continue

        if re.fullmatch(r"\d+", lines[0].strip()) and len(lines) >= 3:
            idx = lines[0].strip()
            timecode = lines[1].strip()
            body_lines = lines[2:]
        elif "-->" in lines[0]:
            idx = ""
            timecode = lines[0].strip()
            body_lines = lines[1:]
        else:
            continue

        if "-->" not in timecode:
            continue

        body = "\n".join(body_lines).strip()
        if body:
            out.append((idx, timecode, body))

    return out


# =========================================================
# タイムコード付きTXT読み取り
# 例：
# 00:00:01:15 - 00:00:02:19
#
# こんばんは
# =========================================================

TXT_TC_PATTERN = re.compile(
    r"^\s*(\d{2}:\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2}:\d{2})\s*$"
)


def frame_tc_to_srt_tc(tc: str, fps: float) -> str:
    """
    00:00:01:15 を 00:00:01,250 のようなSRT形式へ変換。
    fps=60 の場合、15フレーム = 250ms。
    """
    h, m, s, f = tc.split(":")
    h = int(h)
    m = int(m)
    s = int(s)
    f = int(f)

    total_sec = h * 3600 + m * 60 + s + (f / fps)
    return sec_to_tc(total_sec)


def parse_timed_txt_blocks(txt_text: str, fps: float = 60.0):
    """
    タイムコード付きTXTをSRTブロックに変換して返す。
    """
    txt_text = txt_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = txt_text.split("\n")

    out = []
    current_start = None
    current_end = None
    current_body = []

    def flush():
        nonlocal current_start, current_end, current_body

        if current_start and current_end:
            body = "\n".join(current_body).strip()
            if body:
                start_tc = frame_tc_to_srt_tc(current_start, fps)
                end_tc = frame_tc_to_srt_tc(current_end, fps)
                out.append(("", f"{start_tc} --> {end_tc}", body))

        current_start = None
        current_end = None
        current_body = []

    for line in lines:
        m = TXT_TC_PATTERN.match(line)

        if m:
            flush()
            current_start = m.group(1)
            current_end = m.group(2)
            current_body = []
        else:
            if current_start and current_end:
                # 空行は無視。本文が複数行ある場合は保持。
                if line.strip() != "":
                    current_body.append(line.strip())

    flush()
    return out


def build_srt(blocks):
    parts = []
    for i, (_idx, timecode, body) in enumerate(blocks, start=1):
        parts.append(f"{i}\n{timecode}\n{body}")
    return "\n\n".join(parts) + "\n"


def tc_to_sec(tc: str) -> float:
    h, m, rest = tc.strip().split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def sec_to_tc(sec: float) -> str:
    if sec < 0:
        sec = 0.0

    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))

    if ms == 1000:
        s += 1
        ms = 0
    if s == 60:
        m += 1
        s = 0
    if m == 60:
        h += 1
        m = 0

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def split_timecode(timecode: str):
    start_tc, end_tc = [x.strip() for x in timecode.split("-->")]
    return tc_to_sec(start_tc), tc_to_sec(end_tc)


def make_timecode(start: float, end: float):
    return f"{sec_to_tc(start)} --> {sec_to_tc(end)}"


def stabilize_timing_safely(blocks, offset_ms=0, fix_overlap=True):
    offset = offset_ms / 1000.0
    timed = []

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            continue

        start += offset
        end += offset

        if start < 0:
            diff = -start
            start += diff
            end += diff

        if end <= start:
            end = start + MIN_DURATION_SEC

        timed.append([idx, start, end, body])

    if fix_overlap:
        for i in range(1, len(timed)):
            prev = timed[i - 1]
            cur = timed[i]

            if cur[1] < prev[2]:
                cur[1] = prev[2] + MIN_GAP_SEC

            if cur[2] <= cur[1]:
                cur[2] = cur[1] + MIN_DURATION_SEC

    out = []
    for idx, start, end, body in timed:
        out.append((idx, make_timecode(start, end), body))

    return out


def normalize_for_dedupe(text: str) -> str:
    t = text
    t = t.replace("\n", "")
    t = t.replace(" ", "")
    t = t.replace("　", "")
    t = t.replace("、", "")
    t = t.replace("。", "")
    t = t.replace("？", "")
    t = t.replace("?", "")
    t = t.replace("！", "")
    t = t.replace("!", "")
    return t.strip()


def remove_consecutive_duplicates(blocks, gap_ms=1200):
    if not blocks:
        return []

    out = []
    prev_text = None
    prev_end = None

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            continue

        cur_text = normalize_for_dedupe(body)
        is_duplicate = False

        if prev_text and cur_text and cur_text == prev_text:
            gap = start - prev_end if prev_end is not None else 9999
            if gap <= gap_ms / 1000.0:
                is_duplicate = True

        if not is_duplicate:
            out.append((idx, timecode, body))
            prev_text = cur_text
            prev_end = end

    return out


def should_drop_if_alone(text: str) -> bool:
    t = normalize_spaces(text)
    t = t.replace("、", "").replace("。", "")
    t = t.replace("？", "").replace("?", "")
    t = t.replace("！", "").replace("!", "")
    t = t.replace("…", "").strip()

    if not t:
        return True

    if t in DROP_IF_ALONE:
        return True

    if re.fullmatch(r"[?？!！…・ー]+", t):
        return True

    return False


def split_sentences(text: str):
    text = text.strip()
    if not text:
        return []

    parts = re.split(r"(?<=[。！？?])\s*", text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) == 1:
        t = parts[0]
        t = re.sub(
            r"(なんですか|でしょうか|ですか|ましたか|ませんか|でした|です|ます|だった|だね|ですね)(\s*)",
            r"\1\n",
            t
        )
        parts2 = [p.strip() for p in t.split("\n") if p.strip()]
        if parts2:
            parts = parts2

    return parts


def split_long_line(text: str, max_len=22):
    text = text.strip()

    if len(text) <= max_len:
        return [text]

    candidates = ["、", " ", "は", "が", "を", "に", "で", "と", "も", "って", "けど", "ので", "から"]
    best = None
    center = len(text) // 2

    for token in candidates:
        for m in re.finditer(re.escape(token), text):
            pos = m.end()
            score = abs(pos - center)
            if best is None or score < best[0]:
                best = (score, pos)

    if best:
        pos = best[1]
        left = text[:pos].strip()
        right = text[pos:].strip()
        if left and right:
            return [left, right]

    return [text[:max_len].strip(), text[max_len:].strip()]


def format_lines(sentences, allow_3=True, max_len=22):
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return ""

    units = []

    for s in sentences:
        if len(s) > max_len * 1.6:
            units.extend(split_long_line(s, max_len=max_len))
        else:
            units.append(s)

    if len(units) <= 2:
        return "\n".join(units)

    if allow_3 and len(units) <= 3:
        return "\n".join(units)

    total = sum(len(x) for x in units)
    target_lines = 3 if allow_3 and total > max_len * 2 else 2
    target = total / target_lines

    lines = []
    cur = ""

    for u in units:
        if not cur:
            cur = u
            continue

        if len(cur) + 1 + len(u) <= target + 6:
            cur += " " + u
        else:
            lines.append(cur)
            cur = u

    if cur:
        lines.append(cur)

    if len(lines) > target_lines:
        merged = []
        for line in lines:
            if len(merged) < target_lines:
                merged.append(line)
            else:
                merged[-1] += " " + line
        lines = merged

    return "\n".join(lines)


def fix_block_text(
    body,
    replace_dict,
    allow_3=True,
    max_chars=22,
    remove_punct=True,
    add_question=False,
):
    text = normalize_spaces(body)
    text = cleanup_noise(text)
    text = convert_kanji_numbers(text)
    text = apply_replace(text, replace_dict)
    text = remove_fillers(text)
    text = cleanup_noise(text)
    text = normalize_spaces(text)

    sentences = split_sentences(text)
    fixed_sentences = []

    for s in sentences:
        s = normalize_spaces(s)
        if not s:
            continue

        s = add_question_mark_if_needed(s, enabled=add_question)
        fixed_sentences.append(s)

    text = "\n".join(fixed_sentences)
    text = normalize_spaces(text)

    if remove_punct:
        text = remove_punctuation(text)
        text = normalize_spaces(text)

    if should_drop_if_alone(text):
        return ""

    lines = []
    for line in text.split("\n"):
        line = normalize_spaces(line)
        if line:
            lines.append(line)

    result = format_lines(lines, allow_3=allow_3, max_len=max_chars)
    result = re.sub(r"[ ]{2,}", " ", result).strip()

    if should_drop_if_alone(result):
        return ""

    return result


def convert_blocks_to_srt_text(
    blocks,
    allow_3=True,
    max_chars=22,
    preset="common",
    remove_punct=True,
    add_question=False,
    offset_ms=0,
    fix_overlap=True,
    dedupe=True,
):
    replace_dict = PRESETS.get(preset, COMMON_REPLACE)
    fixed_blocks = []

    for idx, timecode, body in blocks:
        fixed = fix_block_text(
            body=body,
            replace_dict=replace_dict,
            allow_3=allow_3,
            max_chars=max_chars,
            remove_punct=remove_punct,
            add_question=add_question,
        )

        if fixed:
            fixed_blocks.append((idx, timecode, fixed))

    fixed_blocks = stabilize_timing_safely(
        fixed_blocks,
        offset_ms=offset_ms,
        fix_overlap=fix_overlap,
    )

    if dedupe:
        fixed_blocks = remove_consecutive_duplicates(fixed_blocks, gap_ms=1200)

    return build_srt(fixed_blocks)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    if "srt_file" not in request.files:
        return "ファイルがありません", 400

    file = request.files["srt_file"]

    if file.filename == "":
        return "ファイルが選択されていません", 400

    filename_lower = file.filename.lower()

    if not (filename_lower.endswith(".srt") or filename_lower.endswith(".txt")):
        return "SRT または タイムコード付きTXT のみ対応しています", 400

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        return "ファイルサイズが大きすぎます。2MB以内のファイルを使ってください。", 400

    try:
        raw_text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw_text = data.decode("cp932", errors="replace")

    try:
        preset = request.form.get("preset", "common")
        max_chars = int(request.form.get("max_chars", "22"))
        offset_ms = int(request.form.get("offset_ms", "0"))
        txt_fps = float(request.form.get("txt_fps", "60"))

        allow_3 = request.form.get("allow_3") == "on"
        remove_punct = request.form.get("remove_punct") == "on"
        add_question = request.form.get("add_question") == "on"
        fix_overlap = request.form.get("fix_overlap") == "on"
        dedupe = request.form.get("dedupe") == "on"

        if filename_lower.endswith(".srt"):
            blocks = parse_srt_blocks(raw_text)
            source_type = "srt"
        else:
            blocks = parse_timed_txt_blocks(raw_text, fps=txt_fps)
            source_type = f"timed_txt_{txt_fps}fps"

        if not blocks:
            return "変換できる字幕がありませんでした。SRTまたはタイムコード付きTXTの形式を確認してください。", 400

        result_text = convert_blocks_to_srt_text(
            blocks=blocks,
            allow_3=allow_3,
            max_chars=max_chars,
            preset=preset,
            remove_punct=remove_punct,
            add_question=add_question,
            offset_ms=offset_ms,
            fix_overlap=fix_overlap,
            dedupe=dedupe,
        )

        if not result_text.strip():
            return "変換できる字幕がありませんでした。ファイルの形式を確認してください。", 400

        output = io.BytesIO(result_text.encode("utf-8"))
        output.seek(0)

        original_name = file.filename.rsplit(".", 1)[0]
        download_name = f"{original_name}.final.srt"

        print(
            f"[{datetime.now()}] converted: "
            f"name={file.filename}, size={len(data)}, type={source_type}, "
            f"preset={preset}, question={add_question}, punct={remove_punct}"
        )

        return send_file(
            output,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/x-subrip",
        )

    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        return "変換中にエラーが発生しました。ファイルの形式を確認してください。", 500


if __name__ == "__main__":
    app.run(debug=True)    "アフターエフェクト": "After Effects",
    "アフターエフェクツ": "After Effects",
    "ダビンチリゾルブ": "DaVinci Resolve",
    "ファイナルカット": "Final Cut Pro",
    "サムネ": "サムネイル",
}

BUSINESS_REPLACE = {
    "博業": "副業",
    "注入": "収入",
    "日頭": "日当",
    "テレアっぽ": "テレアポ",
    "テレアップ": "テレアポ",
    "残量": "残業",
    "体育会計": "体育会系",
    "報連争": "報連相",
    "法連争": "報連相",
}

JOB_REPLACE = {
    "昼食活動": "就職活動",
    "プレジェント": "エージェント",
    "エイジェント": "エージェント",
    "起業理解": "企業理解",
}

PRESETS = {
    "common": COMMON_REPLACE,
    "video": {**COMMON_REPLACE, **VIDEO_REPLACE},
    "business": {**COMMON_REPLACE, **BUSINESS_REPLACE},
    "job": {**COMMON_REPLACE, **JOB_REPLACE},
    "all": {**COMMON_REPLACE, **VIDEO_REPLACE, **BUSINESS_REPLACE, **JOB_REPLACE},
    "none": {},
}

DROP_IF_ALONE = {
    "えー", "あー", "うーん", "えっと", "えっとね",
    "はいはい", "はい", "うん", "まあ", "まぁ",
}

FILLERS_AT_START = [
    "えー", "あー", "えっと", "えっとね", "うーん",
    "そのー", "あのー", "まあ", "まぁ",
]

KANJI_DIGIT = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}

KANJI_SMALL_UNIT = {
    "十": 10,
    "百": 100,
    "千": 1000,
}

KANJI_BIG_UNIT = {
    "万": 10000,
}

QUESTION_END_PATTERNS = [
    r"ですか$",
    r"ますか$",
    r"ましたか$",
    r"ませんか$",
    r"でしょうか$",
    r"なんですか$",
    r"なんでしょうか$",
    r"いいですか$",
    r"大丈夫ですか$",
    r"よろしいですか$",
    r"聞こえますか$",
    r"見えますか$",
    r"分かりますか$",
    r"わかりますか$",
    r"どうですか$",
    r"どう思いますか$",
    r"どう感じますか$",
    r"どうしますか$",
    r"どうしたんですか$",
    r"どうなりましたか$",
    r"どこですか$",
    r"誰ですか$",
    r"いつですか$",
    r"なんでですか$",
    r"なぜですか$",
    r"どれですか$",
    r"どっちですか$",
    r"いくらですか$",
    r"どう$",
    r"どこ$",
    r"誰$",
    r"いつ$",
    r"なんで$",
    r"なぜ$",
    r"どれ$",
    r"どっち$",
    r"いくら$",
    r"本当$",
    r"ほんと$",
    r"マジ$",
    r"まじ$",
]


def normalize_spaces(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\ufeff", "")
    s = s.replace("\u3000", " ")
    s = s.replace("\xa0", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def cleanup_noise(s: str) -> str:
    if not s:
        return ""

    s = s.replace("【", "").replace("】", "")
    s = s.replace("///", "")
    s = s.replace("ｑ", "q")

    s = re.sub(r"(?<![A-Za-z])q(?![A-Za-z])", "?", s)
    s = re.sub(r"\?{2,}", "?", s)
    s = re.sub(r"？{2,}", "？", s)
    s = re.sub(r"[!！]{2,}", "！", s)
    s = re.sub(r"[。]{2,}", "。", s)
    s = re.sub(r"[、]{2,}", "、", s)

    s = re.sub(r"(?mi)^\s*de\s*$", "", s)
    s = re.sub(r"(?m)^\s*で、?\s*$", "", s)
    s = re.sub(r"(?m)^\?+\s*$", "", s)
    s = re.sub(r"(?m)^？+\s*$", "", s)
    s = re.sub(r"(?m)^[ぁ-んァ-ンー]?\s*$", "", s)

    s = re.sub(r"\s+([、。！？?])", r"\1", s)
    s = re.sub(r"\s*,\s*", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def remove_punctuation(s: str) -> str:
    return s.replace("、", "").replace("。", "")


def remove_fillers(text: str) -> str:
    lines = text.split("\n")
    out = []

    for line in lines:
        line = line.strip()
        changed = True

        while changed:
            changed = False
            for f in FILLERS_AT_START:
                pattern = rf"^{re.escape(f)}[、。,\s]*"
                new_line = re.sub(pattern, "", line)
                if new_line != line:
                    line = new_line.strip()
                    changed = True

        out.append(line)

    return "\n".join(out).strip()


def apply_replace(s: str, replace_dict: dict) -> str:
    for a, b in sorted(replace_dict.items(), key=lambda x: len(x[0]), reverse=True):
        s = s.replace(a, b)
    return s


def kanji_number_to_int(token: str):
    if not token:
        return None

    total = 0
    section = 0
    number = 0
    used = False

    for ch in token:
        if ch in KANJI_DIGIT:
            number = KANJI_DIGIT[ch]
            used = True
        elif ch in KANJI_SMALL_UNIT:
            unit = KANJI_SMALL_UNIT[ch]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
            used = True
        elif ch in KANJI_BIG_UNIT:
            unit = KANJI_BIG_UNIT[ch]
            if number == 0 and section == 0:
                section = 1
            section += number
            total += section * unit
            section = 0
            number = 0
            used = True
        else:
            return None

    section += number
    total += section
    return total if used else None


def convert_kanji_numbers(text: str) -> str:
    units_after = "円人個本枚回社件年ヶ月日時間分秒代歳番台"
    pattern = r"[零〇一二三四五六七八九十百千万]+"

    def repl(m):
        token = m.group(0)
        end = m.span()[1]
        next_char = text[end:end + 1]

        contains_unit = any(u in token for u in "十百千万")
        followed_by_unit = next_char in units_after

        if len(token) == 1 and not followed_by_unit:
            return token

        if not contains_unit and not followed_by_unit:
            return token

        num = kanji_number_to_int(token)
        return str(num) if num is not None else token

    return re.sub(pattern, repl, text)


def is_question_sentence(text: str) -> bool:
    t = normalize_spaces(text)
    t = t.replace("。", "").replace("、", "").strip()

    if not t:
        return False

    if t.endswith(("?", "？")):
        return True

    if re.search(r"(してください|下さい|ください|お願いします|してくださいね)$", t):
        return False

    if re.search(r"(というか|なんか|だから|ていうか)$", t):
        return False

    for pattern in QUESTION_END_PATTERNS:
        if re.search(pattern, t):
            return True

    return False


def add_question_mark_if_needed(text: str, enabled: bool) -> str:
    t = text.strip()

    if not t:
        return t

    if not enabled:
        return t

    if t.endswith(("?", "？")):
        return t

    if is_question_sentence(t):
        return t + "？"

    return t


def parse_srt_blocks(srt_text: str):
    srt_text = srt_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    raw_blocks = re.split(r"\n\s*\n", srt_text, flags=re.MULTILINE)
    out = []

    for block in raw_blocks:
        lines = [x.rstrip() for x in block.splitlines()]
        lines = [x for x in lines if x.strip() != ""]

        if len(lines) < 2:
            continue

        if re.fullmatch(r"\d+", lines[0].strip()) and len(lines) >= 3:
            idx = lines[0].strip()
            timecode = lines[1].strip()
            body_lines = lines[2:]
        elif "-->" in lines[0]:
            idx = ""
            timecode = lines[0].strip()
            body_lines = lines[1:]
        else:
            continue

        if "-->" not in timecode:
            continue

        body = "\n".join(body_lines).strip()
        if body:
            out.append((idx, timecode, body))

    return out


def build_srt(blocks):
    parts = []
    for i, (_idx, timecode, body) in enumerate(blocks, start=1):
        parts.append(f"{i}\n{timecode}\n{body}")
    return "\n\n".join(parts) + "\n"


def tc_to_sec(tc: str) -> float:
    h, m, rest = tc.strip().split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def sec_to_tc(sec: float) -> str:
    if sec < 0:
        sec = 0.0

    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))

    if ms == 1000:
        s += 1
        ms = 0
    if s == 60:
        m += 1
        s = 0
    if m == 60:
        h += 1
        m = 0

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def split_timecode(timecode: str):
    start_tc, end_tc = [x.strip() for x in timecode.split("-->")]
    return tc_to_sec(start_tc), tc_to_sec(end_tc)


def make_timecode(start: float, end: float):
    return f"{sec_to_tc(start)} --> {sec_to_tc(end)}"


def stabilize_timing_safely(blocks, offset_ms=0, fix_overlap=True):
    offset = offset_ms / 1000.0
    timed = []

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            continue

        start += offset
        end += offset

        if start < 0:
            diff = -start
            start += diff
            end += diff

        if end <= start:
            end = start + MIN_DURATION_SEC

        timed.append([idx, start, end, body])

    if fix_overlap:
        for i in range(1, len(timed)):
            prev = timed[i - 1]
            cur = timed[i]

            if cur[1] < prev[2]:
                cur[1] = prev[2] + MIN_GAP_SEC

            if cur[2] <= cur[1]:
                cur[2] = cur[1] + MIN_DURATION_SEC

    out = []
    for idx, start, end, body in timed:
        out.append((idx, make_timecode(start, end), body))

    return out


def normalize_for_dedupe(text: str) -> str:
    t = text
    t = t.replace("\n", "")
    t = t.replace(" ", "")
    t = t.replace("　", "")
    t = t.replace("、", "")
    t = t.replace("。", "")
    t = t.replace("？", "")
    t = t.replace("?", "")
    t = t.replace("！", "")
    t = t.replace("!", "")
    return t.strip()


def remove_consecutive_duplicates(blocks, gap_ms=1200):
    if not blocks:
        return []

    out = []
    prev_text = None
    prev_end = None

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            continue

        cur_text = normalize_for_dedupe(body)
        is_duplicate = False

        if prev_text and cur_text and cur_text == prev_text:
            gap = start - prev_end if prev_end is not None else 9999
            if gap <= gap_ms / 1000.0:
                is_duplicate = True

        if not is_duplicate:
            out.append((idx, timecode, body))
            prev_text = cur_text
            prev_end = end

    return out


def should_drop_if_alone(text: str) -> bool:
    t = normalize_spaces(text)
    t = t.replace("、", "").replace("。", "")
    t = t.replace("？", "").replace("?", "")
    t = t.replace("！", "").replace("!", "")
    t = t.replace("…", "").strip()

    if not t:
        return True

    if t in DROP_IF_ALONE:
        return True

    if re.fullmatch(r"[?？!！…・ー]+", t):
        return True

    return False


def split_sentences(text: str):
    text = text.strip()
    if not text:
        return []

    parts = re.split(r"(?<=[。！？?])\s*", text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) == 1:
        t = parts[0]
        t = re.sub(
            r"(なんですか|でしょうか|ですか|ましたか|ませんか|でした|です|ます|だった|だね|ですね)(\s*)",
            r"\1\n",
            t
        )
        parts2 = [p.strip() for p in t.split("\n") if p.strip()]
        if parts2:
            parts = parts2

    return parts


def split_long_line(text: str, max_len=22):
    text = text.strip()

    if len(text) <= max_len:
        return [text]

    candidates = ["、", " ", "は", "が", "を", "に", "で", "と", "も", "って", "けど", "ので", "から"]
    best = None
    center = len(text) // 2

    for token in candidates:
        for m in re.finditer(re.escape(token), text):
            pos = m.end()
            score = abs(pos - center)
            if best is None or score < best[0]:
                best = (score, pos)

    if best:
        pos = best[1]
        left = text[:pos].strip()
        right = text[pos:].strip()
        if left and right:
            return [left, right]

    return [text[:max_len].strip(), text[max_len:].strip()]


def format_lines(sentences, allow_3=True, max_len=22):
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return ""

    units = []

    for s in sentences:
        if len(s) > max_len * 1.6:
            units.extend(split_long_line(s, max_len=max_len))
        else:
            units.append(s)

    if len(units) <= 2:
        return "\n".join(units)

    if allow_3 and len(units) <= 3:
        return "\n".join(units)

    total = sum(len(x) for x in units)
    target_lines = 3 if allow_3 and total > max_len * 2 else 2
    target = total / target_lines

    lines = []
    cur = ""

    for u in units:
        if not cur:
            cur = u
            continue

        if len(cur) + 1 + len(u) <= target + 6:
            cur += " " + u
        else:
            lines.append(cur)
            cur = u

    if cur:
        lines.append(cur)

    if len(lines) > target_lines:
        merged = []
        for line in lines:
            if len(merged) < target_lines:
                merged.append(line)
            else:
                merged[-1] += " " + line
        lines = merged

    return "\n".join(lines)


def fix_block_text(
    body,
    replace_dict,
    allow_3=True,
    max_chars=22,
    remove_punct=True,
    add_question=False,
):
    text = normalize_spaces(body)
    text = cleanup_noise(text)
    text = convert_kanji_numbers(text)
    text = apply_replace(text, replace_dict)
    text = remove_fillers(text)
    text = cleanup_noise(text)
    text = normalize_spaces(text)

    sentences = split_sentences(text)
    fixed_sentences = []

    for s in sentences:
        s = normalize_spaces(s)
        if not s:
            continue

        s = add_question_mark_if_needed(s, enabled=add_question)
        fixed_sentences.append(s)

    text = "\n".join(fixed_sentences)
    text = normalize_spaces(text)

    if remove_punct:
        text = remove_punctuation(text)
        text = normalize_spaces(text)

    if should_drop_if_alone(text):
        return ""

    lines = []
    for line in text.split("\n"):
        line = normalize_spaces(line)
        if line:
            lines.append(line)

    result = format_lines(lines, allow_3=allow_3, max_len=max_chars)
    result = re.sub(r"[ ]{2,}", " ", result).strip()

    if should_drop_if_alone(result):
        return ""

    return result


def convert_srt_text(
    srt_text: str,
    allow_3=True,
    max_chars=22,
    preset="common",
    remove_punct=True,
    add_question=False,
    offset_ms=0,
    fix_overlap=True,
    dedupe=True,
):
    blocks = parse_srt_blocks(srt_text)
    replace_dict = PRESETS.get(preset, COMMON_REPLACE)

    fixed_blocks = []

    for idx, timecode, body in blocks:
        fixed = fix_block_text(
            body=body,
            replace_dict=replace_dict,
            allow_3=allow_3,
            max_chars=max_chars,
            remove_punct=remove_punct,
            add_question=add_question,
        )

        if fixed:
            fixed_blocks.append((idx, timecode, fixed))

    fixed_blocks = stabilize_timing_safely(
        fixed_blocks,
        offset_ms=offset_ms,
        fix_overlap=fix_overlap,
    )

    if dedupe:
        fixed_blocks = remove_consecutive_duplicates(fixed_blocks, gap_ms=1200)

    return build_srt(fixed_blocks)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    if "srt_file" not in request.files:
        return "SRTファイルがありません", 400

    file = request.files["srt_file"]

    if file.filename == "":
        return "ファイルが選択されていません", 400

    if not file.filename.lower().endswith(".srt"):
        return "SRTファイルのみ対応しています", 400

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        return "ファイルサイズが大きすぎます。2MB以内のSRTを使ってください。", 400

    try:
        srt_text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        srt_text = data.decode("cp932", errors="replace")

    try:
        preset = request.form.get("preset", "common")
        max_chars = int(request.form.get("max_chars", "22"))
        offset_ms = int(request.form.get("offset_ms", "0"))

        allow_3 = request.form.get("allow_3") == "on"
        remove_punct = request.form.get("remove_punct") == "on"
        add_question = request.form.get("add_question") == "on"
        fix_overlap = request.form.get("fix_overlap") == "on"
        dedupe = request.form.get("dedupe") == "on"

        result_text = convert_srt_text(
            srt_text=srt_text,
            allow_3=allow_3,
            max_chars=max_chars,
            preset=preset,
            remove_punct=remove_punct,
            add_question=add_question,
            offset_ms=offset_ms,
            fix_overlap=fix_overlap,
            dedupe=dedupe,
        )

        if not result_text.strip():
            return "変換できる字幕がありませんでした。SRTの形式を確認してください。", 400

        output = io.BytesIO(result_text.encode("utf-8"))
        output.seek(0)

        original_name = file.filename.rsplit(".", 1)[0]
        download_name = f"{original_name}.final.srt"

        print(
            f"[{datetime.now()}] converted: "
            f"name={file.filename}, size={len(data)}, preset={preset}, "
            f"question={add_question}, punct={remove_punct}"
        )

        return send_file(
            output,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/x-subrip",
        )

    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        return "変換中にエラーが発生しました。SRTの形式を確認してください。", 500


if __name__ == "__main__":
    app.run(debug=True)
