#!/usr/bin/env python3
import os
import sys
import json
import time
import urllib.request
import urllib.error
import smtplib
from email.mime.text import MIMEText
from concurrent.futures import ThreadPoolExecutor

# --- Feature 1 & 9: Flexible Config Loading ---
def load_servers():
    """
    Loads target URLs from either an environment variable or a local config.json.
    Raises RuntimeError if neither is configured.
    """
    # Check for Option A: Environment Variable
    env_servers = os.environ.get("SERVERS")
    if env_servers:
        # Expected format: "https://url1.com,https://url2.com"
        urls = [url.strip() for url in env_servers.split(",") if url.strip()]
        if urls:
            print(f"Loaded {len(urls)} servers from environment variable.")
            return urls

    # Check for Option B: Config File
    config_filename = "config.json"
    if os.path.isfile(config_filename):
        try:
            with open(config_filename, "r") as f:
                config_data = json.load(f)
                urls = config_data.get("servers", [])
                if not isinstance(urls, list):
                    raise RuntimeError(f"Configuration Error: '{config_filename}' field 'servers' must be a list of URLs.")
                urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
                if urls:
                    print(f"Loaded {len(urls)} servers from config file.")
                    return urls
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to parse {config_filename}: {e}", file=sys.stderr)

    # Error fall-through if nothing is found
    raise RuntimeError("Configuration Error: No servers found. Provide them via SERVERS env var or config.json.")

# --- Feature 2, 3, 4, 5, 6 & 12: Network Probe Logic & Retries ---
def check_single_request(url):
    """
    Performs a single network interaction, calculates execution latency,
    and returns a structured data outcome dictionary.
    """
    # Feature-3: Monotonic CPU clock initialization
    start_time = time.perf_counter()
    status_code = None
    body_content = ""
    error_state = None

    # Configuring a standard User-Agent header to mimic regular clients
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'UptimeMonitorCLI/1.0'}
    )

    try:
        # Default network timeout threshold is set to 5 seconds
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.getcode()
            # Read and decode bytes payload safely
            body_content = response.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        status_code = e.code
    except urllib.error.URLError as e:
        # Handles DNS failures, network connection refusals, and timeouts
        if isinstance(e.reason, TimeoutError) or "timed out" in str(e.reason).lower():
            error_state = "TIMEOUT"
        else:
            error_state = "DOWN"
    except Exception:
        error_state = "DOWN"

    end_time = time.perf_counter()
    duration_ms = int((end_time - start_time) * 1000)

    # --- Feature-4 & 5: Health & Payload Evaluation Rules ---
    status = "DOWN"
    if error_state:
        status = error_state
    elif status_code and (200 <= status_code <= 299):
        status = "OK"
        
        # Feature-5: Deep JSON payload inspection rule
        if body_content:
            try:
                json_payload = json.loads(body_content)
                # If 'status' key exists in JSON payload, it must equal 'ok'
                if "status" in json_payload and str(json_payload["status"]).lower() != "ok":
                    status = "DOWN"
            except json.JSONDecodeError:
                pass # Payload is not JSON or structural format differs; fall back to status code outcome

    # Feature-6: Slow response classification rule threshold (500ms)
    is_slow = (duration_ms > 500) if status == "OK" else False

    return {
        "url": url,
        "status": status,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "is_slow": is_slow
    }

def check_server(url):
    """
    Wrapper handling Feature-12: Retry rules layer.
    """
    max_attempts = 3  # Initial try + 2 retries
    for attempt in range(max_attempts):
        result = check_single_request(url)
        if result["status"] == "OK":
            return result
        
        # If it failed but we have retries left, wait briefly before trying again
        if attempt < max_attempts - 1:
            time.sleep(0.5)
            
    return result

# --- Feature 11: Concurrent Thread Driver Engine ---
def check_all_servers(urls):
    """
    Feature-11: Multi-threaded parallel dispatcher.
    Bypasses GIL bottlenecks during internal network socket polling operations.
    """
    # Max workers bound to 15 to balance concurrency against target socket limits
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(check_server, urls))
    return results

# --- Feature 7: Console Output Structuring ---
def format_result(result):
    """
    Extracts application name domain strings and generates explicit visual readouts.
    """
    # Clean URL down to hostname for consistent standard terminal printing
    display_name = result["url"].replace("https://", "").replace("http://", "").split("/")[0]
    
    if result["status"] == "OK":
        slow_tag = "  [slow]" if result["is_slow"] else ""
        return f"{display_name:<18} — OK ({result['status_code']})    — {result['duration_ms']}ms{slow_tag}"
    elif result["status"] == "TIMEOUT":
        return f"{display_name:<18} — TIMEOUT"
    else:
        code_str = f" ({result['status_code']})" if result["status_code"] else ""
        return f"{display_name:<18} — DOWN{code_str}"

# --- Feature 13: Alert Layer ---
def send_alerts(failed_servers):
    """
    Sends an immediate notification payload if failures occur.
    """
    if not failed_servers:
        return

    # NOTE: Update these configuration variables to connect your real SMTP relay server.
    smtp_server = "smtp.mailtrap.io" 
    smtp_port = 587
    sender_email = "alerts@monitor.internal"
    receiver_email = "sysadmin@yourcompany.com"
    username = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    server_list_str = ", ".join(failed_servers)
    msg_body = f"Alert: The following services are experiencing an outage:\n\n{server_list_str}"
    
    msg = MIMEText(msg_body)
    msg["Subject"] = f"CRITICAL: {len(failed_servers)} Services Outage Detected"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    if not username or not password:
        # Fallback debug mode print statement so it doesn't hard-crash if credentials are empty
        print("\n[Alert System Log]: SMTP credentials missing from env. Skipping network alert dispatch.")
        return

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("\n[Alert System Log]: Email notifications pushed to system administrators.")
    except Exception as e:
        print(f"\n[Alert System Log] Critical Error: Failed to push notification mail data: {e}", file=sys.stderr)


# --- Driver Lifecycle Loop Routine ---
if __name__ == "__main__":
    try:
        urls = load_servers()
    except RuntimeError as err:
        print(err, file=sys.stderr)
        sys.exit(1)

    print("\nRunning parallel service checks...\n")
    
    # Feature-10 & 11: Execute global async worker routines
    results = check_all_servers(urls)
    
    # Feature-8: Track failures for unified reporting block
    failed_services = []

    # Display loop tracking output lines 
    for res in results:
        print(format_result(res))
        
        # If server state is not explicitly "OK", drop hostname into global collection
        if res["status"] != "OK":
            clean_host = res["url"].replace("https://", "").replace("http://", "").split("/")[0]
            failed_services.append(clean_host)

    # Final Summary Blocks
    print("")
    if failed_services:
        print(f"Failed services: {', '.join(failed_services)}")
        # Feature-13: Trigger downstream email alert framework
        send_alerts(failed_services)
    else:
        print("Failed services: None. All endpoints operating within parameters.")