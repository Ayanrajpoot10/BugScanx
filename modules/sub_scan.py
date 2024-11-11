import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading
import requests
from colorama import Fore, Style, Back, init
import socket

init(autoreset=True)  # Initialize colorama for cross-platform terminal colors
file_write_lock = threading.Lock()  # Lock for thread-safe file writing

DEFAULT_TIMEOUT1 = 5  # Default timeout for HTTP requests
EXCLUDE_LOCATIONS = ["https://jio.com/BalanceExhaust", "http://filter.ncell.com.np/nc"]  # URLs to exclude from results

# Clear the screen based on the OS
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# Function to get user input with an optional default value
def get_input(prompt, default=None):
    response = input(prompt + Style.BRIGHT).strip()
    print(Style.RESET_ALL)
    return response if response else default or ""

# Function to extract hostnames from a file, ignoring empty lines
def get_hosts_from_file(file_path):
    path = Path(file_path)
    if path.is_file():
        try:
            return [line.strip() for line in path.read_text().splitlines() if line.strip()]
        except Exception as e:
            print(Fore.RED + f"Error reading file: {e}")
    return []  # Return an empty list if file reading fails or file is not found

# Function to ask for the HTTP method, defaulting to HEAD if not provided
def get_http_method():
    methods = ['GET', 'POST', 'PATCH', 'OPTIONS', 'PUT', 'DELETE', 'TRACE', 'HEAD']
    print(Fore.LIGHTCYAN_EX + Style.BRIGHT + "🌐 Available HTTP methods: " + ", ".join(methods))
    method = get_input(Fore.CYAN+"\n↪ Select an HTTP method (default: HEAD): ", "HEAD").upper()
    return method if method in methods else "HEAD"  # Validate and return the chosen method

# Function to manage file navigation and selection (can go up directories)
def file_manager(start_dir, max_up_levels=None, max_invalid_attempts=3):
    current_dir = start_dir
    levels_up = 0
    directory_stack = [start_dir]  # Stack to keep track of the navigation history
    invalid_attempts = 0  # Track invalid attempts to prevent infinite loop

    while True:
        # List .txt files and directories in the current directory
        files_in_directory = [f for f in current_dir.iterdir() if f.is_file() and f.suffix == '.txt']
        directories_in_directory = [d for d in current_dir.iterdir() if d.is_dir()]

        # Display message if no files or directories are found
        if not files_in_directory and not directories_in_directory:
            print(Fore.RED + "⚠️  No .txt files or directories found.")
            return None

        # Display files and directories in a two-column layout for better readability
        print(Fore.CYAN + f"\n📂 Contents of '{current_dir}':")
        combined_items = directories_in_directory + files_in_directory  # Combine files and directories
        half = math.ceil(len(combined_items) / 2)

        # Split items into two columns
        for i in range(half):
            left_item = combined_items[i]
            left_prefix = "📁 " if left_item.is_dir() else "📄 "
            left_name = f"{Fore.YELLOW + Style.BRIGHT if left_item.is_dir() else Fore.WHITE}{left_item.name}{Style.RESET_ALL}"
            left = f"{i + 1}. {left_prefix}{left_name}"

            right = ""
            if i + half < len(combined_items):
                right_item = combined_items[i + half]
                right_prefix = "📁 " if right_item.is_dir() else "📄 "
                right_name = f"{Fore.YELLOW + Style.BRIGHT if right_item.is_dir() else Fore.WHITE}{right_item.name}{Style.RESET_ALL}"
                right = f"{i + half + 1}. {right_prefix}{right_name}"

            print(f"{left:<50} {right}")

        # Display an option to move up a directory
        print(Fore.LIGHTBLUE_EX +"\n0. " + Fore.LIGHTBLUE_EX + " ↑ Move up a directory" + Style.RESET_ALL)

        # Prompt the user for a file or directory selection
        file_selection = get_input(Fore.CYAN + " ➜  Enter the number or filename (e.g., 1 or domain.txt): ").strip()

        # Check if input is '0' to move up
        if file_selection == '0':
            if max_up_levels is not None and levels_up >= max_up_levels:
                print(Fore.RED + "⚠️ You've reached the maximum level above the start directory.")
            elif current_dir.parent == current_dir:
                print(Fore.RED + "⚠️ You are at the root directory and cannot move up further.")
            else:
                current_dir = current_dir.parent  # Move up one level
                levels_up += 1
                continue

        try:
            # Check if input is a valid directory or file index
            file_index = int(file_selection) - 1
            if file_index < 0 or file_index >= len(combined_items):
                raise IndexError
            selected_item = combined_items[file_index]

            # Navigate into selected directory
            if selected_item.is_dir():
                directory_stack.append(current_dir)  # Save the current directory before moving
                current_dir = selected_item
                levels_up = 0  # Reset level count when entering a subdirectory
                txt_files = [f for f in current_dir.iterdir() if f.is_file() and f.suffix == '.txt']
                sub_dirs = [d for d in current_dir.iterdir() if d.is_dir()]
                
                if not txt_files and not sub_dirs:
                    print(Fore.RED + "⚠️ No .txt files or directories found in this directory. Returning to previous directory.")
                    current_dir = directory_stack.pop()  # Return to the previous directory
                continue
            else:
                return selected_item  # Return the selected .txt file
        except (ValueError, IndexError):
            # Handle invalid input or if file is not found
            file_input = current_dir / file_selection

            if file_input.is_file() and file_input.suffix == '.txt':
                return file_input  # Return the selected .txt file
            else:
                print(Fore.RED + f"⚠️  File '{file_input}' not found or not a .txt file. Please try again.")
                invalid_attempts += 1

        # Exit file manager after too many invalid attempts
        if invalid_attempts >= max_invalid_attempts:
            print(Fore.RED + "⚠️ Too many invalid attempts. Returning to the main menu.")
            return None

