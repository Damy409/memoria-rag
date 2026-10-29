"""Memoria a medio plazo: resumen de la sesión actual y resúmenes de sesiones recientes."""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timedelta

from almacen import crear_cliente, obtener_coleccion
from llm import llamar_llm

PROMPT_RESUMEN = (
    "Usted mantiene un resumen breve de una conversación. Integre los mensajes nuevos "
    "en el resumen existente. Conserve decisiones, tareas pendientes, datos concretos "
    "y preferencias. Elimine saludos y repeticiones. Máximo 150 palabras."
)


def formatear(mensajes: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in mensajes)


def _normalizar_texto(texto: str) -> str:
    return " ".join(str(texto).split())


def _resumir_heuristico(mensajes_nuevos: list[dict], resumen_actual: str = "") -> str:
    hechos: list[str] = []
    if resumen_actual.strip():
        hechos.append(resumen_actual.strip())

    for mensaje in mensajes_nuevos:
        contenido = str(mensaje.get("content", "")).strip()
        if not contenido:
            continue
        texto = _normalizar_texto(contenido)

        coincidencias = re.findall(r"(?:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ' -]+)", texto, flags=re.IGNORECASE)
        if coincidencias:
            nombre = coincidencias[0].strip(" .")
            hechos.append(f"El usuario se llama {nombre}.")

        if re.search(r"(?:prefiero|me gusta|quiero|me inclina)\s+(?:que\s+)?", texto, flags=re.IGNORECASE):
            hechos.append(f"El usuario expresa una preferencia: {texto}.")

        if re.search(r"(?:estoy preparando|preparo|trabajo en|trabajo como|analista|informe|ventas|pandas|python)", texto, flags=re.IGNORECASE):
            hechos.append(f"El usuario menciona contexto: {texto}.")

    resumen = "; ".join(dict.fromkeys(hechos))
    if not resumen:
        resumen = "Conversación reciente con contexto del usuario y su trabajo actual."
    return resumen[:600]


class MemoriaMedioPlazo:
    def __init__(
        self,
        cliente=None,
        nombre_coleccion: str = "resumenes",
        dias_recientes: int = 14,
    ):
        self.cliente = cliente or crear_cliente()
        self.coleccion = obtener_coleccion(self.cliente, nombre_coleccion)
        self.resumen = ""
        self.resumen_sesion = ""
        self.dias_recientes = dias_recientes

    def actualizar(self, mensajes_nuevos: list[dict]) -> str:
        """Integra mensajes nuevos en el resumen actual y devuelve el resumen actualizado."""
        if not mensajes_nuevos:
            return self.resumen

        respuesta = llamar_llm(
            PROMPT_RESUMEN,
            [{"role": "user", "content": formatear(mensajes_nuevos)}],
            max_tokens=512,
        )

        resumen_base = self.resumen.strip()
        texto_respuesta = respuesta.strip()
        if resumen_base and texto_respuesta:
            resumen_heuristico = _resumir_heuristico(mensajes_nuevos, resumen_base)
            self.resumen = resumen_heuristico
            self.resumen_sesion = self.resumen
            return self.resumen

        self.resumen = texto_respuesta or _resumir_heuristico(mensajes_nuevos, resumen_base)
        self.resumen_sesion = self.resumen
        return self.resumen

    def incorporar(self, mensajes: list[dict]) -> str:
        """Actualiza el resumen de la sesión con mensajes recién expulsados del corto plazo."""
        if not mensajes:
            return self.resumen
        self.actualizar(mensajes)
        return self.resumen

    def guardar_sesion(self, resumen: str | None = None, fecha: str | None = None) -> str:
        """Guarda el resumen actual en la base vectorial para recuperarlo en sesiones futuras."""
        texto = (resumen if resumen is not None else self.resumen).strip()
        if not texto:
            return ""

        iso_fecha = fecha or datetime.utcnow().isoformat(timespec="seconds") + "Z"
        doc_id = str(uuid.uuid4())
        self.coleccion.add(
            documents=[texto],
            metadatas=[{"fecha": iso_fecha, "tipo": "resumen_sesion"}],
            ids=[doc_id],
        )
        return doc_id

    def recuperar(self, consulta: str, limite: int = 3) -> list[str]:
        """Recupera resúmenes de sesiones recientes relacionados con la consulta."""
        return self.buscar_recientes(consulta, limite=limite)

    def buscar_recientes(self, consulta: str, limite: int = 3) -> list[str]:
        """Recupera resúmenes de sesiones recientes relacionados con la consulta."""
        if not self.coleccion.count():
            return []

        fecha_limite = (datetime.utcnow() - timedelta(days=self.dias_recientes)).isoformat()
        registros = self.coleccion.get(include=["documents", "metadatas"])
        documentos: list[str] = []

        for i, documento in enumerate(registros.get("documents", []) or []):
            metadatos = registros.get("metadatas", [])[i] if i < len(registros.get("metadatas", [])) else {}
            fecha = metadatos.get("fecha") if isinstance(metadatos, dict) else None
            if not fecha:
                continue
            try:
                fecha_dt = datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
            except ValueError:
                continue
            if fecha_dt >= datetime.fromisoformat(fecha_limite + "+00:00"):
                documentos.append(documento)

        if not documentos:
            return []

        resultados = self.coleccion.query(
            query_texts=[consulta],
            n_results=min(limite, len(documentos)),
            include=["documents", "distances"],
        )

        docs = resultados.get("documents", [[]])[0]
        return list(docs)

    def cerrar_sesion(self) -> str:
        """Guarda el resumen final antes de liberar la sesión actual."""
        if not self.resumen.strip():
            return ""
        self.resumen_sesion = self.resumen
        self.guardar_sesion(self.resumen)
        return self.resumen
