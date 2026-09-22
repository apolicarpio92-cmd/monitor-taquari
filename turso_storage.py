from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import libsql


BASE_DIR = Path(__file__).resolve().parent

ARQUIVOS_PERSISTENTES = [
    BASE_DIR / "historico" / "telemetria_historico.csv",
    BASE_DIR / "historico" / "barragens_historico.csv",
    BASE_DIR / "dados" / "status.json",
]


def turso_configurado():
    return bool(
        os.environ.get("TURSO_DATABASE_URL")
        and os.environ.get("TURSO_AUTH_TOKEN")
    )


def conectar():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    if not url or not token:
        raise RuntimeError(
            "TURSO_DATABASE_URL ou TURSO_AUTH_TOKEN ausente."
        )

    return libsql.connect(
        str(BASE_DIR / "monitor_turso_cache.db"),
        sync_url=url,
        auth_token=token,
    )


def criar_tabela():
    conn = conectar()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_arquivos (
                nome TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )

        conn.commit()
        conn.sync()

    finally:
        conn.close()


def inicializar():
    if not turso_configurado():
        print(
            "[TURSO] Credenciais nao configuradas.",
            flush=True,
        )
        return False

    criar_tabela()

    print(
        "[TURSO] Banco inicializado.",
        flush=True,
    )

    return True


def salvar_no_turso():
    if not turso_configurado():
        return False

    conn = conectar()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_arquivos (
                nome TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )

        agora = datetime.now().isoformat(
            timespec="seconds"
        )

        total = 0

        for arquivo in ARQUIVOS_PERSISTENTES:
            if not arquivo.exists():
                continue

            conteudo = arquivo.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )

            nome = str(
                arquivo.relative_to(BASE_DIR)
            ).replace(
                "\\",
                "/",
            )

            conn.execute(
                """
                INSERT INTO monitor_arquivos
                    (
                        nome,
                        conteudo,
                        atualizado_em
                    )
                VALUES (?, ?, ?)

                ON CONFLICT(nome)
                DO UPDATE SET
                    conteudo = excluded.conteudo,
                    atualizado_em = excluded.atualizado_em
                """,
                (
                    nome,
                    conteudo,
                    agora,
                ),
            )

            total += 1

        conn.commit()
        conn.sync()

        print(
            f"[TURSO] {total} arquivo(s) sincronizado(s).",
            flush=True,
        )

        return True

    finally:
        conn.close()


def restaurar_do_turso():
    if not turso_configurado():
        return False

    conn = conectar()

    try:
        conn.sync()

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_arquivos (
                nome TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )

        conn.commit()

        rows = conn.execute(
            """
            SELECT
                nome,
                conteudo
            FROM monitor_arquivos
            """
        ).fetchall()

        total = 0

        for nome, conteudo in rows:
            destino = BASE_DIR / Path(nome)

            destino.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            destino.write_text(
                conteudo,
                encoding="utf-8",
            )

            total += 1

        print(
            f"[TURSO] {total} arquivo(s) restaurado(s).",
            flush=True,
        )

        return True

    finally:
        conn.close()
