"""合成 4 个答题音效（原创、无版权问题、不依赖第三方库）。

用法（在 backend 目录下）：
    .\\.venv\\Scripts\\python.exe scripts\\generate_sounds.py

生成到 frontend/src/assets/sounds/：
    right.wav   答对：木琴感清脆单音
    wrong.wav   答错：柔和的「噗」声（不是刺耳失败音）
    combo.wav   连对 3 题：三音上行
    finish.wav  通关：五音短旋律

设计依据（《UI设计风格方案》第 9.3 节）：
- 答对用木琴/马林巴的清脆单音；答错用柔和「噗」声，绝不用蜂鸣器式失败音；
- 音量低于系统媒体音量（我们统一把峰值压到 0.6），学习场景不该吓到用户。
"""

from __future__ import annotations

import math
import random
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 22050
PEAK = 0.6  # 统一峰值（低于系统媒体音量）
OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets" / "sounds"


def marimba_tone(freq: float, duration: float, *, tau: float = 0.09, amp: float = 1.0) -> list[float]:
    """木琴音色：基频 + 第 4 分音（马林巴的标志性音色），指数衰减。"""
    samples: list[float] = []
    count = int(SAMPLE_RATE * duration)
    for index in range(count):
        t = index / SAMPLE_RATE
        body = math.sin(2 * math.pi * freq * t)
        overtone = 0.35 * math.sin(2 * math.pi * freq * 4 * t) * math.exp(-t / (tau * 0.5))
        samples.append((body + overtone) * math.exp(-t / tau) * amp)
    return samples


def puff(duration: float = 0.28, *, amp: float = 1.0) -> list[float]:
    """柔和「噗」声：低通噪声 + 低频闷响，刻意去掉刺耳的高频。"""
    rnd = random.Random(42)
    low_pass = 0.0
    samples: list[float] = []
    count = int(SAMPLE_RATE * duration)
    for index in range(count):
        t = index / SAMPLE_RATE
        white = rnd.uniform(-1, 1)
        low_pass += 0.06 * (white - low_pass)  # 一阶低通：削掉尖锐成分
        thud = math.sin(2 * math.pi * 150 * t) * 0.5
        samples.append((low_pass * 2.2 + thud) * math.exp(-t / 0.06) * amp)
    return samples


def mix_into(buffer: list[float], samples: list[float], offset_seconds: float) -> None:
    start = int(SAMPLE_RATE * offset_seconds)
    for index, value in enumerate(samples):
        position = start + index
        if position >= len(buffer):
            break
        buffer[position] += value


def finalize(buffer: list[float]) -> list[float]:
    """统一峰值 + 首尾淡入淡出（避免爆音）。"""
    peak = max((abs(value) for value in buffer), default=0.0) or 1.0
    scaled = [value / peak * PEAK for value in buffer]
    fade = int(SAMPLE_RATE * 0.005)  # 5ms
    for index in range(min(fade, len(scaled))):
        factor = index / fade
        scaled[index] *= factor
        scaled[-1 - index] *= factor
    return scaled


def write_wav(path: Path, samples: list[float]) -> None:
    data = array("h", (int(max(-1.0, min(1.0, value)) * 32767) for value in samples))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(data.tobytes())


def build_right() -> list[float]:
    return finalize(marimba_tone(1046.5, 0.45))  # C6


def build_wrong() -> list[float]:
    return finalize(puff(0.3))


def build_combo() -> list[float]:
    buffer = [0.0] * int(SAMPLE_RATE * 0.6)
    for offset, freq in ((0.0, 1046.5), (0.11, 1318.5), (0.22, 1568.0)):
        mix_into(buffer, marimba_tone(freq, 0.35), offset)
    return finalize(buffer)


def build_finish() -> list[float]:
    buffer = [0.0] * int(SAMPLE_RATE * 1.5)
    melody = ((0.0, 1046.5), (0.16, 1318.5), (0.32, 1568.0), (0.48, 2093.0), (0.68, 1568.0))
    for offset, freq in melody:
        mix_into(buffer, marimba_tone(freq, 0.6, tau=0.16), offset)
    # 收尾加一个柔和的和弦，让"通关"有完整感
    mix_into(buffer, marimba_tone(2093.0, 0.7, tau=0.22, amp=0.5), 0.9)
    mix_into(buffer, marimba_tone(1046.5, 0.7, tau=0.22, amp=0.5), 0.9)
    return finalize(buffer)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    builders = {
        "right.wav": build_right,
        "wrong.wav": build_wrong,
        "combo.wav": build_combo,
        "finish.wav": build_finish,
    }
    for name, builder in builders.items():
        path = OUT_DIR / name
        write_wav(path, builder())
        print(f"[生成] {name}  {path.stat().st_size / 1024:.1f} KB")
    print(f"[完成] 输出目录：{OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
