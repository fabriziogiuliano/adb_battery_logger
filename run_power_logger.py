import subprocess
import time
import csv
from datetime import datetime
import re
import sys
import os

# ========================= CONFIGURAZIONE GLOBALE =========================
T_sleep = 0.01  # Tempo di attesa in secondi (variabile)
ENABLE_LOGGING = True  # Abilita/disabilita il logging CSV
ENABLE_DELTA_COLUMNS = True # Abilita/disabilita colonne delta (sia per display che per CSV)
ENABLE_THERMAL_SENSORS = True # Abilita/disabilita lettura sensori termici
ENABLE_CPU_MONITORING = False  # Abilita/disabilita monitoraggio CPU
ENABLE_MEMORY_MONITORING = False # Abilita/disabilita monitoraggio Memoria

# Percorso dell'eseguibile ADB (modifica se necessario)
ADB_PATH = "./adb"
# ========================= FINE CONFIGURAZIONE GLOBALE =====================

# --- Funzioni Helper (Migliorate) ---

def run_adb_command(command_args, capture=True, text=True, check=False): # Default check=False per gestire errori internamente
    """Esegue un comando ADB e gestisce gli errori comuni."""
    try:
        # Aggiungi encoding e gestione errori per output potenzialmente problematico
        process = subprocess.run(
            [ADB_PATH] + command_args,
            capture_output=capture, text=text, check=check,
            encoding='utf-8', errors='ignore' # Ignora errori di decodifica
        )
        if check and process.returncode != 0:
             # Se check=True era richiesto e fallisce, stampa errore ma continua (restituisce None)
             print(f"\nErrore ADB (Codice {process.returncode}): Comando '{' '.join(command_args)}' fallito.", file=sys.stderr)
             if process.stderr:
                 print(f"Stderr: {process.stderr.strip()}", file=sys.stderr)
             return None

        # Se check=False, controlliamo comunque returncode per sicurezza
        if process.returncode != 0:
             # Non stampiamo errore se check=False, potrebbe essere atteso (es. grep che non trova nulla)
             # Ma restituiamo None per indicare che il comando non ha avuto successo come previsto
             # O forse meglio restituire l'output vuoto se c'è? Dipende dal contesto.
             # Restituire None è più sicuro per indicare un problema.
             # print(f"Debug: Comando '{' '.join(command_args)}' terminato con codice {process.returncode}", file=sys.stderr)
             return None # Indica fallimento o output non utile

        return process.stdout.strip() if capture else True # Restituisce True se capture=False e successo
    except subprocess.CalledProcessError as e:
        # Questo viene catturato solo se check=True fallisce
        print(f"\nErrore ADB: Comando '{' '.join(command_args)}' fallito: {e}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"\nErrore: Comando '{ADB_PATH}' non trovato. Assicurati che ADB sia nel path specificato o nel PATH di sistema.", file=sys.stderr)
        sys.exit(1) # Esce se ADB non è trovato
    except Exception as e:
        print(f"\nErrore inaspettato durante l'esecuzione di ADB '{' '.join(command_args)}': {e}", file=sys.stderr)
        return None

def get_battery_value(property_name):
    """Legge proprietà batteria da sysfs."""
    # Non usiamo check=True perché un file potrebbe non esistere (es. current_avg su alcuni device)
    output = run_adb_command(["shell", f"cat /sys/class/power_supply/battery/{property_name}"], check=False)
    # print(f"Debug Batt Read: {property_name} -> {output}") # DEBUG
    return output

def get_battery_temperature():
    """Legge temperatura batteria da dumpsys battery."""
    # Usiamo grep, quindi check=False è appropriato (potrebbe non trovare "temp")
    output = run_adb_command(["shell", "dumpsys battery | grep temp"], check=False)
    # print(f"Debug Batt Temp Raw: {output}") # DEBUG
    if output:
        parts = output.split(':')
        if len(parts) > 1:
            val_str = parts[1].strip()
            try:
                temp_val = float(val_str) / 10.0
                # print(f"Debug Batt Temp Parsed: {temp_val}") # DEBUG
                return temp_val
            except ValueError:
                print(f"Warning: Impossibile convertire valore temperatura batteria: '{val_str}'", file=sys.stderr)
                return None
    return None

def get_temperature_data():
    """Esegue adb shell dumpsys thermalservice e restituisce output."""
    # check=True qui è ragionevole, il servizio dovrebbe esistere
    output = run_adb_command(['shell', 'dumpsys', 'thermalservice'], check=True)
    # print(f"Debug Thermal Raw: {'Output lungo...' if output else 'Nessun output'}") # DEBUG
    return output

def parse_temperature_output(output):
    """Analizza output dumpsys thermalservice ed estrae temperature."""
    temperatures = {}
    if not output:
        return temperatures

    lines = output.splitlines()
    start_parsing_cached = False
    start_parsing_current = False

    # Regex migliorata: cerca nome e valore in modo più flessibile
    temp_regex = re.compile(r"Temperature\{.*?mValue=([\d.-]+).*?mName=([^,}]+)")

    current_section_temps = {} # Prioritizza Current HAL
    cached_section_temps = {}

    for line in lines:
        line = line.strip()
        if line == "Cached temperatures:":
            start_parsing_cached = True
            start_parsing_current = False
            continue
        if line == "Current temperatures from HAL:":
            start_parsing_current = True
            start_parsing_cached = False
            continue
        if line == "Sensor Status:": # Sezione successiva, smetti di cercare temperature
             start_parsing_cached = False
             start_parsing_current = False
             continue


        if start_parsing_current or start_parsing_cached:
            match = temp_regex.search(line)
            if match:
                try:
                    value = float(match.group(1))
                    # Pulisci nome: rimuovi spazi iniziali/finali, sostituisci spazi interni con _, rimuovi virgolette
                    name = match.group(2).strip().replace(" ", "_").replace('"','')
                    if start_parsing_current:
                        current_section_temps[name] = value
                    elif start_parsing_cached:
                         # Aggiungi solo se non presente nella sezione Current HAL
                         if name not in current_section_temps:
                             cached_section_temps[name] = value

                except ValueError:
                    print(f"Warning: Impossibile convertire valore sensore termico: {match.group(1)} per {match.group(2)}", file=sys.stderr)
                except IndexError:
                     print(f"Warning: Regex fallita su linea termica: {line}", file=sys.stderr)


    # Unisci i risultati, dando priorità a "Current HAL"
    temperatures.update(cached_section_temps)
    temperatures.update(current_section_temps) # Sovrascrive i cached se ci sono duplicati
    # print(f"Debug Thermal Parsed: {temperatures}") # DEBUG
    return temperatures

def get_cpu_usage():
    """Ottiene utilizzo CPU dettagliato da 'top'."""
    # Prova prima con batch mode, più stabile per lo scripting
    output = run_adb_command(["shell", "top", "-b", "-n", "1"], check=False)
    if not output or "%cpu" not in output.lower(): # Fallback se -b non funziona o l'output è strano
        # print("Debug CPU: Fallback a 'top -n 1'") # DEBUG
        output = run_adb_command(["shell", "top", "-n", "1"], check=False)

    # print(f"Debug CPU Raw Output:\n{output}\n----------------") # DEBUG

    if output:
        cpu_line = None
        # Cerca linea che contenga pattern tipici tipo "user", "sys", "idle"
        for line in output.splitlines():
            line_lower = line.lower()
            if ("user" in line_lower or "usr" in line_lower) and \
               ("sys" in line_lower or "system" in line_lower) and \
               ("idle" in line_lower):
                cpu_line = line
                # print(f"Debug CPU Line Found: {cpu_line}") # DEBUG
                break

        if cpu_line:
            # Regex migliorate e più specifiche per ogni campo
            user_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*(?:usr|user))", cpu_line, re.IGNORECASE)
            nice_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*(?:nic|nice))", cpu_line, re.IGNORECASE)
            sys_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*(?:sys|system))", cpu_line, re.IGNORECASE)
            idle_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*idle)", cpu_line, re.IGNORECASE)
            iow_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*(?:iow|iowait|io))", cpu_line, re.IGNORECASE) # Aggiunto 'io'
            irq_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*irq)", cpu_line, re.IGNORECASE)
            sirq_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*(?:sirq|softirq))", cpu_line, re.IGNORECASE)
            host_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*host)", cpu_line, re.IGNORECASE) # Meno comune

            # Funzione helper per estrarre il valore o 'N/A'
            def get_val(match):
                 if match:
                     try:
                         val = float(match.group(1))
                         return int(val) if val.is_integer() else round(val, 1) # Arrotonda a 1 decimale se float
                     except ValueError:
                         return 'N/A'
                 return 'N/A'

            user_val = get_val(user_match)
            nice_val = get_val(nice_match)
            sys_val = get_val(sys_match)
            idle_val = get_val(idle_match)
            iow_val = get_val(iow_match)
            irq_val = get_val(irq_match)
            sirq_val = get_val(sirq_match)
            host_val = get_val(host_match) # Raramente presente

            # Calcola totale: Somma di user, system, nice, iow, irq, sirq (se disponibili e numerici)
            # O 100 - idle se idle è un numero valido
            total_val = 'N/A'
            if isinstance(idle_val, (int, float)):
                total_val = round(100.0 - float(idle_val), 1)
            else:
                # Prova a sommare gli altri componenti noti se idle non è disponibile
                components = [comp for comp in [user_val, nice_val, sys_val, iow_val, irq_val, sirq_val, host_val] if isinstance(comp, (int, float))]
                if components:
                    total_val = round(sum(float(c) for c in components), 1)

            cpu_results = {
                "total": total_val,
                "user": user_val,
                "nice": nice_val,
                "system": sys_val,
                "idle": idle_val,
                "iowait": iow_val,
                "irq": irq_val,
                "sirq": sirq_val,
                "host": host_val,
            }
            # print(f"Debug CPU Parsed: {cpu_results}") # DEBUG
            return cpu_results

    print("Warning: Impossibile parsare output 'top' per CPU.", file=sys.stderr)
    return None # Fallimento completo


