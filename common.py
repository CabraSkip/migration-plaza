from datetime import datetime

def write_log(message, color="white"):
    color_codes = {"red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m", "cyan": "\033[96m", "white": "\033[0m"}
    print(f"{color_codes.get(color, '')}{message}{color_codes['white']}")
    
    with open("DuplicateInfra.log", "a") as log_file:
        log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")