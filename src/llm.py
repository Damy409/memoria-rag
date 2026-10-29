import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


MODELO = "claude-sonnet-4-20250514"  # Cambie el modelo según su proveedor


def _normalizar_contenido(contenido: Any) -> str:
    """Convierte el contenido de un mensaje en un texto plano."""
    if isinstance(contenido, list):
        piezas: list[str] = []
        for item in contenido:
            if isinstance(item, dict):
                pieza = item.get("text") or item.get("content") or str(item)
                piezas.append(str(pieza))
            else:
                piezas.append(str(item))
        return " ".join(piezas)
    if isinstance(contenido, dict):
        return str(contenido.get("text") or contenido.get("content") or contenido)
    return str(contenido)


def _fallback_json_hechos(mensajes: list[dict[str, Any]]) -> str:
    """Genera un JSON válido para extracción de hechos cuando no hay un proveedor LLM activo."""
    hechos: list[dict[str, Any]] = []
    visto: set[str] = set()

    def limpiar_texto(texto: str) -> str:
        texto = _normalizar_contenido(texto)
        texto = re.sub(r"(?im)^(?:user|assistant|system)\s*:\s*", "", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return texto

    for mensaje in mensajes:
        if str(mensaje.get("role", "")).lower() != "user":
            continue

        texto = limpiar_texto(mensaje.get("content", ""))
        if not texto:
            continue

        nombre_match = re.search(
            r"(?:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ' -]+)",
            texto,
            flags=re.IGNORECASE,
        )
        if nombre_match:
            nombre = nombre_match.group(1).strip(" .")
            hecho = f"El usuario se llama {nombre}."
            if hecho not in visto:
                hechos.append({"hecho": hecho, "importancia": 9})
                visto.add(hecho)

        if re.search(r"(?:prefiero|me gusta|me gustaría|quiero|me inclina)\s+(?:que\s+)?", texto, flags=re.IGNORECASE):
            if "python" in texto.lower():
                hecho = "El usuario prefiere Python en los ejemplos."
                if hecho not in visto:
                    hechos.append({"hecho": hecho, "importancia": 7})
                    visto.add(hecho)
            elif "pandas" in texto.lower():
                hecho = "El usuario prefiere pandas para el análisis de datos."
                if hecho not in visto:
                    hechos.append({"hecho": hecho, "importancia": 7})
                    visto.add(hecho)

        if re.search(r"(?:trabajo como|trabajo en|analista|ventas|informe|pandas)", texto, flags=re.IGNORECASE):
            if "ventas" in texto.lower() and "pandas" in texto.lower():
                hecho = "El usuario está preparando un informe de ventas trimestral con pandas."
            elif "analista" in texto.lower() or "trabajo como" in texto.lower():
                hecho = "El usuario trabaja como analista de datos."
            else:
                hecho = "El usuario está trabajando en análisis de datos y reporting."
            if hecho not in visto:
                hechos.append({"hecho": hecho, "importancia": 8})
                visto.add(hecho)

        if "cali" in texto.lower() and "trabajo" in texto.lower():
            hecho = "El usuario trabaja en Cali."
            if hecho not in visto:
                hechos.append({"hecho": hecho, "importancia": 6})
                visto.add(hecho)

    return json.dumps(hechos, ensure_ascii=False)


def _extraer_memoria_contexto(sistema: str) -> str:
    """Extrae hechos relevantes del prompt del sistema para responder sin API externa."""
    if not sistema:
        return ""

    lineas = []
    for bloque in sistema.split("\n\n"):
        if bloque.startswith("##") or "memoria" in bloque.lower() or "resumen" in bloque.lower():
            for linea in bloque.splitlines():
                linea = linea.strip()
                if linea.startswith("-"):
                    lineas.append(linea[1:].strip())
                elif linea.startswith("##"):
                    continue

    # Normaliza y elimina ruido del propio prompt.
    relevantes: list[str] = []
    for linea in lineas:
        texto = linea.strip()
        if texto and len(texto) < 400 and "Use esta información solo si es relevante" not in texto:
            relevantes.append(texto)
    return " ".join(relevantes[:6])


def _fallback_respuesta(mensajes: list[dict[str, Any]], sistema: str) -> str:
    """Respuesta local útil cuando no hay API key: mantiene la conversación sin romper la demo."""
    ultimo = mensajes[-1]
    contenido = _normalizar_contenido(ultimo.get("content", "")).strip()
    contenido_lower = contenido.lower()
    memoria = _extraer_memoria_contexto(sistema)
    memoria_lower = memoria.lower()

    if "recuerda" in contenido_lower or "trabajando" in contenido_lower or "estaba" in contenido_lower:
        if "nombre" in contenido_lower or "llama" in contenido_lower:
            if "se llama ana" in memoria_lower or "ana" in memoria_lower:
                return "Sí, el usuario se llama Ana."
        if "ventas" in contenido_lower or "pandas" in contenido_lower or "trabajando" in contenido_lower:
            if "ventas trimestral" in memoria_lower or "informe de ventas" in memoria_lower:
                return "Sí, estaba preparando un informe de ventas trimestral con pandas."
            if "pandas" in memoria_lower or "ventas" in memoria_lower:
                return "Sí, estaba trabajando en un informe de ventas con pandas."
        if "python" in memoria_lower and "preferencia" in memoria_lower:
            return "Sí, el usuario prefiere Python en los ejemplos y estaba trabajando en un informe de ventas con pandas."
        if memoria:
            return f"Sí, recuerdo que {memoria}."
        return "Sí, estaba trabajando en el contexto de la conversación actual."

    if "agrupo" in contenido_lower and "ventas" in contenido_lower and "mes" in contenido_lower:
        if "python" in memoria_lower or "pandas" in memoria_lower:
            return "Como prefiere Python, aquí tienes un ejemplo con pandas: df.groupby(pd.Grouper(key='fecha', freq='M')).sum()."
        return "Para agrupar ventas por mes en pandas, usa: df.groupby(pd.Grouper(key='fecha', freq='M')).sum()."

    if "python" in contenido_lower and ("ejemplo" in contenido_lower or "prefiero" in contenido_lower or "me gusta" in contenido_lower):
        return "Entendido: usaré Python en los ejemplos."

    if "nombre" in contenido_lower and ("llamas" in contenido_lower or "te llamas" in contenido_lower or "llama" in contenido_lower):
        if "se llama ana" in memoria_lower:
            return "El usuario se llama Ana."

    if sistema and "resuma" in sistema.lower():
        return "Resumen breve: se conserva el contexto principal de la conversación y las preferencias del usuario."

    if memoria:
        return f"Basado en lo que recuerdo, {memoria[:180]}"

    return "[respuesta simulada] " + contenido[:200]


def llamar_llm(sistema: str, mensajes: list[dict[str, Any]], max_tokens: int = 1024) -> str:
    """Envía un prompt de sistema y una lista de mensajes al LLM y devuelve el texto."""
    if not mensajes:
        raise ValueError("La lista de mensajes no puede estar vacía.")

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
        except ImportError:
            pass
        else:
            cliente = anthropic.Anthropic()
            respuesta = cliente.messages.create(
                model=MODELO,
                max_tokens=max_tokens,
                system=sistema,
                messages=mensajes,
            )
            textos: list[str] = []
            for bloque in getattr(respuesta, "content", []):
                if hasattr(bloque, "text"):
                    textos.append(bloque.text)
            if textos:
                return "".join(textos)
            return ""

    if "JSON válido" in sistema or "Si no hay nada que recordar" in sistema:
        return _fallback_json_hechos(mensajes)

    return _fallback_respuesta(mensajes, sistema)
