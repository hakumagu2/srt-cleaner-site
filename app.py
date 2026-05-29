# -*- coding: utf-8 -*-
import io
import re
from datetime import datetime
from flask import Flask, render_template, request, send_file

# =========================================================
# Web版：SRTアップロード → 文脈重視SRT整形
#
# 方針：
# ・単語や文節を細かく切りすぎない
# ・短文として完結するなら1字幕
# ・2行にするときは「前半の説明 / 後半の結論・質問」にする
# ・必要な時だけ、隣の短い字幕を結合する
# ・元のタイムコードを押し出さない
# ・入力SRTをSRTのまま整形し、final.srt を出力
# =========================================================

LINE_CHARS_DEFAULT = 24          # 1行の目安。これより長くても自然なら1行可
ONE_LINE_LIMIT = 26              # この文字数までは基本1行
TWO_LINE_LIMIT = 44              # この文字数までは基本1字幕2行まで
HARD_SPLIT_LIMIT = 45            # これ以上なら字幕自体を2つに分ける候補
MIN_SPLIT_DURATION = 2.4         # これ未満の時間なら字幕分割しない
MIN_PART_DURATION = 0.80
MIN_GAP_SEC = 0.001

MERGE_GAP_SEC = 0.55             # 隣の字幕を結合できる最大間隔
MAX_MERGE_CHARS = 62             # 結合後の最大文字数

# 色付き字幕にしたい場合だけ使う
# 例: --font-color C4DDFFFF
FONT_COLOR_DEFAULT = ""

# =========================================================
# 置換辞書
# =========================================================

