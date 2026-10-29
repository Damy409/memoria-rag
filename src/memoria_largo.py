"""Memoria a largo plazo: hechos duraderos recuperados con RAG."""

from __future__ import annotations

import json
import math
import time
import uuid

from llm import llamar_llm


PROMPT_EXTRACCION = (
    "Extraiga de la conversación los hechos que conviene recordar de forma permanente: "
    "datos del usuario, preferencias estables, decisiones y conocimientos importantes. "
    "Ignore lo trivial o temporal. Responda SOLO con un JSON válido con esta forma: "
    '[{"hecho": "texto breve en tercera persona", "importancia": 1-10}]. '
    "Si no hay nada que recordar, responda []."
)


class MemoriaLargoPlazo:
    def __init__(self, coleccion, umbral_duplicado: float = 0.15):
        self.coleccion = coleccion
        self.umbral_duplicado = umbral_duplicado

    def guardar_hecho(self, hecho: str, importancia: int = 5) -> str:
        """Guarda un hecho. Si ya existe uno casi idéntico, lo actualiza."""
        ahora = time.time()
        id_hecho = str(uuid.uuid4())

        if self.coleccion.count() > 0:
            r = self.coleccion.query(query_texts=[hecho], n_results=1)
            distancias = r.get("distances", [[]])[0]
            ids = r.get("ids", [[]])[0]
            if distancias and ids and distancias[0] < self.umbral_duplicado:
                id_hecho = ids[0]

        self.coleccion.upsert(
            ids=[id_hecho],
            documents=[hecho],
            metadatas=[{"importancia": importancia, "creado": ahora, "ultimo_acceso": ahora}],
        )

        return id_hecho

    def extraer_y_guardar(self, mensajes: list[dict]) -> list[str]:
        """Pide al LLM que extraiga hechos de la conversación y los guarda."""

        texto = "\n".join(f"{m['role']}: {m['content']}" for m in mensajes)

        salida = llamar_llm(PROMPT_EXTRACCION, [{"role": "user", "content": texto}])

        try:
            limpio = salida.replace("```json", "").replace("```", "").strip()
            hechos = json.loads(limpio)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

        guardados = []

        for h in hechos:
            if not isinstance(h, dict):
                continue
            hecho = str(h.get("hecho", "")).strip()
            if not hecho:
                continue
            importancia = int(h.get("importancia", 5))
            self.guardar_hecho(hecho, importancia)
            guardados.append(hecho)

        return guardados
    def recuperar(self, consulta: str, k: int = 5, candidatos: int = 15) -> list[str]:
        """RAG con puntuación combinada: similitud + importancia + recencia."""
        total = self.coleccion.count()

        if total == 0:
            return []

        r = self.coleccion.query(query_texts=[consulta], n_results=min(candidatos, total))

        ahora = time.time()
        puntuados = []

        ids = r.get("ids", [[]])[0]
        documentos = r.get("documents", [[]])[0]
        metadatos = r.get("metadatas", [[]])[0]
        distancias = r.get("distances", [[]])[0]

        for id_, doc, meta, dist in zip(ids, documentos, metadatos, distancias):
            similitud = 1 - dist
            importancia = float(meta.get("importancia", 5)) / 10.0
            dias = (ahora - float(meta.get("ultimo_acceso", ahora))) / 86400.0
            recencia = math.exp(-dias / 30.0)
            puntuacion = 0.6 * similitud + 0.25 * importancia + 0.15 * recencia
            puntuados.append((puntuacion, id_, doc, meta))

        puntuados.sort(reverse=True)
        elegidos = [p for p in puntuados[:k] if p[0] > 0.35]

        if elegidos:
            self.coleccion.update(
                ids=[p[1] for p in elegidos],
                metadatas=[{**p[3], "ultimo_acceso": ahora} for p in elegidos],
            )

        return [p[2] for p in elegidos]

    def olvidar(self, consulta: str) -> int:
        """Borra los hechos muy parecidos a la consulta (derecho al olvido)."""
        if self.coleccion.count() == 0:
            return 0

        r = self.coleccion.query(query_texts=[consulta], n_results=3)
        ids = []

        for id_, dist in zip(r.get("ids", [[]])[0], r.get("distances", [[]])[0]):
            if dist < 0.3:
                ids.append(id_)

        if ids:
            self.coleccion.delete(ids=ids)

        return len(ids)
