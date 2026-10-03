"""文档读取与分块。

分块策略刻意做成"按标题优先、超长再滑窗"，因为场景类知识库多为
分条目的规范/手册，按语义段落切开比固定长度切效果更好，
这一点在方案书"技术路线"里是可以写出来的设计依据。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from app.schemas import Chunk

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".pdf"}


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return _read_text_file(path)
    if suffix == ".csv":
        rows = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                rows.append(" | ".join(cell.strip() for cell in row))
        return "\n".join(rows)
    if suffix == ".json":
        payload = json.loads(_read_text_file(path))
        return json.dumps(payload, ensure_ascii=False, indent=2)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - 取决于环境
            raise RuntimeError(
                f"解析 PDF 需要 pypdf，请先执行 pip install pypdf（文件：{path.name}）"
            ) from exc
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    raise RuntimeError(f"不支持的格式：{suffix}（{path.name}）")


def list_documents(kb_dir: Path) -> list[Path]:
    if not kb_dir.exists():
        return []
    files = [
        p
        for p in sorted(kb_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and p.name != "README.md"
    ]
    return files


def _split_by_heading(text: str) -> list[str]:
    """按 Markdown 标题切段，保留标题作为上下文。"""
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^#{1,6}\s+", line) and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    step = max(1, size - overlap)
    return [
        text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()
    ]


def _split_long_block(block: str, size: int, overlap: int) -> list[str]:
    """先按空行分段，段落仍超长时再滑窗。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", block) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) > size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_sliding_window(paragraph, size, overlap))
            continue
        if len(buffer) + len(paragraph) + 2 <= size:
            buffer = f"{buffer}\n\n{paragraph}".strip()
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph
    if buffer:
        chunks.append(buffer)
    return chunks


def chunk_document(path: Path, kb_root: Path, size: int, overlap: int) -> list[Chunk]:
    text = read_document(path)
    if not text.strip():
        return []
    relative = str(path.relative_to(kb_root)).replace("\\", "/")
    doc_id = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:12]
    chunks: list[Chunk] = []
    ordinal = 0
    for block in _split_by_heading(text):
        for piece in _split_long_block(block, size, overlap):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}-{ordinal:03d}",
                    doc_id=doc_id,
                    doc_title=path.stem,
                    source=relative,
                    text=piece,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    return chunks


def build_chunks(kb_dir: Path, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in list_documents(kb_dir):
        chunks.extend(chunk_document(path, kb_dir, size, overlap))
    return chunks
