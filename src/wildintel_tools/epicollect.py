import csv
import json
import os
import time
import uuid
from typing import List, Dict

import pyepicollect as pyep
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result
import operator
from datetime import datetime

logger = logging.getLogger(__name__)

# Mapa de operadores permitidos
OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}

def _parse_filter_expression(expr: str):
    """
    Convert a expresion like:
        4_Sitio==A01
        4_Sitio==A01 OR A02
        4_Sitio==A01|A02
    into a function that can be used.

    Parameters
    ----------
    expr : str
        The filter expression.
    Returns
    -------
    Callable[[dict], bool]
        A function that takes an entry dict and returns True if it matches the filter.
    """

    op_token = None
    for op in ["==", "!=", ">=", "<=", ">", "<"]:
        if op in expr:
            op_token = op
            break

    if op_token is None:
        raise ValueError(f"Invalid filter expression (missing operator): {expr}")

    field, value = expr.split(op_token, 1)
    field = field.strip()
    value = value.strip()

    if " OR " in value:
        raw_values = [v.strip() for v in value.split(" OR ")]
    elif "|" in value:
        raw_values = [v.strip() for v in value.split("|")]
    else:
        raw_values = [value]

    values_parsed = []
    for val in raw_values:
        try:
            if "." in val:
                values_parsed.append(float(val))
            else:
                values_parsed.append(int(val))
        except ValueError:
            values_parsed.append(val)

    op_func = OPERATORS[op_token]

    # Función evaluadora con soporte OR
    def evaluator(entry: dict) -> bool:
        entry_value = entry.get(field)

        # intentar castear
        for candidate in values_parsed:
            try:
                ev = entry_value
                if isinstance(candidate, (int, float)) and isinstance(ev, str):
                    if "." in ev:
                        ev = float(ev)
                    else:
                        ev = int(ev)
            except Exception:
                ev = entry_value

            # si alguna comparación es verdadera → OR
            if op_func(ev, candidate):
                return True

        return False  # ninguna coincidió

    return evaluator

def _apply_filters(entries: List[dict], filters: List[str]) -> List[dict]:
    """
    Apply multiple filter expressions as AND to a list of entries
    Args:
        entries (list[dict]): List of entries to filter.
        filters (list[str]): List of filter expressions.
    Returns:
        list[dict]: Filtered list of entries.

    """
    evaluators = [_parse_filter_expression(f) for f in filters]

    filtered = []
    for entry in entries:
        if all(ev(entry) for ev in evaluators):
            filtered.append(entry)
    return filtered

def _norm(value):
    """
    Normalize a value to a clean string.

    Args:
        value (str): The value to normalize.
    Returns:
        str: The normalized string.
    """

    if value is None:
        return ""
    if isinstance(value, list):
        return value[0] if value else ""
    return str(value)


def _random_unknown(prefix="UNKNOWN"):
    """Generate UNKNOWN_XXXX with a short id.

    Args:
        prefix (str): The prefix for the unknown identifier.
    Returns:
        str: The generated unknown identifier.
    """

    return f"{prefix}_{uuid.uuid4().hex[:4].upper()}"

def is_rate_limited(result):
    """
    Check if the API result indicates a rate limit (ec5_255)

    Parameters
    ----------
        result (dict): The API response to check.
    Returns
    -------
        bool: True if rate limited, False otherwise.
    """
    if "errors" in result and result["errors"][0]["code"] == "ec5_255":
        print("[WARN] Rate limit detectado. Reintentando…")
        return True
    return False

@retry(retry=retry_if_result(is_rate_limited),
       wait=wait_exponential(multiplier=1, min=1, max=16),
       stop=stop_after_attempt(6))
def safe_call(fn, *args, **kwargs):
    """
    Ejecutes a pyepicollect function with automatic retries on ec5_255 (rate limit) errors.
    Args:
        fn (callable): The pyepicollect function to call.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.
    Returns:
        dict: The result of the function call.
    """
    return fn(*args, **kwargs)

def get_access_token(client_id, client_secret, token_file="epicollect_token.json"):
    """"
    Obtain an access token from Epicollect, caching it in a local file.

    Parameters
    ----------
    client_id : str
        The Epicollect client ID.
    client_secret : str
        The Epicollect client secret.
    token_file : str
        Path to the file where the token will be cached.
    Returns
    -------
    str
        The access token.
    """

    # Si existe token guardado y no ha expirado, lo usamos
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            data = json.load(f)
        if time.time() < data.get("expires_at", 0):
            logger.debug("Using token saved")
            return data["access_token"]

    # Si no hay token válido, pedimos uno nuevo
    token_resp = safe_call(pyep.auth.request_token, client_id, client_secret)
    access_token = token_resp["access_token"]
    expires_in = token_resp.get("expires_in", 7200)

    # Guardar token con timestamp de expiración
    with open(token_file, "w") as f:
        json.dump({"access_token": access_token, "expires_at": time.time() + expires_in}, f)

    logger.debug("New token obtained and saved")

    return access_token

