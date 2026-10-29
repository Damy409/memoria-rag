"""Chat de consola con memoria a corto, medio y largo plazo."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gestor import GestorMemoria


def main():
    gestor = GestorMemoria()
    print("Chat con memoria. Escriba 'salir' para terminar.\n")

    while True:
        try:
            texto = input("Usted: ").strip()
        except EOFError:
            print("\nSesión cerrada por fin de entrada.")
            gestor.cerrar_sesion()
            break

        if texto.lower() in {"salir", "exit"}:
            gestor.cerrar_sesion()
            print("Sesión guardada. Hasta pronto.")
            break
        if texto:
            print(f"Asistente: {gestor.conversar(texto)}\n")


if __name__ == "__main__":
    main()