REPLACE = {
    "youtube": "YouTube",
    "ユーチューブ": "YouTube",
    "ＹｏｕＴｕｂｅ": "YouTube",
    "tiktok": "TikTok",
    "ティックトック": "TikTok",
    "インスタグラム": "Instagram",
    "ツイッター": "X",

    "プレミアプロ": "Premiere Pro",
    "プレミア プロ": "Premiere Pro",
    "アドビ": "Adobe",
    "フォトショップ": "Photoshop",
    "アフターエフェクト": "After Effects",
    "アフターエフェクツ": "After Effects",
    "ダビンチリゾルブ": "DaVinci Resolve",
    "ファイナルカット": "Final Cut Pro",
    "サムネ": "サムネイル",

    "パワー払い": "パワハラ",
    "パワ払": "パワハラ",
    "博業": "副業",
    "注入": "収入",
    "日頭": "日当",
    "ライン": "LINE",
    "オンLINE": "オンライン",
    "オン line": "オンライン",
    "受 講生": "受講生",
    "テレアっぽ": "テレアポ",
    "テレアップ": "テレアポ",
    "残量": "残業",
    "体育会計": "体育会系",
    "シャフ": "社不",
    "法連争": "報連相",

    "やめ": "辞め",
    "公開": "後悔",
    "ライブドアにもならないような": "ネタにもならないような",
    "ねぎり": "ぎり",
    "くしずさんだ": "口ずさんだ",
    "アイシールの21": "アイシールド21",
    "プレジェント": "エージェント",
    "エイジェント": "エージェント",
    "タイモー": "体毛",
    "回収の方が臭かったり": "体臭が臭かったり",
    "悠々自敵": "悠々自適",
    "バックレート": "バックレて",
    "比率": "起立",
    "れって": "敬礼って",
    "年座": "捻挫",
    "療制中": "療養中",
    "ボケ役先": "ご契約先",
    "回答のパソコン": "会社のパソコン",
    "重大上": "10台上",
    "トーム": "当務",
    "フット繰り返してて": "ずっと繰り返してて",
    "治療の診断": "鬱病の診断",
    "もしさるとおりです": "おっしゃる通りです",
    "化病": "仮病",
    "チャミ": "ちなみに",
    "賞の叩き直された": "性根を叩き直された",
    "ずさってきました": "グサッてきました",
    "多くてるんで": "わかってるんで",
    "医者の内定": "1社内定",
    "新店": "進展",

    "おもしろーし": "もしもーし",
    "あおもしろしい": "もしもし",
    "聞えますか": "聞こえますか",
    "聞えます か": "聞こえますか",
    "聞こえます か": "聞こえますか",
    "卒内容": "凸内容",
    "ヘンタル": "メンタル",
    "キンジストロフィー": "筋ジストロフィー",
    "前年ナース": "全然ナース",
    "泊み込ました": "勤めてました",
    "宝れてた": "たかられてた",
    "昼食活動": "就職活動",
    "なるほどです ね": "なるほどですね",
    "別かれて": "別れて",
    "走ちゃった": "走っちゃった",
    "見ばれ": "身バレ",

    "サザエ": "さざえ",
    "うつ病": "鬱病",

    # 今回のサンプル寄り
    "1026年卒": "2026年卒",
    "1026年": "2026年",
    "1026": "2026",
    "石骨院": "接骨院",
    "骨盤強制": "骨盤矯正",
    "解散": "改ざん",
    "金量": "給料",
    "しらっと": "ちらっと",
    "身を見真似": "見よう見まね",
    "何もないのみたいな": "何もないの...？",
    "という家です": "という形です",
    "ニーズが足りない": "人数が足りない",
    "営業を入れて": "営業に出て",
    "こまで自分も": "そこまで自分も",

    # 接骨院・面接系の追加
    "積極院": "接骨院",
    "背骨院": "接骨院",
    "正骨院": "接骨院",
    "整骨院": "接骨院",
    "人体の骨の仕組みみたいなの": "人体の骨の仕組み",
    "ちんぷいんかんぷいん": "ちんぷんかんぷん",
    "チンプイんかんぷん": "ちんぷんかんぷん",
    "分かんなかくて": "分からなくて",
    "分かんなくて": "分からなくて",
    "完全未経減": "完全未経験",
    "完全ミ経験": "完全未経験",
    "退職に至るまでの経験": "退職に至るまでの経緯",
    "経験を順を追って": "経緯を順を追って",
    "獣人": "求人",
    "休職票": "求人票",
    "院長とかって": "院長って",
    "日報が解散": "日報が改ざん",
    "日報解散": "日報改ざん",
    "金量改ざん": "給料改ざん",
    "給料解散": "給料改ざん",
    "施術してこい": "施術してこい",
    "何もできないのに": "何もできないのに",

    # さらに訂正版寄せ
    "そういう人体の骨の仕組み": "人体の骨の仕組み",
    "人体の骨の仕組みみたいなのを": "人体の骨の仕組みを",
    "学校でそういう": "学校で",
    "患者さんの触ってストレッチしてたのを": "「患者さんのストレッチして」だの",
    "患者さんの触ってストレッチしてた": "「患者さんのストレッチして」だの",
    "患者さんのストレッチしてたのを": "「患者さんのストレッチして」だの",
    "たのを 言われて": "だの言われて",
    "何もないのみたいな": "何もないの...？",
    "何もないの...？?": "何もないの...？",
    "いやしてないんですけど": "いやしてないんですけど",
    "給料下げるぞみたいな": "給料下げるぞみたいな",
    "やばいかなって思って": "やばいかなって思って",
}

CONTEXT_REPLACEMENTS = [
    (r"精神ではない", "正社員ではない"),

    (r"社科(?=を聞いて)", "社歌"),
    (r"社科(?=が6時に)", "社歌"),
    (r"軍科(?=みたいな)", "軍歌"),

    (r"給食(?=は使えません)", "休職"),
    (r"給食(?=ないって)", "休職"),
    (r"給食(?=はちょっと使えなくて)", "休職"),

    (r"高齢層(?=があまりにも多い)", "報連相"),
    (r"起業理解", "企業理解"),
    (r"病気扱いですね", "病欠扱いですね"),

    (r"夜勤を戦場にやってた", "夜勤を専従にやってた"),
    (r"夜勤を戦場に", "夜勤を専従に"),
    (r"夜勤も払えない", "家賃も払えない"),
    (r"二勤と夜勤", "日勤と夜勤"),
    (r"2設施", "2施設"),
    (r"3設施", "3施設"),
    (r"マッチアップ男", "マッチングアプリの男"),
    (r"マッチアップ", "マッチングアプリ"),
    (r"マチアプ", "マッチアプ"),
    (r"蠣", "牡蠣"),
]

