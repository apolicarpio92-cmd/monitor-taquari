from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import turso_serverless


BASE = Path(__file__).resolve().parent

ARQUIVOS = [
    BASE / "historico" / "telemetria_historico.csv",
    BASE / "historico" / "barragens_historico.csv",
    BASE / "dados" / "status.json",
]


def configurado():

    return bool(
        os.environ.get("TURSO_DATABASE_URL")
        and os.environ.get("TURSO_AUTH_TOKEN")
    )


def conectar():

    url = os.environ.get(
        "TURSO_DATABASE_URL"
    )

    token = os.environ.get(
        "TURSO_AUTH_TOKEN"
    )

    if not url or not token:

        raise RuntimeError(
            "TURSO_DATABASE_URL / TURSO_AUTH_TOKEN "
            "nao configurados."
        )

    return turso_serverless.connect(
        url,
        auth_token=token,
    )


def inicializar():

    if not configurado():

        print(
            "[TURSO] Credenciais nao configuradas.",
            flush=True
        )

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

        conn.commit()

        print(
            "[TURSO] Banco inicializado.",
            flush=True
        )

        return True

    finally:

        conn.close()


def salvar_no_turso():

    if not configurado():
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

        agora = datetime.now().isoformat()

        quantidade = 0

        for arquivo in ARQUIVOS:

            if not arquivo.exists():
                continue

            conteudo = arquivo.read_text(
                encoding="utf-8-sig"
            )

            nome = str(
                arquivo.relative_to(BASE)
            ).replace(
                "\\",
                "/"
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
                )
            )

            quantidade += 1

        conn.commit()

        print(
            f"[TURSO] {quantidade} arquivo(s) "
            "sincronizado(s).",
            flush=True
        )

        return True

    finally:

        conn.close()


def restaurar_do_turso():

    if not configurado():

        print(
            "[TURSO] Sem credenciais. "
            "Restauracao ignorada.",
            flush=True
        )

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

        conn.commit()

        rows = conn.execute(
            """
            SELECT
                nome,
                conteudo,
                atualizado_em
            FROM monitor_arquivos
            """
        ).fetchall()

        if not rows:

            print(
                "[TURSO] Banco ainda sem historico.",
                flush=True
            )

            return True

        quantidade = 0

        for row in rows:

            nome = row[0]
            conteudo = row[1]

            destino = (
                BASE
                / Path(nome)
            )

            destino.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            destino.write_text(
                conteudo,
                encoding="utf-8"
            )

            quantidade += 1

        print(
            f"[TURSO] {quantidade} arquivo(s) "
            "restaurado(s).",
            flush=True
        )

        return True

    finally:

        conn.close()
