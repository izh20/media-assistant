import argparse
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


VIDEO_DIR = Path('/Volumes/扩展盘512G/video test')
REPORT_PATH = Path('/tmp/media_subtitle_eval_minimax_bulk_report.json')
RAW_DUMP_DIR = Path('/tmp/media_subtitle_eval_minimax_bulk_raw')
MINIMAX_CONFIG_PATH = Path.home() / '.openclaw' / 'openclaw.json'
MINIMAX_API_BASE = 'https://api.minimaxi.com/v1'
MINIMAX_CHAT_URL = f'{MINIMAX_API_BASE}/chat/completions'
MINIMAX_MODEL = 'MiniMax-M2.7'

VIDEOS = [
    {
        'name': 'Ginga',
        'source': VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb_ja.srt',
        'translated': VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb_zh_minimax_bulk.srt',
        'bilingual': VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb_bilingual_minimax_bulk.srt',
        'references': {
            'translated_vs_zh': VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb.chi.Simplified.srt',
            'translated_vs_zh_traditional': VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb.chi.Traditional.srt',
            'bilingual_vs_mul': VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb.mul.srt',
        },
    },
    {
        'name': 'Hanzawa',
        'source': VIDEO_DIR / 'Hanzawa.Naoki.S02E05.2020.HDTV.1080p.x265.10bit-Yumi_ja.srt',
        'translated': VIDEO_DIR / 'Hanzawa.Naoki.S02E05.2020.HDTV.1080p.x265.10bit-Yumi_zh_minimax_bulk.srt',
        'bilingual': VIDEO_DIR / 'Hanzawa.Naoki.S02E05.2020.HDTV.1080p.x265.10bit-Yumi_bilingual_minimax_bulk.srt',
        'references': {
            'translated_vs_zh': VIDEO_DIR / 'Hanzawa.Naoki.S02E05.2020.HDTV.1080p.x265.10bit-Yumi.chi.srt',
        },
    },
]

BASELINE_REPORT_PATH = Path('/tmp/media_subtitle_eval_faster_report.json')


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str
    lines: list[str]


TIME_RE = re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)')


def parse_args():
    parser = argparse.ArgumentParser(description='Run one-shot MiniMax subtitle translation eval.')
    parser.add_argument('--video', help='Only process videos whose source path contains this text.')
    parser.add_argument('--limit', type=int, default=0, help='Only translate the first N cues for smoke validation.')
    parser.add_argument('--max-items', type=int, default=80, help='Max subtitle items per MiniMax bulk window.')
    parser.add_argument('--max-chars', type=int, default=6000, help='Max estimated chars per MiniMax bulk window.')
    return parser.parse_args()


def load_minimax_api_key() -> str:
    config = json.loads(MINIMAX_CONFIG_PATH.read_text(encoding='utf-8'))
    key = config.get('models', {}).get('providers', {}).get('minimax', {}).get('apiKey', '').strip()
    if not key:
        raise RuntimeError('MiniMax apiKey not found in ~/.openclaw/openclaw.json')
    return key


def parse_ts(ts: str) -> float:
    match = TIME_RE.match(ts.strip())
    if not match:
        raise ValueError(f'bad timestamp: {ts}')
    hour, minute, second, millis = map(int, match.groups())
    if len(match.group(4)) == 2:
        millis *= 10
    return hour * 3600 + minute * 60 + second + millis / 1000