# ========================================================================
# <<< INIZIO FUNZIONE get_memory_usage MODIFICATA >>>
# ========================================================================
def get_memory_usage():
    """Ottiene utilizzo memoria da 'top' o fallback a 'dumpsys meminfo' (semplificato)."""
    output_top = run_adb_command(["shell", "top", "-b", "-n", "1"], check=False)
    if not output_top or "Mem:" not in output_top:
         output_top = run_adb_command(["shell", "top", "-n", "1"], check=False)

    # print(f"Debug Mem Raw Output (top):\n{output_top}\n----------------") # DEBUG

    mem_data = {}
    parsed_from_top = False
    ram_cached_kb = None # Variabile per cache trovata nella linea Mem:

    if output_top:
        mem_line = None
        swap_line = None
        # Cerca linee che iniziano con "Mem:" e "Swap:" (case insensitive)
        for line in output_top.splitlines():
            if re.match(r"^\s*Mem:", line, re.IGNORECASE):
                mem_line = line
            elif re.match(r"^\s*Swap:", line, re.IGNORECASE):
                swap_line = line
            # Non fermarti finché non hai letto tutto

        # --- Parsing Linea Mem: ---
        if mem_line:
            # Funzione helper per estrarre valori DALLA LINEA MEM
            def extract_mem_val(label):
                match = re.search(rf"(\d+)\s*k\s*{label}", mem_line, re.IGNORECASE)
                if match: return int(match.group(1))
                match = re.search(rf"(\d+)\s*m\s*{label}", mem_line, re.IGNORECASE)
                if match: return int(match.group(1)) * 1024
                return None

            total_kb = extract_mem_val("total")
            free_kb = extract_mem_val("free")
            used_kb = extract_mem_val("used")
            buffers_kb = extract_mem_val("buffers")
            # Cerchiamo ancora cache qui, ma lo salviamo temporaneamente
            ram_cached_kb = extract_mem_val("cached") or extract_mem_val("cache")

            if total_kb is not None:
                mem_data['total_mb'] = round(total_kb / 1024.0, 1)
                mem_data['free_mb'] = round(free_kb / 1024.0, 1) if free_kb is not None else 'N/A'
                mem_data['buffers_mb'] = round(buffers_kb / 1024.0, 1) if buffers_kb is not None else 'N/A'

                if used_kb is None and free_kb is not None:
                     calculated_used = total_kb - free_kb - (buffers_kb or 0) - (ram_cached_kb or 0)
                     mem_data['used_mb'] = round(calculated_used / 1024.0, 1)
                elif used_kb is not None:
                     mem_data['used_mb'] = round(used_kb / 1024.0, 1)
                else:
                     mem_data['used_mb'] = 'N/A'

                if free_kb is not None:
                     available_kb = free_kb + (buffers_kb or 0) + (ram_cached_kb or 0)
                     mem_data['available_mb'] = round(available_kb / 1024.0, 1)
                else:
                     mem_data['available_mb'] = 'N/A'

                parsed_from_top = True # Abbiamo parsato almeno la linea Mem:

        # --- Parsing Linea Swap: ---
        swap_cached_kb = None # Inizializza swap cache a None
        if swap_line:
             # Funzione helper per estrarre valori DALLA LINEA SWAP
             def extract_swap_val(label):
                 match = re.search(rf"(\d+)\s*k\s*{label}", swap_line, re.IGNORECASE)
                 if match: return int(match.group(1))
                 match = re.search(rf"(\d+)\s*m\s*{label}", swap_line, re.IGNORECASE)
                 if match: return int(match.group(1)) * 1024
                 return None

             swap_total_kb = extract_swap_val("total")
             swap_used_kb = extract_swap_val("used")
             # << CORREZIONE: CERCA "cached" QUI >>
             swap_cached_kb = extract_swap_val("cached") # Cerca cached nella linea Swap

             mem_data['swap_total_mb'] = round(swap_total_kb / 1024.0, 1) if swap_total_kb is not None else 'N/A'
             mem_data['swap_used_mb'] = round(swap_used_kb / 1024.0, 1) if swap_used_kb is not None else 'N/A'
             # Assegna il valore trovato qui alla colonna generica 'Memory Cached (MB)'
             mem_data['cached_mb'] = round(swap_cached_kb / 1024.0, 1) if swap_cached_kb is not None else 'N/A'

        else: # Nessuna linea Swap trovata
            mem_data['swap_total_mb'] = 'N/A'
            mem_data['swap_used_mb'] = 'N/A'
            # Se non c'è linea swap, cached_mb non può venire da qui
            if 'cached_mb' not in mem_data:
                mem_data['cached_mb'] = 'N/A' # Sarà impostato dopo se ram_cached_kb esiste

        # Fallback: Se non abbiamo trovato 'cached' nella linea Swap,
        # ma lo avevamo trovato nella linea Mem (ram_cached_kb), usiamo quello
        if swap_cached_kb is None and ram_cached_kb is not None:
             mem_data['cached_mb'] = round(ram_cached_kb / 1024.0, 1)
             # print("Debug Mem: Usato ram_cached_kb come fallback per Memory Cached (MB)") # DEBUG


    # --- Fallback Dumpsys ---
    if parsed_from_top:
         # print(f"Debug Mem Parsed (top): {mem_data}") # DEBUG
         # Assicurati che tutte le chiavi memoria esistano nel dict restituito, anche se N/A
         for key in ['total_mb', 'used_mb', 'free_mb', 'available_mb', 'buffers_mb', 'cached_mb', 'swap_total_mb', 'swap_used_mb']:
             if key not in mem_data:
                 mem_data[key] = 'N/A'
         return mem_data

    # Fallback a dumpsys (se top non ha funzionato)
    print("Warning: Tentativo di fallback a 'dumpsys meminfo' per la memoria totale (output di top non utilizzabile).", file=sys.stderr)
    output_dumpsys = run_adb_command(["shell", "dumpsys meminfo"], check=False)
    if output_dumpsys:
        total_ram_match = re.search(r"Total RAM:\s*([\d,]+)\s*kB", output_dumpsys)
        free_ram_match = re.search(r"Free RAM:\s*([\d,]+)\s*kB", output_dumpsys)
        used_ram_match = re.search(r"Used RAM:\s*([\d,]+)\s*kB", output_dumpsys)
        total_swap_match = re.search(r"Total Swap:\s*([\d,]+)\s*kB", output_dumpsys)

        def parse_dumpsys_val(match):
            if match:
                 try: return int(match.group(1).replace(',', ''))
                 except ValueError: return None
            return None

        total_kb = parse_dumpsys_val(total_ram_match)
        free_kb = parse_dumpsys_val(free_ram_match)
        used_kb = parse_dumpsys_val(used_ram_match)
        swap_total_kb = parse_dumpsys_val(total_swap_match)

        if total_kb is not None:
            mem_data['total_mb'] = round(total_kb / 1024.0, 1)
            mem_data['free_mb'] = round(free_kb / 1024.0, 1) if free_kb is not None else 'N/A'
            mem_data['used_mb'] = round(used_kb / 1024.0, 1) if used_kb is not None else 'N/A'
            mem_data['swap_total_mb'] = round(swap_total_kb / 1024.0, 1) if swap_total_kb is not None else 'N/A'
            # Dumpsys non fornisce facilmente questi, quindi rimangono N/A
            mem_data['available_mb'] = 'N/A'
            mem_data['buffers_mb'] = 'N/A'
            mem_data['cached_mb'] = 'N/A' # Dumpsys non lo dà facilmente
            mem_data['swap_used_mb'] = 'N/A' # Dumpsys non lo dà facilmente
            # Assicurati che tutte le chiavi siano presenti
            for key in ['total_mb', 'used_mb', 'free_mb', 'available_mb', 'buffers_mb', 'cached_mb', 'swap_total_mb', 'swap_used_mb']:
                 if key not in mem_data: mem_data[key] = 'N/A'
            return mem_data


    print("Warning: Impossibile ottenere dati memoria da 'top' o 'dumpsys meminfo'.", file=sys.stderr)
    # Ritorna comunque un dizionario con N/A per evitare errori successivi
    return {
        'total_mb': 'N/A', 'used_mb': 'N/A', 'free_mb': 'N/A',
        'available_mb': 'N/A', 'buffers_mb': 'N/A', 'cached_mb': 'N/A',
        'swap_total_mb': 'N/A', 'swap_used_mb': 'N/A'
    }
