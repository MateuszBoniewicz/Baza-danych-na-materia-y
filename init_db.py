import sqlite3

def initialize_database():
    # Połączenie z bazą (stworzy plik, jeśli go nie ma)
    connection = sqlite3.connect('gmsystem.db')
    cursor = connection.cursor()
    
    # Wczytanie pliku SQL (używamy nazwy z Twojego komputera)
    try:
        with open('gm_schema_and_data 1.sql', 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # Wykonanie komend tworzących tabele (Materialy, OperacjeMagazynowe itd.)
        cursor.executescript(sql_script)
        connection.commit()
        print("Sukces: Tabele zostały utworzone w gmsystem.db")
    except FileNotFoundError:
        print("Błąd: Nie znaleziono pliku 'gm_schema_and_data 1.sql' w folderze.")
    except Exception as e:
        print(f"Wystąpił błąd: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    initialize_database()