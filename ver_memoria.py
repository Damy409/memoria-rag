from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from almacen import crear_cliente, obtener_coleccion


cliente = crear_cliente()

for nombre in ("hechos", "sesiones"):
    col = obtener_coleccion(cliente, nombre)
    print(f"\n=== {nombre} ({col.count()} registros) ===")
    datos = col.get()
    for doc, meta in zip(datos["documents"], datos["metadatas"]):
        print("-", doc, meta)
