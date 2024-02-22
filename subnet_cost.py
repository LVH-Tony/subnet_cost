import smtplib
import time
import logging
import subprocess
import re
import json
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables and the app_password
load_dotenv()
APP_PASSWORD = os.getenv("APP_PASSWORD")

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Forecasted alert times
forecasted_times = {
    559: datetime(2024, 2, 23, 12, 57, 21),
    400: datetime(2024, 2, 24, 5, 13, 26),
    300: datetime(2024, 2, 24, 15, 27, 19),
}


def send_email_alert(cost, threshold, reason):
    sender_email = "tony.leviethung@gmail.com"
    receiver_email = "hung.le@aitprotocol.ai"
    password = APP_PASSWORD

    message = MIMEMultipart("alternative")
    message["Subject"] = "Subnet Lock Cost Alert"
    message["From"] = sender_email
    message["To"] = receiver_email

    text = f"Alert: {reason} Current value: τ{cost}"
    part = MIMEText(text, "plain")
    message.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
            logging.info("Email alert sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")


def get_subnet_lock_cost():
    try:
        result = subprocess.run(
            ["btcli", "subnet", "lock_cost"], capture_output=True, text=True
        )
        output = result.stdout
        if result.stderr or result.returncode != 0:
            logging.error(f"Command execution failed: {result.stderr}")
            return None

        match = re.search(r"Subnet lock cost: τ([\d.]+)", output)
        if match:
            cost = float(match.group(1))
            logging.info(f"Retrieved subnet lock cost: τ{cost}")
            return cost
        else:
            logging.warning("Failed to parse subnet lock cost from command output.")
            return None
    except Exception as e:
        logging.error(f"Exception occurred when retrieving subnet lock cost: {e}")
        return None


def write_to_json_file(data, file_path="cost_log.json"):
    # Check if file exists, load it, and update; otherwise, create a new list
    if os.path.isfile(file_path):
        with open(file_path, "r") as file:
            logs = json.load(file)
    else:
        logs = []

    logs.append(data)

    with open(file_path, "w") as file:
        json.dump(logs, file, indent=4, default=str)


def monitor():
    alerted_for = set()  # Keep track of the alerts that have been sent
    forecasted_alerted_for = (
        set()
    )  # Keep track of the forecasted alerts that have been sent
    last_cost = None
    
    while True:
        now = datetime.now()
        cost = get_subnet_lock_cost()

        # Log the cost and time to JSON
        if cost is not None:
            cost_data = {"time": now, "cost": cost}
            write_to_json_file(cost_data)
            
            # Check for price jump
            if last_cost is not None and cost > last_cost:
                price_jump = cost - last_cost
                # Define your threshold for what you consider a significant jump, e.g., τ10
                if price_jump >= 10:  # Threshold for alerting a price jump
                    send_email_alert(
                        cost,
                        last_cost,
                        f"Significant price jump detected: from τ{last_cost} to τ{cost}."
                    )

            last_cost = cost  # Update the last checked cost for the next iteration

        # Check against forecasted alert times
        for threshold, alert_time in forecasted_times.items():
            if now >= alert_time and threshold not in forecasted_alerted_for:
                send_email_alert(
                    cost,
                    threshold,
                    f"Forecasted time for price below τ{threshold} has been reached.",
                )
                forecasted_alerted_for.add(threshold)

        # Check against dynamic price thresholds
        if cost is not None:
            for threshold in [550, 400, 300]:
                if cost <= threshold and threshold not in alerted_for:
                    send_email_alert(
                        cost,
                        threshold,
                        f"Subnet lock cost has dropped below τ{threshold}.",
                    )
                    alerted_for.add(threshold)
                else:
                    logging.info(
                        f"Subnet lock cost is τ{cost}, not below τ{threshold}."
                    )
        else:
            logging.error("Failed to retrieve cost or parse the output.")

        # Ensure we don't send a forecast alert if we have already alerted for that price threshold
        alerted_for = alerted_for.union(forecasted_alerted_for)

        logging.info("Sleeping for 5 minutes...")
        time.sleep(600)


if __name__ == "__main__":
    monitor()
