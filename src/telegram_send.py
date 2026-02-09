#!/usr/bin/env python3
"""
Скрипт мини-интеграции с Telegram: читает текст из .txt-файла
и отправляет его в указанный приватный чат через бота.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv


TELEGRAM_API_BASE = "https://api.telegram.org"
ENV_PATH_VAR = "TELEGRAM_SEND_ENV"


def load_config(env_path: Optional[Path] = None) -> tuple[str, str]:
    """
    Загружает BOT_TOKEN и CHAT_ID из .env.
    Путь к .env: env_path или TELEGRAM_SEND_ENV, иначе .env в корне проекта.
    """
    if env_path is None:
        env_path = os.environ.get(ENV_PATH_VAR)
        if env_path:
            env_path = Path(env_path)
        else:
            # Корень проекта — на уровень выше src/
            env_path = Path(__file__).resolve().parents[1] / ".env"

    load_dotenv(env_path, override=True)

    token = (os.environ.get("BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("CHAT_ID") or "").strip()

    if not token:
        print("Ошибка: не задан BOT_TOKEN (в .env или окружении).", file=sys.stderr)
        sys.exit(1)
    if not chat_id:
        print("Ошибка: не задан CHAT_ID (в .env или окружении).", file=sys.stderr)
        sys.exit(1)

    return token, chat_id


def read_message_file(file_path: Path, encoding: str = "utf-8") -> str:
    """
    Читает содержимое текстового файла в заданной кодировке.
    При ошибке выводит сообщение в stderr и завершает процесс с ненулевым кодом.
    """
    if not file_path.is_file():
        print(f"Ошибка: файл не найден: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        return file_path.read_text(encoding=encoding)
    except UnicodeDecodeError as e:
        print(f"Ошибка кодировки при чтении {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


def send_to_telegram(
    token: str,
    chat_id: str,
    text: str,
    timeout: float = 30.0,
) -> None:
    """
    Отправляет текст в чат через Telegram Bot API (sendMessage).
    При ошибке API или сети выводит сообщение в stderr и завершает с ненулевым кодом.
    """
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as e:
        print(f"Ошибка сети при отправке в Telegram: {e}", file=sys.stderr)
        sys.exit(1)

    if not resp.ok:
        print(
            f"Ошибка Telegram API (HTTP {resp.status_code}): {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    data = resp.json()
    if not data.get("ok"):
        desc = data.get("description", resp.text)
        print(f"Ошибка Telegram API: {desc}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов CLI."""
    parser = argparse.ArgumentParser(
        description="Отправка текста из .txt-файла в приватный Telegram-чат через бота.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Путь к .txt-файлу с текстом сообщения.",
    )
    parser.add_argument(
        "--chat-id",
        type=str,
        default=None,
        help="Переопределить CHAT_ID из .env (опционально).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Таймаут запроса к API в секундах (по умолчанию 30).",
    )
    return parser


def main() -> int:
    """Точка входа: загрузка конфига, чтение файла, отправка."""
    parser = build_parser()
    args = parser.parse_args()

    token, chat_id_from_env = load_config()
    chat_id = (args.chat_id or chat_id_from_env).strip()
    if not chat_id:
        print("Ошибка: CHAT_ID не задан (ни в .env, ни в --chat-id).", file=sys.stderr)
        return 1

    text = read_message_file(args.file)
    send_to_telegram(token, chat_id, text, timeout=args.timeout)

    print("Сообщение успешно отправлено в Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
