#!/usr/bin/env python3
"""
Скрипт для проверки доменов email-адресов:
- наличие MX-записей;
- best-effort SMTP-handshake для проверки существования пользователя.
"""

from __future__ import annotations

import argparse
import re
import smtplib
import socket
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import dns.resolver


STATUS_DOMAIN_VALID = "домен валиден"
STATUS_DOMAIN_ABSENT = "домен отсутствует"
STATUS_MX_INVALID = "MX-записи отсутствуют или некорректны"
# Уточнения к «домен валиден» по результату SMTP-handshake (проверка существования пользователя)
SMTP_USER_OK = "пользователь подтверждён по SMTP"
SMTP_USER_REJECTED = "пользователь не найден по SMTP"
SMTP_UNAVAILABLE = "SMTP-проверка недоступна"


@dataclass(frozen=True)
class MxRecord:
    """Структура для хранения MX-записи с приоритетом и хостом."""

    preference: int
    host: str


def parse_email(email: str) -> Optional[str]:
    """Базовая проверка email и извлечение домена."""

    email = email.strip()
    if not email:
        return None

    # Упрощённая проверка формата: локальная часть@домен.
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return None

    _, domain = email.split("@", 1)
    return domain.lower()


# Публичные DNS для надёжного разрешения MX (системный DNS в Windows часто даёт сбои).
DEFAULT_NAMESERVERS = ["8.8.8.8", "8.8.4.4"]


def resolve_mx_records(
    domain: str,
    timeout: float,
) -> Tuple[Optional[List[MxRecord]], Optional[str]]:
    """
    Получает MX-записи домена.
    Возвращает (список MX или None) и код ошибки при отсутствии домена.
    Использует публичные DNS, чтобы не зависеть от настроек системы.
    """

    resolver = dns.resolver.Resolver()
    resolver.nameservers = DEFAULT_NAMESERVERS
    resolver.timeout = timeout
    resolver.lifetime = timeout * 2  # общее время попыток больше одного таймаута

    try:
        answers = resolver.resolve(domain, "MX")
    except dns.resolver.NXDOMAIN:
        return None, "NXDOMAIN"
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return [], None
    except dns.resolver.LifetimeTimeout:
        return [], None
    except dns.exception.DNSException:
        return [], None

    records: List[MxRecord] = []
    for record in answers:
        host = str(record.exchange).rstrip(".")
        records.append(MxRecord(preference=record.preference, host=host))

    records.sort(key=lambda item: item.preference)
    return records, None


def smtp_check_user(
    email: str,
    mx_hosts: Iterable[str],
    timeout: float,
) -> Optional[bool]:
    """
    Best-effort SMTP-handshake.
    Возвращает:
      - True, если сервер подтвердил адрес;
      - False, если сервер явно отверг адрес;
      - None, если результат неопределён (ошибка/блокировка/таймаут).
    """

    from_address = "check@local.invalid"
    result: Optional[bool] = None

    for host in mx_hosts:
        try:
            with smtplib.SMTP(host=host, port=25, timeout=timeout) as server:
                server.ehlo_or_helo_if_needed()

                # MAIL FROM нужен для корректного SMTP-диалога.
                server.mail(from_address)
                code, _ = server.rcpt(email)

                if code in (250, 251, 252):
                    return True
                if code in (550, 551, 553, 554):
                    result = False
                    continue

                result = None
        except (smtplib.SMTPException, socket.timeout, OSError):
            continue

    return result


def check_email_domain(email: str, timeout: float) -> str:
    """Проверяет домен email и возвращает итоговый статус."""

    domain = parse_email(email)
    if not domain:
        return STATUS_DOMAIN_ABSENT

    mx_records, error = resolve_mx_records(domain, timeout)
    if error == "NXDOMAIN":
        return STATUS_DOMAIN_ABSENT

    if not mx_records:
        return STATUS_MX_INVALID

    mx_hosts = [record.host for record in mx_records]
    # SMTP-handshake: проверка существования пользователя без отправки письма
    smtp_result = smtp_check_user(email, mx_hosts, timeout)
    if smtp_result is True:
        return f"{STATUS_DOMAIN_VALID} ({SMTP_USER_OK})"
    if smtp_result is False:
        return f"{STATUS_DOMAIN_VALID} ({SMTP_USER_REJECTED})"
    return f"{STATUS_DOMAIN_VALID} ({SMTP_UNAVAILABLE})"


def build_parser() -> argparse.ArgumentParser:
    """Создаёт CLI-парсер для аргументов."""

    parser = argparse.ArgumentParser(
        description="Проверка MX-записей домена и SMTP-handshake.",
    )
    parser.add_argument(
        "emails",
        nargs="+",
        help="Список email-адресов для проверки.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Таймаут в секундах для DNS и SMTP (по умолчанию 5).",
    )
    return parser


def main() -> int:
    """Точка входа в CLI-приложение."""

    parser = build_parser()
    args = parser.parse_args()

    for email in args.emails:
        status = check_email_domain(email, args.timeout)
        print(f"{email}: {status}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