def get_all_entries(
    app_slug: str,
    form_ref: str,
    token: str,
    per_page=1000,
    filters: List[str] | None = None,
    fields: List[str] | None = None
) -> List:
    """
    Download all entries from an Epicollect form, handling pagination automatically.
    Supports post-filters with expressions like:
        ["4_Sitio==A01", "10_SD>32"]
    Supports field selection to return only a subset of fields.

    Args:
        app_slug (str): The slug of the Epicollect app.
        form_ref (str): The reference of the form to download entries from.
        token (str): The access token for authentication.
        per_page (int): Number of entries to fetch per page (default is 1000).
        filters (list[str]): A list of filter expressions.
        fields (list[str]): A list of field names to keep in each entry.

    Returns:
        list: A list of all (optionally filtered and reduced) entries.
    """
    all_entries = []
    page = 1

    while True:

        result = safe_call(
            pyep.api.get_entries,
            app_slug,
            token=token,
            map_index="",
            form_ref=form_ref,
            page=page,
            per_page=per_page,
        )
        if "errors" in result:
            raise Exception(result["errors"][0]["title"])

        entries = result["data"]["entries"]
        # Convertir listas a cadenas según regla
        for entry in entries:
            for k, v in entry.items():
                if isinstance(v, list):
                    if len(v) == 1:
                        entry[k] = str(v[0])
                    elif len(v) > 1:
                        entry[k] = ":::".join(str(x) for x in v)

        all_entries.extend(entries)

        meta = result["meta"]

        if meta["current_page"] >= meta["last_page"]:
            break

        page += 1

    if filters:
        all_entries = _apply_filters(all_entries, filters)

    if fields:
        filtered_entries = []
        for entry in all_entries:
            reduced = {field: entry.get(field) for field in fields}
            filtered_entries.append(reduced)
        all_entries = filtered_entries

    return all_entries

def get_project_info(slug, token) -> Dict:
    """
    Obtains project information from Epicollect.

    Args:
        slug (str): The slug of the Epicollect app.
        token (str): The access token for authentication.
    Returns:
        dict: The project information.
    """
    result = safe_call(pyep.api.get_project, slug, token=token)
    return result


def group_entries_by_site_and_session(entries, site_aliases, site_field, session_field):
    """
    Groups entries by site and session, ordering them by creation date.
    Args:
        entries (list): A list of entries.
        site_aliases (list): A list of site aliases.
        site_field (str): The field name of the site to group entries by.
        session_field (str): The field name of the session to group entries by.
    Returns:
        dict: A nested dictionary with the structure {site: {session: [entries]}}
    """
    result = {}

    for entry in entries:
        # --- SITE ---
        site_raw = _norm(entry.get(site_field))
        site_raw = site_raw.strip()

        if not site_raw:
            site_key = _random_unknown("UNKNOWN_SITE")
        else:
            site_key = site_aliases.get(site_raw, site_raw)

        if site_key not in result:
            result[site_key] = {}

        # --- SESSION ---
        session_raw = _norm(entry.get(session_field))
        session_raw = session_raw.strip()

        if not session_raw:
            session_key = _random_unknown("UNKNOWN_SES")
        else:
            session_key = session_raw

        if session_key not in result[site_key]:
            result[site_key][session_key] = []

        # --- FECHA ---
        created_at = entry.get("created_at")
        if not created_at:
            created_at = _random_unknown("NO_DATE")
            # Podemos usar la fecha actual o un string, depende de tu lógica

        # Guardamos la tupla (fecha, entry) para ordenar después
        result[site_key][session_key].append((created_at, entry))

    # --- ORDENAR POR FECHA ---
    for site_key in result:
        for session_key in result[site_key]:
            # Convertimos a datetime para ordenar, ignorando entradas sin fecha válida
            def parse_date(tup):
                try:
                    return datetime.fromisoformat(tup[0].replace("Z", "+00:00"))
                except Exception:
                    return datetime.min
            result[site_key][session_key].sort(key=parse_date)

            # Opcional: solo quedarnos con la lista de entries
            result[site_key][session_key] = [e[1] for e in result[site_key][session_key]]

    return result

def entries_to_csv(entries_list, filename="entries.csv", fields=None):
    if not fields:
        fields = set()
        for e in entries_list:
            fields.update(e.keys())
        fields = sorted(fields)

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for e in entries_list:
            row = {k: e.get(k, "") for k in fields}
            writer.writerow(row)


def generate_field_sheet(entries, site_aliases, site_field, session_field):
    grouped = group_entries_by_site_and_session(entries, site_aliases, site_field, session_field)

    resultado = []

    for sitio, revisiones in grouped.items():          # revisiones = dict(session → [entries])
        for revision, entries in revisiones.items():   # entries = lista de entries ordenadas
            todas_fechas = []

            for entry in entries:                      # cada entry ya viene ordenada por created_at
                created = entry.get("created_at")
                if created:
                    # Parseamos ISO 8601 con o sin milisegundos
                    try:
                        dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ")
                    except ValueError:
                        dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")

                    todas_fechas.append((dt, created))

            if not todas_fechas:
                continue

            # Ya vienen casi ordenadas, pero aseguramos
            todas_fechas.sort(key=lambda x: x[0])

            fecha_inicio = todas_fechas[0][1]
            fecha_fin    = todas_fechas[-1][1]

            resultado.append({
                "sitio": sitio,
                "revision": revision,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
            })

    # Ordenamos por fecha_inicio
    def parse_iso(s):
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

    resultado.sort(key=lambda x: parse_iso(x["fecha_inicio"]))

    # Creamos fecha_inicio_new como la fecha_fin del anterior
    for i in range(1, len(resultado)):
        resultado[i]["fecha_inicio_new"] = resultado[i-1]["fecha_fin"]

    return resultado
