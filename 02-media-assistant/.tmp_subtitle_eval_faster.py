import asyncio
import json
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from config import load_config, save_config, get_whisper_backend


VIDEO_DIR = Path('/Volumes/扩展盘512G/video test')
VIDEOS = [
    VIDEO_DIR / 'Ginga.no.Ippyo.S01E01.1080p.friDay.WEB-DL.AAC2.0.H.264-MWeb.mkv',
    VIDEO_DIR / 'Hanzawa.Naoki.S02E05.2020.HDTV.1080p.x265.10bit-Yumi.mkv',
]
REPORT_PATH = Path('/tmp/media_subtitle_eval_faster_report.json')


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str
    lines: list[str]


TIME_RE = re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)')


def parse_ts(ts: str) -> float:
    match = TIME_RE.match(ts.strip())
    if not match:
        raise ValueError(f'bad timestamp: {ts}')
    hour, minute, second, millis = map(int, match.groups())
    if len(match.group(4)) == 2:
        millis *= 10
    return hour * 3600 + minute * 60 + second + millis / 1000


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


def build_comparisons(video_path: Path, results: dict) -> dict:
    stem = video_path.stem
    refs = {}
    if video_path.name.startswith('Ginga.no.Ippyo'):
        refs['source_jpn'] = VIDEO_DIR / f'{stem}.jpn.srt'
        refs['translated_zh'] = VIDEO_DIR / f'{stem}.chi.Simplified.srt'
        refs['translated_zh_traditional'] = VIDEO_DIR / f'{stem}.chi.Traditional.srt'
        refs['bilingual_mul'] = VIDEO_DIR / f'{stem}.mul.srt'
    elif video_path.name.startswith('Hanzawa.Naoki'):
        refs['translated_zh'] = VIDEO_DIR / f'{stem}.chi.srt'

    comparisons = {}
    if refs.get('source_jpn') and refs['source_jpn'].exists() and results.get('source'):
        comparisons['source_vs_jpn'] = compare_mono(Path(results['source']), refs['source_jpn'])
    if refs.get('translated_zh') and refs['translated_zh'].exists() and results.get('translated'):
        comparisons['translated_vs_zh'] = compare_mono(Path(results['translated']), refs['translated_zh'])
    if refs.get('translated_zh_traditional') and refs['translated_zh_traditional'].exists() and results.get('translated'):
        comparisons['translated_vs_zh_traditional'] = compare_mono(Path(results['translated']), refs['translated_zh_traditional'])
    if refs.get('bilingual_mul') and refs['bilingual_mul'].exists() and results.get('bilingual'):
        comparisons['bilingual_vs_mul'] = compare_bilingual(Path(results['bilingual']), refs['bilingual_mul'])
    return comparisons


class DummyRequest:
    def __init__(self, payload: dict | None = None):
        self._payload = json.dumps(payload or {}).encode('utf-8') if payload is not None else b''

    async def body(self):
        return self._payload


def write_report(report: dict) -> None:
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


async def process_video(app_module, video_path: Path, report: dict) -> dict:
    video_state = {
        'video': str(video_path),
        'status': 'starting',
        'detected_lang': None,
        'source_segments': None,
        'translated_segments': None,
        'results': {},
        'timings': {},
        'comparisons': {},
    }
    report['videos'].append(video_state)
    write_report(report)

    init = await app_module.local_file({
        'path': str(video_path),
        'source_lang': 'auto',
        'target_lang': 'zh',
        'mode': 'translate',
        'enable_frames': False,
    })
    if 'error' in init:
        raise RuntimeError(init['error'])

    task_id = init['task_id']
    task = app_module.tasks[task_id]
    video_state['task_id'] = task_id
    video_state['status'] = 'running'
    write_report(report)

    steps = [
        ('audio', app_module.step_audio, (task_id,)),
        ('transcribe', app_module.step_transcribe, (task_id,)),
        ('translate', app_module.step_translate, (task_id, DummyRequest())),
        ('subtitle', app_module.step_subtitle, (task_id,)),
    ]
    for step_name, step_func, args in steps:
        video_state['current_step'] = step_name
        video_state['step_started_at'] = time.time()
        write_report(report)

        started = time.monotonic()
        result = await step_func(*args)
        video_state['timings'][step_name] = {
            'seconds': round(time.monotonic() - started, 3),
            'result': result,
        }
        video_state['detected_lang'] = task.get('detected_lang')
        video_state['source_segments'] = len(task.get('source_texts') or [])
        video_state['translated_segments'] = len(task.get('translated_texts') or [])
        video_state['results'] = task.get('results', {})
        write_report(report)

        if isinstance(result, dict) and result.get('error'):
            video_state['status'] = 'error'
            video_state['error'] = result['error']
            write_report(report)
            raise RuntimeError(f'{video_path.name} {step_name} failed: {result["error"]}')

    video_state['comparisons'] = build_comparisons(video_path, video_state['results'])
    video_state['status'] = 'completed'
    video_state.pop('current_step', None)
    video_state.pop('step_started_at', None)
    write_report(report)
    return video_state


async def main():
    original_config = load_config()
    temp_config = json.loads(json.dumps(original_config))
    temp_config['whisper']['backend'] = 'faster-whisper'
    temp_config['whisper']['model_path'] = 'bundled'
    temp_config['whisper']['device'] = 'auto'
    temp_config['whisper']['compute_type'] = 'auto'
    save_config(temp_config)

    report = {
        'backend': get_whisper_backend(),
        'started_at': time.time(),
        'videos': [],
    }
    write_report(report)

    try:
        import video_subtitle_app as app_module

        print(f'ACTIVE_BACKEND={get_whisper_backend()}', flush=True)
        for video_path in VIDEOS:
            print(f'PROCESSING {video_path.name}', flush=True)
            video_state = await process_video(app_module, video_path, report)
            print(json.dumps({'video': video_state['video'], 'timings': video_state['timings'], 'comparisons': video_state['comparisons']}, ensure_ascii=False, indent=2), flush=True)

        report['completed_at'] = time.time()
        write_report(report)
        print(f'REPORT_PATH={REPORT_PATH}', flush=True)
    finally:
        save_config(original_config)


if __name__ == '__main__':
    asyncio.run(main())