# Function to get scan inputs such as hosts, ports, and other configuration details
def get_scan_inputs():
    start_dir = Path('.').resolve()  # Set the starting directory for file manager
    selected_file = file_manager(start_dir, max_up_levels=3)  # Call the file manager

    if not selected_file:
        print(Fore.RED + "⚠️ No valid file selected. Returning to main menu.")
        return None, None, None, None, None

    hosts = get_hosts_from_file(selected_file)
    if not hosts:
        print(Fore.RED + "⚠️ No valid hosts found in the file.")
        return None, None, None, None, None

    # Additional inputs for ports, output file, threads, and HTTP method
    ports_input = get_input(Fore.CYAN + "➜ Enter port list (default: 80): ", "80").strip()
    ports = ports_input.split(',') if ports_input else ["80"]
    output_file = get_input(Fore.CYAN + "➜ Enter output file name (default: results_inputfile.txt): ", f"results_{selected_file.name}").strip()
    output_file = output_file or f"results_{selected_file.name}"
    threads = int(get_input(Fore.CYAN + "➜ Enter number of threads (default: 50): ", "50") or "50")
    http_method = get_http_method()
    return hosts, ports, output_file, threads, http_method

# Function to format the results for printing in the output
def format_row(code, server, port, ip_address, host, use_colors=True):
    return (f"{Fore.GREEN if use_colors else ''}{code:<4} " +
            f"{Fore.CYAN if use_colors else ''}{server:<20} " +
            f"{Fore.YELLOW if use_colors else ''}{port:<5} " +
            f"{Fore.MAGENTA if use_colors else ''}{ip_address:<15} " +
            f"{Fore.LIGHTBLUE_EX if use_colors else ''}{host}")

# Function to check HTTP response status for a given host and port
def check_http_response(host, port, method):
    url = f"{'https' if port in ['443', '8443'] else 'http'}://{host}:{port}"
    try:
        response = requests.request(method, url, timeout=DEFAULT_TIMEOUT1, allow_redirects=True)
        if any(exclude in response.headers.get('Location', '') for exclude in EXCLUDE_LOCATIONS):
            return None  # Exclude if the response location matches the exclude list
        return response.status_code, response.headers.get('Server', 'N/A')
    except requests.RequestException:
        return None  # Return None if there's an exception during the request

# Function to get the IP address from a host, returns 'N/A' on failure
def get_ip_from_host(host):
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return "N/A"  # Return 'N/A' if there's an error in resolving the host

# Function to format elapsed time into minutes and seconds or just seconds
def format1_time(elapsed_time):
    return f"{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s" if elapsed_time >= 60 else f"{elapsed_time:.2f}s"

# Function to perform the scan using HTTP method for each host and port combination
def perform_scan(hosts, ports, output_file, threads, method):
    clear_screen()  # Clear the terminal screen before starting the scan
    print(Fore.LIGHTGREEN_EX + f"🔍 Scanning using HTTP method: {method}...\n")

    # Header for the scan results table
    headers = Fore.GREEN + Style.BRIGHT + "Code  " + Fore.CYAN + "Server               " + \
              Fore.YELLOW + "Port   " + Fore.MAGENTA + "IP Address     " + Fore.LIGHTBLUE_EX + "Host" + Style.RESET_ALL
    separator = "-" * 65  # Separator line for the result table

    # Check and prepare the output file for saving results
    try:
        existing_lines = Path(output_file).is_file() and sum(1 for _ in open(output_file, 'r'))
        with open(output_file, 'a') as file:
            if not existing_lines:  # Write headers to the file if it's empty
                file.write(f"{headers}\n{separator}\n")
    except Exception as e:
        print(Fore.RED + f"Error opening output file: {e}")
        return  # Exit the scan if file cannot be opened

    # Display headers in the terminal
    print(headers, separator, sep='\n')

    start_time = time.time()  # Start the timer for elapsed time tracking
    total_hosts, scanned_hosts, responded_hosts = len(hosts) * len(ports), 0, 0  # Track total, scanned, and responded hosts

    # Use ThreadPoolExecutor to manage concurrent HTTP requests for scanning
    with ThreadPoolExecutor(max_workers=threads) as executor:
        # Submit all host-port combinations for scanning
        futures = [executor.submit(check_http_response, host, port, method) for host in hosts for port in ports]
        
        for future in as_completed(futures):  # Process each future as it completes
            scanned_hosts += 1  # Increment the count of scanned hosts
            try:
                # Wait for the result from the future with a small timeout buffer
                result = future.result(timeout=DEFAULT_TIMEOUT1 + 1)
                
                if result:  # If a result is received, increment responded_hosts
                    responded_hosts += 1
                    row = format_row(*result)  # Format the result into a table row
                    print(row)  # Print the row to the terminal
                    
                    # Write results to the output file with thread-safe access
                    with file_write_lock:
                        with open(output_file, 'a') as file:
                            file.write(format_row(*result, use_colors=False) + "\n")
            except requests.exceptions.RequestException as e:
                print(Fore.RED + f"Request error on host {hosts}:{ports} - {e}")  # Handle request-specific errors
            except Exception as e:
                print(Fore.RED + f"Error in scan for host {hosts}:{ports} - {e}")  # Handle general scan errors

            # Display scan progress in real-time, updating on the same line
            elapsed_time = time.time() - start_time
            print(Style.BRIGHT + f"Scanned {scanned_hosts}/{total_hosts} - Responded: {responded_hosts} - Elapsed: {format1_time(elapsed_time)}", end='\r')

    print(f"\n\n{Fore.GREEN}✅ Scan completed! Results saved to {output_file}.")  # Completion message