# ========================================================================
# <<< FINE FUNZIONE get_memory_usage MODIFICATA >>>
# ========================================================================


def get_device_model():
    """Recupera modello dispositivo."""
    model = run_adb_command(["shell", "getprop ro.product.model"])
    return model if model else "UNKNOWN_MODEL"

def get_device_serial():
    """Recupera seriale dispositivo."""
    serial = run_adb_command(["get-serialno"])
    return serial if serial else "UNKNOWN_SERIAL"

def sanitize_filename(filename):
    """Sanifica nome file."""
    sanitized = re.sub(r'[<>:"/\\|?*\s]+', '_', filename) # Sostituisci uno o più caratteri illegali con un underscore
    sanitized = re.sub(r'_+', '_', sanitized) # Rimuovi underscore multipli
    sanitized = sanitized.strip('._') # Rimuovi punti o underscore iniziali/finali
    return sanitized if sanitized else "invalid_filename"


# --- Nuove Funzioni per la Struttura (Leggermente modificate) ---

def get_all_available_columns(include_thermal=True, include_cpu=True, include_memory=True, include_deltas=True):
    """Determina tutte le colonne potenzialmente disponibili."""
    columns = [ # Ordine base
        'Timestamp', 'Current (mA)', 'Avg Current (mA)', 'Voltage (mV)',
        'Power (W)', 'Capacity (%)', 'Battery Temp (°C)'
    ]

    if include_deltas:
        columns.extend([
            'ΔCurrent (mA)', 'ΔAvg Current (mA)', 'ΔVoltage (mV)', 'ΔPower (W)'
        ])

    if include_cpu:
        columns.extend([ # Mantieni ordine consistente
            'CPU Total (%)', 'CPU User (%)','CPU System (%)', 'CPU Nice (%)',
            'CPU Idle (%)', 'CPU Iowait (%)', 'CPU Irq (%)', 'CPU Sirq (%)',
            'CPU Host (%)'
        ])

    if include_memory:
        columns.extend([ # Aggiunti nuovi campi memoria
            'Memory Total (MB)', 'Memory Used (MB)', 'Memory Free (MB)',
            'Memory Available (MB)', 'Memory Buffers (MB)', 'Memory Cached (MB)', # <--- Chiave usata coerentemente
            'Swap Total (MB)', 'Swap Used (MB)'
        ])

    thermal_sensor_names = []
    if include_thermal:
        print("Recupero nomi sensori termici dal dispositivo...")
        thermal_output = get_temperature_data()
        if thermal_output:
            thermal_sensors = parse_temperature_output(thermal_output)
            # Ordina i nomi dei sensori alfabeticamente per un output consistente
            thermal_sensor_names = sorted(list(thermal_sensors.keys()))
            columns.extend(thermal_sensor_names) # Aggiungi alla fine
            print(f"Trovati {len(thermal_sensor_names)} sensori termici.")
        else:
            print("Warning: Impossibile recuperare i nomi dei sensori termici.", file=sys.stderr)

    return columns, thermal_sensor_names