DROP_IF_ALONE = {
    "えー", "あー", "うーん", "えっと", "えっとね", "うーんね",
    "はいはい", "はい", "うん", "まあ", "まぁ",
}

FILLERS_AT_START = [
    "えー", "あー", "えっと", "えっとね", "うーん", "そのー", "あのー",
]

KANJI_DIGIT = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}
KANJI_SMALL_UNIT = {"十": 10, "百": 100, "千": 1000}
KANJI_BIG_UNIT = {"万": 10000}


# =========================================================
# 基本文字処理
# =========================================================

def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def normalize_spaces(s: str) -> str:
    if not s:
        return ""
    s = strip_tags(s)
    s = s.replace("\ufeff", "")
    s = s.replace("\u3000", " ")
    s = s.replace("\xa0", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def flatten_text(s: str) -> str:
    s = normalize_spaces(s)
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def remove_punctuation(s: str) -> str:
    # 字幕では句読点は基本消す。ただし ? や ! や ... は残す。
    return s.replace("、", "").replace("。", "")


def cleanup_noise(s: str) -> str:
    if not s:
        return ""

    s = strip_tags(s)
    s = s.replace("【", "").replace("】", "")
    s = s.replace("///", "")

    # 単独qだけ ? にする
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

    s = s.replace("です ね", "ですね")
    s = s.replace("そうです ね", "そうですね")
    s = s.replace("なんです ね", "なんですね")
    s = s.replace("なるほどです ね", "なるほどですね")
    s = s.replace("聞こえます か", "聞こえますか")
    s = s.replace("聞えます か", "聞こえますか")

    s = re.sub(r"\s+([、。！？?])", r"\1", s)
    s = re.sub(r"\s*,\s*", " ", s)

    return normalize_spaces(s)


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


def apply_replace(s: str) -> str:
    for a, b in sorted(REPLACE.items(), key=lambda x: len(x[0]), reverse=True):
        s = s.replace(a, b)
    return s


def apply_context_replace(s: str) -> str:
    for pattern, repl in CONTEXT_REPLACEMENTS:
        s = re.sub(pattern, repl, s)
    return s


def remove_internal_repeated_phrase(text: str) -> str:
    """
    字幕内で同じフレーズが連続する場合だけ削る。
    例: 分かります分かります → 分かります
    """
    t = flatten_text(text)
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"(.{4,24})\1+", r"\1", t)
    return t.strip()


# =========================================================
# 漢数字 → 数字
# =========================================================

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
        end = m.end()
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


# =========================================================
# SRT処理
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


# =========================================================
# 本文クリーニング
# =========================================================

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


def is_question_like(s: str) -> bool:
    s = s.strip()
    if s.endswith(("？", "?")):
        return True

    question_endings = (
        "なんですか", "ですか", "でしょうか", "ましたか", "ませんか",
        "感じですか", "したんですか", "どうされましたか", "いいですか",
        "聞けるんですかね", "違うんですか",
    )

    return s.endswith(question_endings)


def ensure_question_mark(s: str, add_question_mark=True) -> str:
    s = s.strip()
    if not s:
        return s

    if s.endswith(("？", "?")):
        return s

    if add_question_mark and is_question_like(s):
        return s + "?"

    return s


def clean_body_text(body: str, remove_punct=True, add_question_mark=True) -> str:
    text = normalize_spaces(body)
    text = cleanup_noise(text)
    text = convert_kanji_numbers(text)
    text = apply_replace(text)
    text = apply_context_replace(text)
    text = remove_fillers(text)
    text = cleanup_noise(text)
    text = remove_internal_repeated_phrase(text)

    if remove_punct:
        text = remove_punctuation(text)

    text = flatten_text(text)
    text = ensure_question_mark(text, add_question_mark=add_question_mark)

    return text