def format_time(seconds: float) -> str:
    hour = int(seconds // 3600)
    minute = int((seconds % 3600) // 60)
    second = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    return f'{hour:02d}:{minute:02d}:{second:02d},{millis:03d}'


def parse_srt(path: Path) -> list[Cue]:
    text = path.read_text(encoding='utf-8', errors='replace').replace('\r\n', '\n')
    blocks = re.split(r'\n\s*\n', text.strip())
    cues = []
    for block in blocks:
        lines = [line for line in block.split('\n') if line.strip()]
        if len(lines) < 2:
            continue
        idx_line = lines[0].strip()
        timeline = lines[1]
        payload = lines[2:] if '-->' in timeline else lines[1:]
        if '-->' not in timeline:
            timeline = lines[0]
            payload = lines[1:]
            index = len(cues) + 1
        else:
            try:
                index = int(idx_line)
            except ValueError:
                index = len(cues) + 1
        start_text, end_text = [part.strip() for part in timeline.split('-->')]
        cues.append(Cue(index, parse_ts(start_text), parse_ts(end_text), '\n'.join(payload).strip(), payload))
    return cues


def normalize_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r'\{[^}]*\}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', '', text)
    text = text.replace('…', '...')
    text = text.replace('，', ',').replace('。', '.').replace('！', '!').replace('？', '?').replace('：', ':').replace('；', ';')
    return text.lower()


def normalize_lines(lines: list[str]) -> list[str]:
    return [line for line in (normalize_text(line) for line in lines) if line]


def midpoint_hits(lhs: list[Cue], rhs: list[Cue]) -> float:
    if not lhs or not rhs:
        return 0.0
    hits = 0
    rhs_index = 0
    rhs_ranges = [(cue.start, cue.end) for cue in rhs]
    for cue in lhs:
        midpoint = (cue.start + cue.end) / 2
        while rhs_index < len(rhs_ranges) and rhs_ranges[rhs_index][1] < midpoint:
            rhs_index += 1
        matched = False
        for candidate in (rhs_index - 1, rhs_index, rhs_index + 1):
            if 0 <= candidate < len(rhs_ranges):
                start, end = rhs_ranges[candidate]
                if start <= midpoint <= end:
                    matched = True
                    break
        if matched:
            hits += 1
    return hits / len(lhs)


def similarity(lhs: str, rhs: str) -> float:
    if not lhs and not rhs:
        return 1.0
    return SequenceMatcher(None, lhs, rhs).ratio()


def compare_mono(generated_path: Path, reference_path: Path) -> dict:
    generated = parse_srt(generated_path)
    reference = parse_srt(reference_path)
    generated_text = ''.join(normalize_text(cue.text) for cue in generated)
    reference_text = ''.join(normalize_text(cue.text) for cue in reference)
    return {
        'generated_file': str(generated_path),
        'reference_file': str(reference_path),
        'generated_cues': len(generated),
        'reference_cues': len(reference),
        'generated_span_sec': round(generated[-1].end - generated[0].start, 3) if generated else 0,
        'reference_span_sec': round(reference[-1].end - reference[0].start, 3) if reference else 0,
        'text_similarity': round(similarity(generated_text, reference_text), 4),
        'generated_midpoint_hit_rate': round(midpoint_hits(generated, reference), 4),
        'reference_midpoint_hit_rate': round(midpoint_hits(reference, generated), 4),
        'first_generated': generated[0].text if generated else '',
        'first_reference': reference[0].text if reference else '',
        'last_generated': generated[-1].text if generated else '',
        'last_reference': reference[-1].text if reference else '',
    }


def compare_bilingual(generated_path: Path, reference_path: Path) -> dict:
    generated = parse_srt(generated_path)
    reference = parse_srt(reference_path)
    generated_pairs = ['|'.join(sorted(normalize_lines(cue.lines))) for cue in generated]
    reference_pairs = ['|'.join(sorted(normalize_lines(cue.lines))) for cue in reference]
    return {
        'generated_file': str(generated_path),
        'reference_file': str(reference_path),
        'generated_cues': len(generated),
        'reference_cues': len(reference),
        'pair_similarity': round(similarity(''.join(generated_pairs), ''.join(reference_pairs)), 4),
        'generated_midpoint_hit_rate': round(midpoint_hits(generated, reference), 4),
        'reference_midpoint_hit_rate': round(midpoint_hits(reference, generated), 4),
        'first_generated': generated[0].text if generated else '',
        'first_reference': reference[0].text if reference else '',
    }


def write_srt(cues: list[Cue], texts: list[str], path: Path) -> None:
    with path.open('w', encoding='utf-8') as handle:
        for index, (cue, text) in enumerate(zip(cues, texts), 1):
            handle.write(f'{index}\n{format_time(cue.start)} --> {format_time(cue.end)}\n{text}\n\n')


def write_bilingual_srt(cues: list[Cue], top_texts: list[str], bottom_texts: list[str], path: Path) -> None:
    with path.open('w', encoding='utf-8') as handle:
        for index, (cue, top, bottom) in enumerate(zip(cues, top_texts, bottom_texts), 1):
            handle.write(f'{index}\n{format_time(cue.start)} --> {format_time(cue.end)}\n{top}\n{bottom}\n\n')


def build_prompt(cues: list[Cue]) -> str:
    numbered_lines = []
    for index, cue in enumerate(cues, 1):
        text = cue.text.replace('\n', ' / ').strip()
        numbered_lines.append(f'{index}\t{text}')
    joined = '\n'.join(numbered_lines)
    return (
        'Translate the following Japanese subtitle lines into concise, natural Simplified Chinese subtitles.\n'
        'Rules:\n'
        '1. Keep exactly the same number of items as the input.\n'
        '2. Output only plain text lines in the format: <index><TAB><translation>.\n'
        '3. One output line per input item.\n'
        '4. Do not merge, omit, reorder, or explain any item.\n'
        '5. Do not output markdown, JSON, code fences, or thinking.\n'
        '6. Continue until the final item is translated; do not stop early.\n'
        '7. If a line is hard to translate, still output a concise Chinese subtitle for that line instead of skipping it.\n\n'
        f'Input lines ({len(cues)} items):\n{joined}\n\n'
        'Output lines:\n'
    )


def estimate_max_tokens(cues: list[Cue]) -> int:
    total_chars = sum(len(cue.text) for cue in cues)
    estimated = int(total_chars * 1.6) + len(cues) * 24
    return max(256, min(4096, estimated))


def strip_thinking(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^```[a-zA-Z0-9_-]*\n', '', text.strip())
    text = re.sub(r'\n```$', '', text.strip())
    return text.strip()


def dump_raw_response(content: str, expected_count: int) -> None:
    RAW_DUMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    target = RAW_DUMP_DIR / f'minimax_raw_{expected_count}_{stamp}.txt'
    target.write_text(content, encoding='utf-8')


def build_windows(cues: list[Cue], max_items: int, max_chars: int) -> list[list[Cue]]:
    windows = []
    current = []
    current_chars = 0
    for cue in cues:
        estimated_chars = len(cue.text or '') + 12
        should_flush = current and (
            len(current) >= max_items or current_chars + estimated_chars > max_chars
        )
        if should_flush:
            windows.append(current)
            current = []
            current_chars = 0
        current.append(cue)
        current_chars += estimated_chars
    if current:
        windows.append(current)
    return windows


def request_translation_window(cues: list[Cue], api_key: str) -> tuple[list[str], dict]:
    req_data = {
        'model': MINIMAX_MODEL,
        'messages': [
            {
                'role': 'system',
                'content': 'You are a professional subtitle translator. Translate Japanese subtitles into concise natural Simplified Chinese. Never include reasoning or markup.',
            },
            {
                'role': 'user',
                'content': build_prompt(cues),
            },
        ],
        'stream': False,
        'temperature': 0.0,
        'max_tokens': estimate_max_tokens(cues),
    }
    request = urllib.request.Request(
        MINIMAX_CHAT_URL,
        data=json.dumps(req_data).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'MiniMax HTTP {exc.code}: {body[:800]}') from exc
    except Exception as exc:
        raise RuntimeError(f'MiniMax request failed: {exc}') from exc

    content = payload.get('choices', [{}])[0].get('message', {}).get('content', '')
    cleaned = strip_thinking(content)
    try:
        parsed = parse_translation_lines(cleaned, len(cues))
    except Exception:
        dump_raw_response(cleaned, len(cues))
        raise
    meta = {
        'seconds': round(time.monotonic() - started, 3),
        'max_tokens': req_data['max_tokens'],
        'usage': payload.get('usage', {}),
        'model': payload.get('model', MINIMAX_MODEL),
        'input_items': len(cues),
    }
    return parsed, meta


def parse_translation_lines(text: str, expected_count: int) -> list[str]:
    raw_lines = []
    items = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in {'output translated subtitles only:', 'translated subtitles only:', 'output lines:'}:
            continue
        raw_lines.append(line)
        match = re.match(r'^(\d+)\s*[\t：:、.\-]\s*(.+)$', line)
        if not match and '\t' in line:
            prefix, rest = line.split('\t', 1)
            if prefix.strip().isdigit():
                match = re.match(r'^(\d+)$', prefix.strip())
                if match:
                    items[int(match.group(1))] = rest.strip()
                    continue
        if not match:
            continue
        index = int(match.group(1))
        value = match.group(2).strip()
        if value:
            items[index] = value

    if len(items) == 0 and len(raw_lines) == expected_count:
        return raw_lines

    translations = []
    missing = []
    for index in range(1, expected_count + 1):
        value = items.get(index, '')
        if value:
            translations.append(value)
        else:
            translations.append(f'[翻译失败] #{index}')
            missing.append(index)

    if len(missing) > max(2, expected_count // 10):
        preview = ', '.join(map(str, missing[:12]))
        raise RuntimeError(f'MiniMax response missing {len(missing)} items, examples: {preview}')
    return translations


def translate_cues_windowed(cues: list[Cue], api_key: str, max_items: int, max_chars: int) -> tuple[list[str], dict]:
    windows = build_windows(cues, max_items=max_items, max_chars=max_chars)
    translations = []
    window_reports = []
    started = time.monotonic()
    for window_index, window in enumerate(windows, 1):
        window_translations, meta = request_translation_window(window, api_key)
        translations.extend(window_translations)
        meta['window_index'] = window_index
        window_reports.append(meta)
    report = {
        'seconds': round(time.monotonic() - started, 3),
        'window_count': len(windows),
        'max_items': max_items,
        'max_chars': max_chars,
        'windows': window_reports,
    }
    return translations, report


def load_baselines() -> dict:
    if not BASELINE_REPORT_PATH.exists():
        return {}
    data = json.loads(BASELINE_REPORT_PATH.read_text(encoding='utf-8'))
    baselines = {}
    for video in data.get('videos', []):
        baselines[Path(video['video']).stem] = video.get('comparisons', {})
    return baselines


def build_comparisons(video_entry: dict, baselines: dict) -> dict:
    comparisons = {}
    if video_entry['references'].get('translated_vs_zh') and video_entry['translated'].exists():
        comparisons['translated_vs_zh'] = compare_mono(video_entry['translated'], video_entry['references']['translated_vs_zh'])
    if video_entry['references'].get('translated_vs_zh_traditional') and video_entry['translated'].exists():
        comparisons['translated_vs_zh_traditional'] = compare_mono(video_entry['translated'], video_entry['references']['translated_vs_zh_traditional'])
    if video_entry['references'].get('bilingual_vs_mul') and video_entry['bilingual'].exists():
        comparisons['bilingual_vs_mul'] = compare_bilingual(video_entry['bilingual'], video_entry['references']['bilingual_vs_mul'])

    baseline = baselines.get(video_entry['source'].stem.replace('_ja', ''), {})
    for key, payload in comparisons.items():
        if key in baseline:
            baseline_payload = baseline[key]
            delta = {}
            if 'text_similarity' in payload and 'text_similarity' in baseline_payload:
                delta['text_similarity'] = round(payload['text_similarity'] - baseline_payload['text_similarity'], 4)
            if 'pair_similarity' in payload and 'pair_similarity' in baseline_payload:
                delta['pair_similarity'] = round(payload['pair_similarity'] - baseline_payload['pair_similarity'], 4)
            if 'generated_midpoint_hit_rate' in payload and 'generated_midpoint_hit_rate' in baseline_payload:
                delta['generated_midpoint_hit_rate'] = round(payload['generated_midpoint_hit_rate'] - baseline_payload['generated_midpoint_hit_rate'], 4)
            if delta:
                payload['delta_vs_qwen_batch'] = delta
    return comparisons


def select_videos(args) -> list[dict]:
    if not args.video:
        return VIDEOS
    filtered = [video for video in VIDEOS if args.video.lower() in str(video['source']).lower()]
    if not filtered:
        raise RuntimeError(f'No video matched filter: {args.video}')
    return filtered


def main() -> None:
    args = parse_args()
    api_key = load_minimax_api_key()
    baselines = load_baselines()
    report = {
        'provider': 'minimax',
        'model': MINIMAX_MODEL,
        'mode': 'windowed-bulk-from-generated-ja-srt',
        'started_at': time.time(),
        'max_items': args.max_items,
        'max_chars': args.max_chars,
        'videos': [],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    for video in select_videos(args):
        cues = parse_srt(video['source'])
        if args.limit:
            cues = cues[:args.limit]
        state = {
            'source_file': str(video['source']),
            'translated_file': str(video['translated']),
            'bilingual_file': str(video['bilingual']),
            'input_cues': len(cues),
            'status': 'running',
        }
        report['videos'].append(state)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

        translated, meta = translate_cues_windowed(cues, api_key, max_items=args.max_items, max_chars=args.max_chars)
        write_srt(cues, translated, video['translated'])
        write_bilingual_srt(cues, [cue.text for cue in cues], translated, video['bilingual'])

        state['status'] = 'completed'
        state['request'] = meta
        state['comparisons'] = build_comparisons(video, baselines)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'source_file': state['source_file'],
            'request': meta,
            'comparisons': state['comparisons'],
        }, ensure_ascii=False, indent=2), flush=True)

    report['completed_at'] = time.time()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'REPORT_PATH={REPORT_PATH}', flush=True)


if __name__ == '__main__':
    main()