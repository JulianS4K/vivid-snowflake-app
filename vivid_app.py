import os
import requests
import csv
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from dotenv import load_dotenv

# Load API Token from .env file
load_dotenv()

class VividSeatsDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Vivid Seats Pro Order Porter")
        self.root.geometry("480x400")
        self.root.configure(padx=20, pady=20)

        # --- UI Setup ---
        tk.Label(root, text="Vivid Seats API Token", font=("Arial", 9, "bold")).pack(anchor="w")
        self.token_entry = tk.Entry(root, width=50)
        self.token_entry.pack(pady=(0, 15), fill="x")
        
        # Load default from .env
        env_token = os.getenv("VIVID_API_TOKEN")
        if env_token:
            self.token_entry.insert(0, env_token)

        tk.Label(root, text="Order Status to Fetch", font=("Arial", 9, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="PENDING_SHIPMENT")
        statuses = ["UNCONFIRMED", "PENDING_SHIPMENT", "COMPLETED", "VERIFICATION", "PENDING_RESERVATION"]
        self.status_combo = ttk.Combobox(root, textvariable=self.status_var, values=statuses, state="readonly")
        self.status_combo.pack(pady=(0, 20), fill="x")

        self.btn_fetch = tk.Button(
            root, text="DOWNLOAD & SAVE CSV", 
            command=self.run_process, 
            bg="#2c3e50", fg="white", font=("Arial", 10, "bold"), pady=10
        )
        self.btn_fetch.pack(fill="x")

        self.log_label = tk.Label(root, text="Ready to fetch", fg="gray", pady=10)
        self.log_label.pack()

    def run_process(self):
        token = self.token_entry.get().strip()
        status = self.status_var.get()

        if not token:
            messagebox.showwarning("Missing Token", "Please enter your API token.")
            return

        self.log_label.config(text="Contacting Vivid Seats...", fg="blue")
        self.root.update_idletasks()

        url = "https://brokers.vividseats.com/webservices/v1/getOrders"
        params = {"apiToken": token, "status": status}
        headers = {"Accept": "application/xml"}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                self.parse_and_save(response.content)
            elif response.status_code == 429:
                messagebox.showerror("Rate Limit", "Too many requests. Please wait 60 seconds for PENDING_SHIPMENT.")
            else:
                messagebox.showerror("API Error", f"HTTP {response.status_code}\nCheck your token or connection.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        
        self.log_label.config(text="Ready", fg="gray")

    def parse_and_save(self, xml_data):
        try:
            root = ET.fromstring(xml_data)
            orders_list = root.findall("order")

            if not orders_list:
                messagebox.showinfo("No Data", "No orders were found for this status.")
                return

            # 1. Identify all possible columns (Dynamic Header Detection)
            # This ensures that if some orders have 'firstName' and others don't, 
            # the CSV will still have the 'firstName' column.
            all_fields = set()
            parsed_orders = []

            for order in orders_list:
                order_data = {}
                for child in order:
                    tag = child.tag
                    # Flatten the seats array
                    if tag == 'seats':
                        seat_values = [s.text.strip() for s in child.findall('seat') if s.text]
                        val = ", ".join(seat_values)
                    else:
                        val = child.text.strip() if child.text else ""
                    
                    order_data[tag] = val
                    all_fields.add(tag)
                parsed_orders.append(order_data)

            # Sort headers so they appear consistently (optional)
            headers = sorted(list(all_fields))

            # 2. Save Dialog
            save_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv")],
                title="Save Report As"
            )

            if not save_path:
                return

            # 3. Write CSV
            with open(save_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(parsed_orders)

            messagebox.showinfo("Success", f"Successfully saved {len(parsed_orders)} orders to CSV.")

        except ET.ParseError:
            messagebox.showerror("Parse Error", "The server returned invalid XML data.")
        except Exception as e:
            messagebox.showerror("File Error", f"Failed to save file: {e}")

if __name__ == "__main__":
    main_root = tk.Tk()
    app = VividSeatsDownloader(main_root)
    main_root.mainloop()