# =========================================================
# 文脈結合
# =========================================================

BOUNDARY_STARTS = (
    "なるほど", "じゃあ", "はい", "そうですね", "いいですね",
    "ちなみに", "では", "次", "まず", "いや", "お疲れ様",
    "そしたら", "ではでは", "ありがとうございました",
)

def should_not_merge(a: str, b: str) -> bool:
    a = flatten_text(a)
    b = flatten_text(b)

    if not a or not b:
        return True
    if a.endswith(("?", "？", "!", "！")):
        return True
    if b.startswith(BOUNDARY_STARTS):
        return True

    return False


def is_strong_continuation(a: str, b: str) -> bool:
    """
    a と b を1字幕にまとめた方が自然かどうか。
    訂正版SRTの傾向に合わせて、
    「前半の説明」＋「後半の完成文/質問」を拾いやすくする。
    """
    a = flatten_text(a)
    b = flatten_text(b)

    if should_not_merge(a, b):
        return False

    combined = a + b
    if len(combined) > MAX_MERGE_CHARS:
        return False

    # 1) 前が明らかに途中で終わっている
    continuation_ends = (
        "を", "が", "は", "に", "で", "と", "も", "へ",
        "の", "とか", "みたいな", "みたいなの", "というのを",
        "経緯を", "仕組み", "仕組みを", "骨の仕組み", "やつを",
        "求人票を", "求人の内容を", "退職に至るまでの経緯を",
        "完全未経験とか", "全く何も分からない状態で",
        "4月の最初から", "受付やって", "患者さんから",
        "それが増えてくと", "見よう見まねで",
        "院長が", "先輩が", "社長が", "会社のやつが",
    )
    if a.endswith(continuation_ends):
        return True

    # 2) 前が接続語・未完了で終わっている
    if re.search(
        r"(けど|ですけど|なんですけど|けれども|なので|だから|から|ので|して|しまして|してて|していて|"
        r"なくて|やって|聞いて|言われて|増えてくと|始まって|入って|出て|見て|押して|やったら|"
        r"なりまして|トラブルになりまして|続かず|合わなくて)$",
        a
    ):
        return True

    # 3) 後ろが明らかに前の続き
    continuation_starts = (
        "を勉強", "を教えて", "を見て", "をやって", "を聞いて",
        "順を追って", "教えてもらって", "いいですか", "感じですか",
        "入ったんですけど", "入ったみたいな", "状態で入った",
        "仕事の時間にも", "やることになるから", "電気とか",
        "できるでしょ", "患者さんの", "先輩っていう",
        "施術してこい", "何もできないのに", "言われて",
        "ちょっと聞きたいんですけど", "全部ちんぷんかんぷん",
    )
    if b.startswith(continuation_starts):
        return True

    # 4) aが短い名詞句、bがそれを説明している
    if len(a) <= 18 and re.search(r"(求人票|骨の仕組み|完全未経験|受付|患者さん|院長|先輩|日報|給料|施術)$", a):
        if not b.startswith(BOUNDARY_STARTS):
            return True

    # 5) 質問文の前半 + 後半
    if re.search(r"(ですか|でしょうか|いいですか|聞きたいんですけど)$", b):
        if len(combined) <= MAX_MERGE_CHARS:
            return True

    return False


def make_clean_items(blocks, remove_punct=True, add_question_mark=True):
    items = []

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            continue

        cleaned = clean_body_text(
            body,
            remove_punct=remove_punct,
            add_question_mark=add_question_mark,
        )

        if not cleaned or should_drop_if_alone(cleaned):
            continue

        items.append([idx, start, end, cleaned])

    return items


