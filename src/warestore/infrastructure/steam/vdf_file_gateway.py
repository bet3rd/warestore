# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import vdf


class VdfFileGateway:
    def detect_encoding(self, file_path: str) -> str:
        try:
            import chardet

            with open(file_path, "rb") as f:
                raw = f.read(8192)
            return chardet.detect(raw).get("encoding") or "utf-8"
        except Exception:
            return "utf-8"

    def read_text(self, file_path: str) -> str:
        with open(file_path, encoding=self.detect_encoding(file_path), errors="replace") as f:
            return f.read()

    def write_text(self, file_path: str, text: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

    def read_vdf(self, file_path: str) -> dict:
        with open(file_path, encoding=self.detect_encoding(file_path), errors="replace") as f:
            return vdf.loads(f.read())

    def write_vdf(self, file_path: str, data: dict) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(vdf.dumps(data, pretty=True))
