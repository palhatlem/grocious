"""Five synthetic receipts, seeded only on an explicit demo inbox visit."""

from .store import ingest


def seed():
    examples = [
        ("Kiwi Demo", "Melk", "24,90"),
        ("Vinmonopolet Demo", "Alkoholfri drikk", "49,90"),
        ("Apotek 1 Demo", "Plaster", "39,00"),
        ("Restaurant Demo", "Dagens suppe", "119,00"),
        ("Coop Extra Demo", "Brød", "35,00"),
    ]
    for name, item, amount in examples:
        text = f"{name}\n01.09.2026 12:00\n{item}  {amount}\nTOTALT {amount}\nNOK\nSyntetisk demokvittering"
        ingest(text.encode(), "demo.txt", "text/plain", {"channel": "api"})