def merge_context_items_once(items):
    """
    1周分の文脈結合。
    """
    if not items:
        return []

    out = []
    i = 0

    while i < len(items):
        cur = items[i]

        if i + 1 < len(items):
            nxt = items[i + 1]
            gap = nxt[1] - cur[2]

            if gap <= MERGE_GAP_SEC and is_strong_continuation(cur[3], nxt[3]):
                combined = flatten_text(cur[3] + " " + nxt[3])
                out.append([cur[0], cur[1], nxt[2], combined])
                i += 2
                continue

        out.append(cur)
        i += 1

    return out


def merge_context_items(items):
    """
    Whisperが変な場所で分けた短文を結合する。
    1回だけだと「A+B」後に「+C」が拾えないので、最大3周まで行う。
    ただし MAX_MERGE_CHARS を超えるものは結合しない。
    """
    prev_len = None
    cur = items

    for _ in range(3):
        new_items = merge_context_items_once(cur)
        if prev_len == len(new_items) or len(new_items) == len(cur):
            cur = new_items
            break
        prev_len = len(new_items)
        cur = new_items

    return cur


# =========================================================
# 2行化・字幕分割
# =========================================================

def bad_tiny_line(left: str, right: str) -> bool:
    left = left.strip()
    right = right.strip()

    if len(left) < 5 or len(right) < 4:
        return True

    # 単語の途中っぽいものを防止
    if re.search(r"[ぁ-んァ-ン一-龥A-Za-z0-9]$", left) and re.match(r"^[ぁ-んァ-ン一-龥A-Za-z0-9]", right):
        # ただし文法上の自然な切れ目なら許可
        allowed = (
            left.endswith((
                "を", "が", "は", "に", "で", "と", "も",
                "から", "けど", "ので", "って", "っていう",
                "して", "してて", "やって", "聞いて", "言われて",
                "仕組み", "経緯を", "完全未経験とか", "受付やって",
                "それが増えてくと", "4月の最初から", "見よう見まねで",
            )),
            right.startswith((
                "を", "が", "は", "に", "で", "と", "も",
                "順を", "仕事の", "電気", "入った", "患者さん",
                "を勉強", "を教えて", "状態で", "全く", "ちょっと",
                "施術してこい", "何もできないのに",
            )),
        )
        if not any(allowed):
            return True

    return False


def find_line_break(text: str):
    """
    2行にするならここ、という位置を探す。
    ユーザー訂正版に近く、前半説明 / 後半結論に分ける。
    """
    text = flatten_text(text)
    n = len(text)

    if n <= ONE_LINE_LIMIT:
        return None

    # 優先度順
    tokens = [
        # 非常に自然：ここで前半説明、後半が続き
        "退職に至るまでの経緯を", "経緯を", "仕組み", "骨の仕組み",
        "完全未経験とか", "全く何も分からない状態で",
        "聞いて", "できるよって聞いて",
        "それが増えてくと", "4月の最初から", "受付やって",
        "患者さんから", "見よう見まねで", "院長が", "先輩が",
        "求人票を", "求人の内容を", "っていうんですか",
        "見よう見まねで押してみるわけですか",

        # 自然
        "ので", "から", "けど", "ですけど", "なんですけど",
        "して", "していて", "してて", "やって", "なくて",
        "言われて", "だの言われて", "増えてくと",
        "とか", "っていう", "って",
        "を", "が", "は", "に", "で", "と",
    ]

    center = n / 2
    min_pos = max(6, int(center - 16))
    max_pos = min(n - 4, int(center + 16))

    candidates = []

    for priority, token in enumerate(tokens):
        for m in re.finditer(re.escape(token), text):
            pos = m.end()

            if pos < min_pos or pos > max_pos:
                continue

            left = text[:pos].strip()
            right = text[pos:].strip()

            if bad_tiny_line(left, right):
                continue

            # 中央に近いほど良い。優先度も加味。
            score = priority * 100 + abs(center - pos)
            candidates.append((score, pos))

    if not candidates:
        # 中央付近にない場合、長文だけ行頭側で探す
        if n <= TWO_LINE_LIMIT:
            search_min = 8
            search_max = min(n - 5, LINE_CHARS_DEFAULT + 10)

            for priority, token in enumerate(tokens):
                for m in re.finditer(re.escape(token), text):
                    pos = m.end()

                    if pos < search_min or pos > search_max:
                        continue

                    left = text[:pos].strip()
                    right = text[pos:].strip()

                    if bad_tiny_line(left, right):
                        continue

                    score = priority * 100 + abs(LINE_CHARS_DEFAULT - pos)
                    candidates.append((score, pos))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def format_two_lines(text: str, font_color: str = ""):
    text = flatten_text(text)
    text = re.sub(r"([をがはにでともへ])\s+", r"\1", text)
    text = text.replace(" ?","?").replace(" ？","？")

    if len(text) <= ONE_LINE_LIMIT:
        return apply_font(text, font_color)

    pos = find_line_break(text)

    # 良い切れ目がないなら無理に改行しない
    if pos is None:
        return apply_font(text, font_color)

    left = text[:pos].strip()
    right = text[pos:].strip()

    if bad_tiny_line(left, right):
        return apply_font(text, font_color)

    return apply_font(left, font_color) + "\n" + apply_font(right, font_color)