def prompt_user_for_display_columns(all_columns):
    """Chiede all'utente quali colonne visualizzare."""
    print("\n--- Colonne Disponibili per la Visualizzazione ---")
    for i, col_name in enumerate(all_columns):
        print(f"  {i+1}: {col_name}")

    while True:
        try:
            #choice_str = input("\nInserisci i numeri delle colonne da visualizzare, separati da virgola (es: 1,3,5) o range (es: 1-4,8,10-12), o 'all' per tutte: ")
            choice_str = "1-7"
            choice_str = choice_str.strip().lower()

            if choice_str == 'all':
                chosen_indices = set(range(len(all_columns)))
            else:
                chosen_indices = set()
                parts = choice_str.split(',')
                for part in parts:
                    part = part.strip()
                    if not part: continue
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        if start < 1 or end > len(all_columns) or start > end:
                            raise ValueError(f"Range non valido: {part}")
                        chosen_indices.update(range(start - 1, end)) # Indici 0-based
                    else:
                        idx = int(part)
                        if idx < 1 or idx > len(all_columns):
                            raise ValueError(f"Numero colonna non valido: {idx}")
                        chosen_indices.add(idx - 1)

            if not chosen_indices:
                print("Nessuna colonna selezionata. Riprova.")
                continue

            # Usiamo una lista ordinata basata sull'ordine originale
            chosen_columns_ordered = [all_columns[i] for i in range(len(all_columns)) if i in chosen_indices]

            print("\nColonne selezionate per la visualizzazione:")
            for col in chosen_columns_ordered:
                 print(f" - {col}")
            # Restituiamo la lista ordinata, non il set, per mantenere l'ordine
            return chosen_columns_ordered

        except ValueError as e:
            print(f"Input non valido: {e}. Assicurati di usare numeri, virgole o trattini correttamente. Riprova.")
        except Exception as e:
            print(f"Errore inaspettato nell'input: {e}. Riprova.")


