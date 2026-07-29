"""JSON stdout logging for typed operational signals."""

from __future__ import annotations

import json
from typing import TextIO

from umbral.application.runtime.telemetry import TelemetrySignal


class JsonTelemetryLogger:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def emit(self, signal: TelemetrySignal) -> None:
        self._stream.write(json.dumps(signal.attributes(), separators=(",", ":")) + "\n")