def split_by_strong_phrases(text: str):
    """
    結合後に長すぎる字幕を、訂正版に近い意味単位へ切る。
    文字数ではなく「ここで別字幕にしたい」フレーズを優先。
    """
    text = flatten_text(text)
    if not text:
        return []

    # ここは「前で切る」候補。
    # 例: A 完全未経験とか B → A / 完全未経験とか B
    before_markers = [
        "完全未経験とか",
        "トレーニングみたいなやつがしたくて",
        "入社してすぐは",
        "何か研修みたいなのがあったんですか",
        "給料下げるぞみたいな",
        "やばいかなって思って辞めました",
        "何もないの...？",
        "あとはなんか",
    ]

    # ここは「後ろで切る」候補。
    # 例: A なんですけど B → Aなんですけど / B
    after_markers = [
        "いやしてないんですけど",
        "ちょっと聞きたいんですけど",
        "仕事の時間にもやることになるから",
        "給料下げるぞみたいな",
        "完全未経験とか",
        "全く何も分からない状態で入ったみたいな?",
        "全く何も分からない状態で入ったみたいな",
    ]

    parts = [text]

    # 前で切る
    for marker in before_markers:
        new_parts = []
        for part in parts:
            if len(part) <= TWO_LINE_LIMIT:
                new_parts.append(part)
                continue

            pos = part.find(marker)
            if pos > 8:
                left = part[:pos].strip()
                right = part[pos:].strip()
                if left and right:
                    new_parts.extend([left, right])
                else:
                    new_parts.append(part)
            else:
                new_parts.append(part)
        parts = new_parts

    # 後ろで切る
    for marker in after_markers:
        new_parts = []
        for part in parts:
            if len(part) <= TWO_LINE_LIMIT:
                new_parts.append(part)
                continue

            pos = part.find(marker)
            if pos >= 0:
                cut = pos + len(marker)
                left = part[:cut].strip()
                right = part[cut:].strip()
                if len(left) >= 8 and len(right) >= 8:
                    new_parts.extend([left, right])
                else:
                    new_parts.append(part)
            else:
                new_parts.append(part)
        parts = new_parts

    # 最後に、まだ長すぎるものだけ自然な切れ目で2分割
    final = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        if len(part) <= TWO_LINE_LIMIT:
            final.append(part)
            continue

        pos = find_caption_split_position_loose(part)
        if pos:
            left = part[:pos].strip()
            right = part[pos:].strip()
            if len(left) >= 8 and len(right) >= 8:
                final.extend([left, right])
            else:
                final.append(part)
        else:
            final.append(part)

    return [p for p in final if p.strip()]