def build_display_header(ordered_chosen_columns):
    """Costruisce la stringa dell'intestazione per la console."""
    if not ordered_chosen_columns:
        return ""

    header_parts = []
    # Mappe indicative per larghezza colonne (aggiornate/aggiustate)
    widths = {
        'Timestamp': 23, 'Current (mA)': 12, 'Avg Current (mA)': 16, 'Voltage (mV)': 12,
        'Power (W)': 11, 'Capacity (%)': 10, 'Battery Temp (°C)': 15,
        'ΔCurrent (mA)': 14, 'ΔAvg Current (mA)': 18, 'ΔVoltage (mV)': 14, 'ΔPower (W)': 12,
        'CPU Total (%)': 11, 'CPU User (%)': 10, 'CPU System (%)': 12, 'CPU Nice (%)': 10,
        'CPU Idle (%)': 10, 'CPU Iowait (%)': 12, 'CPU Irq (%)': 9, 'CPU Sirq (%)': 10,
        'CPU Host (%)': 10,
        'Memory Total (MB)': 15, 'Memory Used (MB)': 14, 'Memory Free (MB)': 14,
        'Memory Available (MB)': 18, 'Memory Buffers (MB)': 16, 'Memory Cached (MB)': 15, # <--- Larghezza coerente
        'Swap Total (MB)': 13, 'Swap Used (MB)': 12,
        # Larghezza default per sensori termici (aggiustabile)
        'DEFAULT_THERMAL': 18
    }

    for col_name in ordered_chosen_columns:
         # Determina larghezza: usa specifica se esiste, altrimenti default
         default_w = widths['DEFAULT_THERMAL'] if len(col_name) < 15 else len(col_name) + 2
         width = widths.get(col_name, default_w)
         header_parts.append(f"{col_name:<{width}} | ") # Allineato a sinistra

    return "".join(header_parts)

