from __future__ import annotations

import os
from datetime import datetime

import libsql


# ============================================================
# TURSO
# ============================================================

TURSO_DATABASE_URL = os.getenv(
    "TURSO_DATABASE_URL",
    ""
).strip()

TURSO_AUTH_TOKEN = os.getenv(
    "TURSO_AUTH_TOKEN",
    ""
).strip()


def configurado():

    return bool(
        TURSO_DATABASE_URL
        and TURSO_AUTH_TOKEN
    )


def conectar():

    if not configurado():
        return None

    return libsql.connect(
        database=TURSO_DATABASE_URL,
        auth_token=TURSO_AUTH_TOKEN,
    )


def garantir_tabela(conn):

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_runtime_status (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            atualizado_em TEXT
        )
        """
    )

    conn.commit()


# ============================================================
# SALVAR
# ============================================================

def salvar_status_runtime(
    chave,
    valor,
):

    if not configurado():
        return False

    conn = None

    try:

        conn = conectar()

        if conn is None:
            return False

        garantir_tabela(
            conn
        )

        atualizado_em = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO
                monitor_runtime_status
                (
                    chave,
                    valor,
                    atualizado_em
                )
            VALUES (?, ?, ?)
            """,
            (
                str(chave),
                str(valor),
                atualizado_em,
            ),
        )

        conn.commit()

        return True

    except Exception as e:

        print(
            "[RUNTIME/TURSO] "
            "Erro ao salvar status:",
            e,
            flush=True,
        )

        return False

    finally:

        if conn is not None:

            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# CARREGAR
# ============================================================

def carregar_status_runtime(
    chave,
):

    if not configurado():
        return None

    conn = None

    try:

        conn = conectar()

        if conn is None:
            return None

        garantir_tabela(
            conn
        )

        cursor = conn.execute(
            """
            SELECT valor
            FROM monitor_runtime_status
            WHERE chave = ?
            LIMIT 1
            """,
            (
                str(chave),
            ),
        )

        linha = cursor.fetchone()

        if not linha:
            return None

        return linha[0]

    except Exception as e:

        print(
            "[RUNTIME/TURSO] "
            "Erro ao carregar status:",
            e,
            flush=True,
        )

        return None

    finally:

        if conn is not None:

            try:
                conn.close()
            except Exception:
                pass