def find_caption_split_position_loose(text: str):
    """
    長すぎる字幕を別字幕へ分けるための、少しゆるめの分割位置。
    改行用ではなく、字幕自体の分割用。
    """
    text = flatten_text(text)
    n = len(text)
    if n <= TWO_LINE_LIMIT:
        return None

    tokens = [
        "なんですけど", "ですけど", "けど",
        "ということで", "それで", "その後に",
        "なので", "だから", "から",
        "しました", "しまして", "していて", "してて", "して",
        "言われて", "だの言われて",
        "みたいな", "みたいな?", "みたいな？",
    ]

    center = n / 2
    min_pos = max(10, int(center - 20))
    max_pos = min(n - 8, int(center + 20))

    candidates = []
    for priority, token in enumerate(tokens):
        for m in re.finditer(re.escape(token), text):
            pos = m.end()
            if pos < min_pos or pos > max_pos:
                continue
            left = text[:pos].strip()
            right = text[pos:].strip()
            if len(left) < 8 or len(right) < 8:
                continue
            if bad_tiny_line(left, right):
                continue
            score = priority * 100 + abs(center - pos)
            candidates.append((score, pos))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def find_caption_split(text: str, duration: float):
    """
    字幕自体を2つに分ける位置。
    かなり長い時だけ使う。
    """
    text = flatten_text(text)
    n = len(text)

    if n < HARD_SPLIT_LIMIT:
        return None
    if duration < MIN_SPLIT_DURATION:
        return None
    if duration / 2 < MIN_PART_DURATION:
        return None

    tokens = [
        "なんですけど", "ですけど", "けど",
        "ということで", "それで", "その後に", "あとはなんか",
        "なので", "だから", "から",
        "しました", "しまして", "していて", "して",
    ]

    center = n / 2
    min_pos = max(12, int(center - 18))
    max_pos = min(n - 8, int(center + 18))

    candidates = []

    for priority, token in enumerate(tokens):
        for m in re.finditer(re.escape(token), text):
            pos = m.end()
            if pos < min_pos or pos > max_pos:
                continue

            left = text[:pos].strip()
            right = text[pos:].strip()

            if bad_tiny_line(left, right):
                continue

            if len(left) < 12 or len(right) < 10:
                continue

            score = priority * 100 + abs(center - pos)
            candidates.append((score, pos))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def apply_font(text: str, font_color: str = ""):
    text = text.strip()
    if not text:
        return text
    if font_color:
        return f"<font color=#{font_color}>{text}</font>"
    return text


def split_long_caption(item):
    """
    結合後に長すぎる字幕を意味単位で再分割する。
    元の start-end の中だけで時間を割るので、後続字幕は押し出さない。
    """
    idx, start, end, text = item
    duration = max(0.01, end - start)
    text = flatten_text(text)

    # 短いものは分けない
    if len(text) <= TWO_LINE_LIMIT:
        return [item]

    # まず強いフレーズで複数分割
    chunks = split_by_strong_phrases(text)

    # 分割できなかった場合は従来の2分割
    if len(chunks) <= 1:
        pos = find_caption_split(text, duration)
        if pos is None:
            return [item]
        chunks = [text[:pos].strip(), text[pos:].strip()]

    chunks = [c for c in chunks if c.strip()]

    # 分割しすぎで1個あたりが短すぎるなら、近いものを戻す
    if chunks and duration / len(chunks) < 0.55:
        if len(chunks) >= 3:
            # 後ろ側から結合して個数を減らす
            merged = []
            buf = ""
            for c in chunks:
                if not buf:
                    buf = c
                elif len(buf + c) <= TWO_LINE_LIMIT:
                    buf = flatten_text(buf + " " + c)
                else:
                    merged.append(buf)
                    buf = c
            if buf:
                merged.append(buf)
            chunks = merged

    if len(chunks) <= 1:
        return [item]

    weights = [max(1, len(flatten_text(c))) for c in chunks]
    total_weight = sum(weights)

    out = []
    cur_start = start

    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            cur_end = end
        else:
            part_duration = duration * (weights[i] / total_weight)
            cur_end = cur_start + part_duration
            if cur_end > end:
                cur_end = end

        if cur_end <= cur_start:
            break

        out.append([idx, cur_start, cur_end, chunk])
        cur_start = cur_end + MIN_GAP_SEC

        if cur_start >= end:
            break

    return out if out else [item]


