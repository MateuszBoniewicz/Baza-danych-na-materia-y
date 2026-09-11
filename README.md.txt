# System GM — zarządzanie magazynem

Aplikacja do zarządzania stanem magazynowym: przyjęcia/wydania materiałów, 
kontrola stanu zapasu, inwentaryzacja, raporty i wykresy.

## Funkcje
- Rejestracja przyjęć i wydań z kontrolą stanu magazynowego
- Podgląd stanu zapasu na żywo (kolorowanie: ok / niski / minus)
- Inwentaryzacja — porównanie stanu systemowego z rzeczywistym
- Raporty: wykresy słupkowe/liniowe, eksport do CSV, ranking materiałów

## Technologie
- Python 3
- [SQLite / MS SQL Server — dopisz właściwe]
- tkinter, pandas, matplotlib

## Struktura bazy
Materialy, Magazyny, OperacjeMagazynowe, KontaKosztowe, StanZapasu