def format_value_for_display(value, col_name):
    """Formatta un valore per la visualizzazione in console (Allineamento a destra)."""
    # Mappe indicative per precisione decimali
    precision_map = {
        'Current (mA)': 1, 'Avg Current (mA)': 1, 'Voltage (mV)': 1,
        'Power (W)': 3, 'Battery Temp (°C)': 1,
        'ΔCurrent (mA)': 1, 'ΔAvg Current (mA)': 1, 'ΔVoltage (mV)': 1, 'ΔPower (W)': 3,
         'Memory Total (MB)': 0, 'Memory Used (MB)': 0, 'Memory Free (MB)': 0,
        'Memory Available (MB)': 0, 'Memory Buffers (MB)': 0, 'Memory Cached (MB)': 0, # <--- Precisione coerente
        'Swap Total (MB)': 0, 'Swap Used (MB)': 0,
        'CPU': 1, # Default per tutti i campi CPU
        'DEFAULT_THERMAL': 1
    }
    # Larghezze (devono corrispondere a build_display_header)
    widths = {
        'Timestamp': 23, 'Current (mA)': 12, 'Avg Current (mA)': 16, 'Voltage (mV)': 12,
        'Power (W)': 11, 'Capacity (%)': 10, 'Battery Temp (°C)': 15,
        'ΔCurrent (mA)': 14, 'ΔAvg Current (mA)': 18, 'ΔVoltage (mV)': 14, 'ΔPower (W)': 12,
        'CPU Total (%)': 11, 'CPU User (%)': 10, 'CPU System (%)': 12, 'CPU Nice (%)': 10,
        'CPU Idle (%)': 10, 'CPU Iowait (%)': 12, 'CPU Irq (%)': 9, 'CPU Sirq (%)': 10,
        'CPU Host (%)': 10,
        'Memory Total (MB)': 15, 'Memory Used (MB)': 14, 'Memory Free (MB)': 14,
        'Memory Available (MB)': 18, 'Memory Buffers (MB)': 16, 'Memory Cached (MB)': 15, # <--- Larghezza coerente
        'Swap Total (MB)': 13, 'Swap Used (MB)': 12,
        'DEFAULT_THERMAL': 18
    }
    default_w = widths['DEFAULT_THERMAL'] if len(col_name) < 15 else len(col_name) + 2
    width = widths.get(col_name, default_w)

    # Gestione N/A o None
    if value is None or value == 'N/A':
        return f"{'N/A':>{width}}"

    # Formattazione specifica
    formatted_str = "ERR" # Default in caso di errore imprevisto
    try:
        if col_name == 'Timestamp':
             return f"{str(value):<{width}}" # Timestamp allineato a sinistra

        is_delta = col_name.startswith('Δ')
        prec = 0 # Default precisione 0

        # Trova precisione corretta
        if col_name in precision_map:
            prec = precision_map[col_name]
        elif any(cpu_label in col_name for cpu_label in ['CPU', '(%']):
             prec = precision_map['CPU']
        elif any(mem_label in col_name for mem_label in ['Memory', '(MB)']):
             prec = precision_map.get(col_name, 0) # Usa specifica se c'è, altrimenti 0 per MB
        elif isinstance(value, float): # Heuristica per sensori termici o non mappati
             prec = precision_map['DEFAULT_THERMAL']

        # Applica formattazione
        if isinstance(value, (int, float)):
             sign = '+' if is_delta and float(value) > 0 else ''
             if prec == 0:
                 formatted_str = f"{sign}{int(value)}"
             else:
                 formatted_str = f"{sign}{float(value):.{prec}f}"
        else: # Stringhe (es. Capacity con %)
             formatted_str = str(value)

    except (ValueError, TypeError) as e:
         print(f"Warning: Errore formattazione valore '{value}' per colonna '{col_name}': {e}", file=sys.stderr)
         formatted_str = "FMT_ERR"

    # Allinea a destra e aggiungi padding
    return f"{formatted_str:>{width}}"