def normalize_for_dedupe(text: str) -> str:
    t = strip_tags(flatten_text(text))
    t = t.replace(" ", "").replace("　", "")
    t = t.replace("、", "").replace("。", "")
    t = t.replace("？", "").replace("?", "")
    t = t.replace("！", "").replace("!", "")
    t = t.replace("…", "")
    return t.strip()


def remove_consecutive_duplicates(blocks, gap_ms=1400):
    if not blocks:
        return []

    out = []
    prev_text = ""
    prev_end = None

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            continue

        cur_text = normalize_for_dedupe(body)
        is_duplicate = False

        if prev_text and cur_text:
            gap = start - prev_end if prev_end is not None else 9999
            if gap <= gap_ms / 1000.0:
                if cur_text == prev_text:
                    is_duplicate = True
                elif len(cur_text) >= 6 and cur_text in prev_text:
                    is_duplicate = True
                elif len(prev_text) >= 6 and prev_text in cur_text:
                    if out:
                        out[-1] = (out[-1][0], out[-1][1], body)
                        prev_text = cur_text
                        prev_end = end
                    is_duplicate = True

        if not is_duplicate:
            out.append((idx, timecode, body))
            prev_text = cur_text
            prev_end = end

    return out


def apply_offset_only(blocks, offset_ms=0):
    if offset_ms == 0:
        return blocks

    offset = offset_ms / 1000.0
    out = []

    for idx, timecode, body in blocks:
        try:
            start, end = split_timecode(timecode)
        except Exception:
            out.append((idx, timecode, body))
            continue

        start += offset
        end += offset

        if start < 0:
            diff = -start
            start += diff
            end += diff

        if end <= start:
            end = start + 0.1

        out.append((idx, make_timecode(start, end), body))

    return out



# =========================================================
# Flask Web版：SRTをSRTのまま整形
# =========================================================

app = Flask(__name__)
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB


def convert_srt_text_to_final(
    srt_text: str,
    remove_punct=True,
    add_question_mark=True,
    offset_ms=0,
    dedupe=True,
    dedupe_gap_ms=1400,
    font_color="",
):
    """
    SRT文字列を受け取り、元コードと同じ条件で整形したSRT文字列を返す。
    WhisperやMP3処理は行わない。
    """
    blocks = parse_srt_blocks(srt_text)

    items = make_clean_items(
        blocks,
        remove_punct=remove_punct,
        add_question_mark=add_question_mark,
    )

    # 文脈的に続くところだけ結合
    items = merge_context_items(items)

    # 長すぎる字幕だけ分割
    split_items = []
    for item in items:
        split_items.extend(split_long_caption(item))

    fixed_blocks = []
    for idx, start, end, txt in split_items:
        formatted = format_two_lines(txt, font_color=font_color)
        if formatted and not should_drop_if_alone(strip_tags(formatted)):
            fixed_blocks.append((idx, make_timecode(start, end), formatted))

    fixed_blocks = apply_offset_only(fixed_blocks, offset_ms=offset_ms)

    if dedupe:
        fixed_blocks = remove_consecutive_duplicates(
            fixed_blocks,
            gap_ms=dedupe_gap_ms,
        )

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
        # 画面側には出さない固定条件。
        # 添付されたローカル版コードの標準条件をそのまま使う。
        result_text = convert_srt_text_to_final(
            srt_text=srt_text,
            remove_punct=True,
            add_question_mark=True,
            offset_ms=0,
            dedupe=True,
            dedupe_gap_ms=1400,
            font_color="",
        )

        if not result_text.strip():
            return "変換できる字幕がありませんでした。SRTの形式を確認してください。", 400

        output = io.BytesIO(result_text.encode("utf-8"))
        output.seek(0)

        original_name = file.filename.rsplit(".", 1)[0]
        download_name = f"{original_name}.final.srt"

        print(
            f"[{datetime.now()}] converted: "
            f"name={file.filename}, size={len(data)}, mode=srt_context_formatter"
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
