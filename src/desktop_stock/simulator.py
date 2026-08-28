"""Sistema legado Windows simulado para demonstração da automação visual."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

HEADERS = (
    "lote_id",
    "produto",
    "quantidade_disponivel",
    "localizacao",
    "status_estoque",
    "atualizado_em",
)

SAMPLE_STOCK = (
    ("L001", "Monitor", 18, "A-01", "DISPONIVEL", "2026-08-26T12:00:00+00:00"),
    ("L002", "Teclado", 4, "A-02", "BAIXO", "2026-08-26T12:02:00+00:00"),
    ("L003", "Mouse", 0, "B-07", "INDISPONIVEL", "2026-08-26T12:04:00+00:00"),
    ("L004", "Notebook", 7, "C-03", "DISPONIVEL", "2026-08-26T12:06:00+00:00"),
    ("L005", "Impressora", 2, "D-11", "BAIXO", "2026-08-26T12:08:00+00:00"),
)


class StockSimulatorApp:
    """Interface controlada cuja massa só é exposta ao bot pela tela."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Sistema Legado de Estoque - Capstone")
        root.geometry("900x520")
        root.minsize(850, 480)

        ttk.Label(root, text="Sistema Legado de Estoque", font=("Segoe UI", 18, "bold")).pack(pady=(18, 4))
        ready = tk.Canvas(root, height=18, width=110, highlightthickness=0)
        ready.create_rectangle(0, 0, 110, 18, fill="#1E88E5", outline="#1E88E5")
        ready.pack()
        ttk.Label(root, text="Pronto para consulta").pack(pady=(2, 12))

        search_frame = ttk.Frame(root)
        search_frame.pack(fill="x", padx=24)
        marker = tk.Canvas(search_frame, height=24, width=24, highlightthickness=0)
        marker.create_rectangle(0, 0, 24, 24, fill="#C2185B", outline="#C2185B")
        marker.pack(side="left", padx=(0, 8))
        ttk.Label(search_frame, text="Lote:").pack(side="left")
        self.query = ttk.Entry(search_frame, width=34)
        self.query.pack(side="left", padx=8)
        self.query.insert(0, "*")
        ttk.Button(search_frame, text="Consultar", command=self.search).pack(side="left")
        self.query.bind("<Return>", lambda _event: self.search())

        result_frame = ttk.Frame(root)
        result_frame.pack(fill="both", expand=True, padx=24, pady=18)
        result_marker = tk.Canvas(result_frame, height=24, width=24, highlightthickness=0)
        result_marker.create_rectangle(0, 0, 24, 24, fill="#00897B", outline="#00897B")
        result_marker.pack(side="left", anchor="n", padx=(0, 8))
        self.results = tk.Text(result_frame, wrap="none", font=("Consolas", 9))
        self.results.pack(side="left", fill="both", expand=True)
        self.status = ttk.Label(root, text="Nenhuma consulta executada")
        self.status.pack(pady=(0, 14))
        self.search()

    def search(self) -> None:
        query = self.query.get().strip().upper()
        rows = SAMPLE_STOCK if query in {"", "*"} else tuple(
            row for row in SAMPLE_STOCK if row[0].upper() == query
        )
        lines = ["\t".join(HEADERS)]
        lines.extend("\t".join(map(str, row)) for row in rows)
        self.results.delete("1.0", "end")
        self.results.insert("1.0", "\n".join(lines))
        self.status.configure(text=f"Consulta concluída: {len(rows)} registro(s)")


def main() -> None:
    root = tk.Tk()
    StockSimulatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