def collect_data(thermal_sensor_names):
    """Raccoglie tutti i dati abilitati dal dispositivo (Gestione errori migliorata)."""
    data = {'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]} # Millisecondi

    # --- Batteria ---
    current_now_str = get_battery_value("current_now")
    current_avg_str = get_battery_value("current_avg") # Potrebbe non esistere
    voltage_now_str = get_battery_value("voltage_now")
    capacity_str = get_battery_value("capacity")
    temp_celsius = get_battery_temperature() # Già gestisce errori interni

    data['Battery Temp (°C)'] = temp_celsius # Assegna direttamente, può essere None

    # Converti individualmente per isolare errori
    current_ua = None
    current_avg_ua = None
    voltage_uv = None
    capacity_percent = None

    try:
        if current_now_str is not None: current_ua = int(current_now_str)
    except (ValueError, TypeError): print(f"Warning: Valore 'current_now' non valido: {current_now_str}", file=sys.stderr)

    try:
        if current_avg_str is not None and current_avg_str != '0': current_avg_ua = int(current_avg_str)
        else: current_avg_ua = 0 # Default a 0 se assente o 0
    except (ValueError, TypeError): print(f"Warning: Valore 'current_avg' non valido: {current_avg_str}", file=sys.stderr)

    try:
        if voltage_now_str is not None: voltage_uv = int(voltage_now_str)
    except (ValueError, TypeError): print(f"Warning: Valore 'voltage_now' non valido: {voltage_now_str}", file=sys.stderr)

    try:
        if capacity_str is not None: capacity_percent = int(capacity_str)
    except (ValueError, TypeError): print(f"Warning: Valore 'capacity' non valido: {capacity_str}", file=sys.stderr)

    # Assegna valori convertiti o None
    data['Current (mA)'] = current_ua / 1000.0 if current_ua is not None else None
    data['Avg Current (mA)'] = current_avg_ua / 1000.0 if current_avg_ua is not None else None
    data['Voltage (mV)'] = voltage_uv / 1000.0 if voltage_uv is not None else None
    data['Capacity (%)'] = f"{capacity_percent}%" if capacity_percent is not None else None # Aggiungi % per display

    # Calcola Potenza
    if data['Voltage (mV)'] is not None and data['Current (mA)'] is not None:
        try:
            power_w = (data['Voltage (mV)'] / 1000.0) * (data['Current (mA)'] / 1000.0)
            data['Power (W)'] = power_w
        except TypeError: data['Power (W)'] = None
    else: data['Power (W)'] = None


    # --- CPU (se abilitato) ---
    if ENABLE_CPU_MONITORING:
        cpu_data = get_cpu_usage() # Restituisce dict o None
        if cpu_data:
            for key in ['total', 'user', 'system', 'nice', 'idle', 'iowait', 'irq', 'sirq', 'host']:
                 # Mappa le chiavi interne alle chiavi colonna
                 col_key_map = {'system': 'System', 'iowait': 'Iowait', 'sirq': 'Sirq'} # Esempio, aggiusta se serve
                 col_name = f"CPU {col_key_map.get(key, key.capitalize())} (%)"
                 data[col_name] = cpu_data.get(key, 'N/A')
        else: # Errore nel recupero CPU
             for key in ['CPU Total (%)', 'CPU User (%)','CPU System (%)', 'CPU Nice (%)', 'CPU Idle (%)', 'CPU Iowait (%)', 'CPU Irq (%)', 'CPU Sirq (%)', 'CPU Host (%)']:
                 data[key] = 'N/A'


    # --- Memoria (se abilitato) ---
    if ENABLE_MEMORY_MONITORING:
        memory_data = get_memory_usage() # Restituisce dict o None
        # La funzione get_memory_usage ora restituisce sempre un dict con N/A in caso di fallimento
        data['Memory Total (MB)'] = memory_data.get('total_mb', 'N/A')
        data['Memory Used (MB)'] = memory_data.get('used_mb', 'N/A')
        data['Memory Free (MB)'] = memory_data.get('free_mb', 'N/A')
        data['Memory Available (MB)'] = memory_data.get('available_mb', 'N/A')
        data['Memory Buffers (MB)'] = memory_data.get('buffers_mb', 'N/A')
        data['Memory Cached (MB)'] = memory_data.get('cached_mb', 'N/A') # <--- Chiave usata coerentemente
        data['Swap Total (MB)'] = memory_data.get('swap_total_mb', 'N/A')
        data['Swap Used (MB)'] = memory_data.get('swap_used_mb', 'N/A')


    # --- Sensori Termici (se abilitato) ---
    if ENABLE_THERMAL_SENSORS:
        thermal_output = get_temperature_data()
        thermal_readings = parse_temperature_output(thermal_output)
        for sensor_name in thermal_sensor_names:
            data[sensor_name] = thermal_readings.get(sensor_name) # Restituisce None se non trovato

    return data


def calculate_deltas(current_data, previous_data):
    """Calcola le differenze rispetto ai dati precedenti (solo se numerici)."""
    deltas = {}
    if not previous_data or not ENABLE_DELTA_COLUMNS:
        if ENABLE_DELTA_COLUMNS: # Prima iterazione con delta abilitati
             for delta_key in ['ΔCurrent (mA)', 'ΔAvg Current (mA)', 'ΔVoltage (mV)', 'ΔPower (W)']:
                 deltas[delta_key] = None
        return deltas

    for key, delta_key in [('Current (mA)', 'ΔCurrent (mA)'),
                           ('Avg Current (mA)', 'ΔAvg Current (mA)'),
                           ('Voltage (mV)', 'ΔVoltage (mV)'),
                           ('Power (W)', 'ΔPower (W)')]:
        current_val = current_data.get(key)
        previous_val = previous_data.get(key)

        if isinstance(current_val, (int, float)) and isinstance(previous_val, (int, float)):
            try:
                 delta_val = float(current_val) - float(previous_val)
                 deltas[delta_key] = delta_val
            except (ValueError, TypeError): deltas[delta_key] = None
        else: deltas[delta_key] = None
    return deltas


def print_data_to_console(data_snapshot, ordered_chosen_display_columns):
    """Stampa i dati selezionati sulla console."""
    if not ordered_chosen_display_columns: return

    output_parts = []
    for col_name in ordered_chosen_display_columns:
        value = data_snapshot.get(col_name)
        formatted_value = format_value_for_display(value, col_name)
        output_parts.append(formatted_value + " | ")

    print("".join(output_parts))


def log_data_to_csv(csv_writer, data_snapshot, csv_header_order):
    """Scrive una riga di dati nel file CSV nell'ordine specificato."""
    if not csv_writer or not ENABLE_LOGGING: return

    csv_row = []
    for col_name in csv_header_order:
        value = data_snapshot.get(col_name)

        if value is None or value == 'N/A': csv_row.append("N/A")
        elif isinstance(value, float):
            prec = 3 if 'Power' in col_name else \
                   1 if 'Temp' in col_name or any(cpu in col_name for cpu in ['CPU','(%)']) else \
                   0 if any(mem in col_name for mem in ['Memory','(MB)']) else \
                   1 # Default per altri float (termici, delta mA/mV)
            try: csv_row.append(f"{value:.{prec}f}")
            except (ValueError, TypeError): csv_row.append(str(value))
        elif isinstance(value, str) and '%' in value:
            csv_row.append(value.replace('%','')) # Rimuovi % per CSV
        else: csv_row.append(str(value))

    try: csv_writer.writerow(csv_row)
    except Exception as e: print(f"\nErrore durante la scrittura nel CSV: {e}", file=sys.stderr)


# --- Flusso Principale ---

if __name__ == "__main__":
    print("-" * 80)
    print("Script Monitoraggio Dispositivo (Batteria, Termico, CPU, Memoria)")
    print("    Selezione Colonne Display / Logging CSV Completo")
    print("-" * 80)

    # --- Controlli Iniziali ADB ---
    adb_executable = ADB_PATH
    if not os.path.exists(ADB_PATH):
        try:
             # Prova a trovare adb nel PATH
             result = subprocess.run(['which', 'adb'], capture_output=True, text=True, check=True)
             adb_executable = result.stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
             print(f"Errore: Eseguibile ADB non trovato in '{ADB_PATH}' o nel PATH di sistema.", file=sys.stderr)
             print("Verifica il percorso in ADB_PATH o installa ADB e aggiungilo al PATH.")
             sys.exit(1)
    print(f"Usando ADB: {adb_executable}")
    # Aggiorna ADB_PATH per usare quello trovato, se diverso
    if adb_executable != ADB_PATH:
         ADB_PATH = adb_executable


    print("Controllo connessione ADB...")
    devices_output = run_adb_command(["devices"])
    if not devices_output or "List of devices attached" not in devices_output:
         print("\nErrore: Impossibile ottenere l'elenco dei dispositivi ADB.", file=sys.stderr)
         print("Assicurati che ADB funzioni correttamente.")
         sys.exit(1)

    device_lines = devices_output.strip().splitlines()
    if len(device_lines) < 2:
         print("\nErrore: Nessun dispositivo ADB trovato.", file=sys.stderr)
         print("Assicurati che un dispositivo sia connesso, autorizzato e che il debugging USB sia abilitato.")
         sys.exit(1)

    found_device = False
    for line in device_lines[1:]:
        parts = line.split()
        if len(parts) == 2:
             serial, state = parts
             if state == "device":
                 print(f"Trovato dispositivo attivo: {serial}")
                 found_device = True
                 break
             elif state == "unauthorized":
                 print(f"\nErrore: Dispositivo {serial} non autorizzato.", file=sys.stderr)
                 print("Accetta la richiesta di autorizzazione RSA sul tuo dispositivo.")
                 sys.exit(1)
             elif state == "offline":
                 print(f"\nErrore: Dispositivo {serial} offline.", file=sys.stderr)
                 print("Prova a scollegare/ricollegare, riavviare ADB (adb kill-server; adb start-server), o riavviare il dispositivo.")
                 sys.exit(1)
             else: print(f"Trovato dispositivo {serial} con stato sconosciuto: {state}")

    if not found_device:
         print("\nErrore: Nessun dispositivo ADB attivo trovato.")
         sys.exit(1)
    print("Controllo ADB superato.")


    # --- Determinazione Colonne e Scelta Utente ---
    all_possible_columns_for_csv, thermal_names = get_all_available_columns(
        ENABLE_THERMAL_SENSORS, ENABLE_CPU_MONITORING, ENABLE_MEMORY_MONITORING, ENABLE_DELTA_COLUMNS
    )

    chosen_display_columns_ordered = prompt_user_for_display_columns(all_possible_columns_for_csv)

    # --- Preparazione Logging CSV ---
    csv_file = None
    csv_writer = None
    csv_filename = ""
    if ENABLE_LOGGING:
        device_model = get_device_model()
        device_serial = get_device_serial()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_model = sanitize_filename(device_model)
        sanitized_serial = sanitize_filename(device_serial)
        csv_filename = f"log_{sanitized_model}_{sanitized_serial}_{timestamp_str}.csv"

        try:
            csv_file = open(csv_filename, 'w', newline='', encoding='utf-8')
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(all_possible_columns_for_csv) # Header CSV usa TUTTE le colonne
            csv_file.flush()
            print(f"\nLogging CSV abilitato. Dati salvati in: {csv_filename}")
        except IOError as e:
            print(f"\nErrore: Impossibile aprire o scrivere il file CSV '{csv_filename}': {e}", file=sys.stderr)
            ENABLE_LOGGING = False
            csv_file = None
            csv_writer = None

    # --- Stampa Intestazione Console ---
    display_header = build_display_header(chosen_display_columns_ordered) # Header display usa solo colonne scelte
    print("\n" + "=" * (len(display_header) if display_header else 80))
    if display_header:
        print(display_header)
        print("-" * len(display_header))
    else:
        print("Nessuna colonna selezionata per la visualizzazione.")
        if not ENABLE_LOGGING: print("ATTENZIONE: Logging CSV disabilitato e nessuna colonna scelta per la visualizzazione.")


    # --- Ciclo di Monitoraggio ---
    previous_data_snapshot = None
    print(f"\nAvvio monitoraggio... Intervallo: {T_sleep}s. Premi Ctrl+C per fermare.")

    try:
        while True:
            # 1. Raccogli tutti i dati
            current_data_snapshot = collect_data(thermal_names)

            # 2. Calcola Delta
            deltas = calculate_deltas(current_data_snapshot, previous_data_snapshot)
            current_data_snapshot.update(deltas)

            # 3. Stampa sulla console
            print_data_to_console(current_data_snapshot, chosen_display_columns_ordered)

            # 4. Logga su CSV
            if ENABLE_LOGGING and csv_writer:
                log_data_to_csv(csv_writer, current_data_snapshot, all_possible_columns_for_csv)
                if csv_file: csv_file.flush()

            # 5. Salva dati correnti
            previous_data_snapshot = current_data_snapshot

            # 6. Attendi
            time.sleep(T_sleep)

    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente (Ctrl+C). Chiusura...")
    except Exception as e:
        print(f"\nErrore critico nel ciclo principale: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        # --- Pulizia ---
        if csv_file:
            try:
                csv_file.close()
                print(f"File CSV '{csv_filename}' chiuso.")
            except Exception as e: print(f"Errore durante la chiusura del file CSV: {e}", file=sys.stderr)
        print("Script terminato.")