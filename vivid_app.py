import os
import requests
import csv
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import messagebox, ttk, filedialog, simpledialog
from dotenv import load_dotenv
import threading
import time
from datetime import datetime
import glob

load_dotenv()

class VividMasterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vivid Seats Pro: Master Fulfillment Suite v12.0")
        self.root.geometry("1150x950")
        
        self.api_token = os.getenv("VIVID_API_TOKEN", "")
        self.enriched_data = {} 
        self.phase1_results = [] 
        self.current_filename = ""
        self.selected_order_id = None
        self.url_entries = []

        self.setup_ui()
        self.auto_load_existing_csvs()

    def setup_ui(self):
        # --- TOP CONTROL PANEL ---
        self.ctrl_frame = tk.Frame(self.root, pady=10)
        self.ctrl_frame.pack(fill="x", padx=10)

        self.btn_fetch = tk.Button(self.ctrl_frame, text="FETCH DUAL-STATUS & AUTO-SAVE", command=self.start_dual_fetch, 
                                   bg="#27ae60", fg="white", font=("Arial", 9, "bold"))
        self.btn_fetch.pack(side="left", padx=10)

        self.info_label = tk.Label(self.ctrl_frame, text="Ready", fg="blue")
        self.info_label.pack(side="right", padx=10)

        # --- SEARCH & FILTER BAR ---
        self.filter_frame = tk.Frame(self.root, pady=5)
        self.filter_frame.pack(fill="x", padx=10)

        tk.Label(self.filter_frame, text="Search Order ID:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.refresh_table())
        self.ent_search = tk.Entry(self.filter_frame, textvariable=self.search_var, width=20)
        self.ent_search.pack(side="left", padx=5)

        self.today_filter_var = tk.BooleanVar(value=False)
        self.chk_today = tk.Checkbutton(self.filter_frame, text="Today's Events Only", 
                                        variable=self.today_filter_var, command=self.refresh_table)
        self.chk_today.pack(side="left", padx=10)

        self.hide_past_var = tk.BooleanVar(value=True) 
        self.chk_past = tk.Checkbutton(self.filter_frame, text="Hide Past Events", 
                                       variable=self.hide_past_var, command=self.refresh_table)
        self.chk_past.pack(side="left", padx=10)

        # --- PANEL 1: MAIN TABLE ---
        tk.Label(self.root, text="Panel 1: Order History (Retransfers in Yellow)", font=("Arial", 10, "bold")).pack(anchor="w", padx=10)
        self.tree1 = ttk.Treeview(self.root, columns=("id", "event", "date", "qty", "status", "transferable"), show="headings", height=10)
        for col, head in zip(self.tree1["columns"], ["Order ID", "Event", "Event Date", "Qty", "Status", "URL Transfer?"]):
            self.tree1.heading(col, text=head)
            self.tree1.column(col, width=150)
        
        self.tree1.tag_configure('retransfer', background='#ffffcc') 
        self.tree1.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree1.bind("<<TreeviewSelect>>", self.on_order_selected)

        # --- PANEL 2: DETAIL VIEW ---
        tk.Label(self.root, text="Panel 2: Detailed Data (Double-Click to Copy | Hiding Blanks/False)", font=("Arial", 10, "bold")).pack(anchor="w", padx=10)
        self.tree2 = ttk.Treeview(self.root, columns=("field", "value"), show="headings", height=8)
        self.tree2.heading("field", text="Field Name")
        self.tree2.heading("value", text="Value (Double-Click to Copy)")
        self.tree2.column("field", width=200)
        self.tree2.column("value", width=750)
        
        self.tree2.tag_configure('email', background='#e1f5fe') # Soft blue for emails
        
        self.tree2.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree2.bind("<Double-1>", self.copy_to_clipboard) # Enable copy on double click

        # --- PANEL 3: TRANSFER CONSOLE ---
        self.transfer_frame = tk.LabelFrame(self.root, text="Panel 3: Phase 3 - URL Transfer Console", 
                                            font=("Arial", 10, "bold"), fg="#e67e22", pady=10, padx=10)
        self.transfer_frame.pack(fill="x", padx=10, pady=10)

        self.header_row = tk.Frame(self.transfer_frame)
        self.header_row.pack(fill="x")
        tk.Label(self.header_row, text="Selected Order ID:").pack(side="left")
        self.lbl_transfer_id = tk.Label(self.header_row, text="None", font=("Arial", 9, "bold"))
        self.lbl_transfer_id.pack(side="left", padx=5)

        self.btn_add_url = tk.Button(self.header_row, text="+ Add Link", command=self.add_url_field, bg="#34495e", fg="white", font=("Arial", 8))
        self.btn_add_url.pack(side="right", padx=5)

        self.url_container = tk.Frame(self.transfer_frame)
        self.url_container.pack(fill="x", pady=5)

        self.action_row = tk.Frame(self.transfer_frame)
        self.action_row.pack(fill="x")
        self.btn_post_transfer = tk.Button(self.action_row, text="POST ALL LINKS TO VIVID", 
                                          command=self.execute_url_transfer, bg="#e67e22", fg="white", 
                                          font=("Arial", 9, "bold"), state="disabled", pady=5)
        self.btn_post_transfer.pack(side="left", pady=5)
        self.lbl_transfer_status = tk.Label(self.action_row, text="Status: Waiting...", fg="gray")
        self.lbl_transfer_status.pack(side="left", padx=20)

        self.add_url_field()

    def copy_to_clipboard(self, event):
        """Copies the double-clicked value from Panel 2 to system clipboard."""
        item = self.tree2.identify_row(event.y)
        column = self.tree2.identify_column(event.x)
        if item:
            # We want the value (column 2), index 1 in the list
            val = self.tree2.item(item)['values'][1]
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
            self.lbl_transfer_status.config(text=f"Copied to clipboard: {val[:30]}...", fg="#2c3e50")

    def on_order_selected(self, event):
        selected = self.tree1.selection()
        if not selected: return
        vals = self.tree1.item(selected[0])['values']
        self.selected_order_id = str(vals[0])
        self.lbl_transfer_id.config(text=self.selected_order_id)
        self.reset_url_fields()
        
        if vals[5] == "YES (URL)":
            self.btn_post_transfer.config(state="normal")
            self.btn_add_url.config(state="normal")
        else:
            self.btn_post_transfer.config(state="disabled")
            self.btn_add_url.config(state="disabled")

        # Refresh Panel 2 with "Hide Blank/False" logic
        for item in self.tree2.get_children(): self.tree2.delete(item)
        details = self.enriched_data.get(self.selected_order_id) or next((i for i in self.phase1_results if str(i["orderId"]) == self.selected_order_id), None)
        
        if details:
            for k, v in sorted(details.items()):
                # Logic to hide blank/false/null fields
                val_str = str(v).lower().strip()
                if not v or val_str == "" or val_str == "false" or val_str == "none":
                    continue
                
                tag = 'email' if k == 'emailAddress' else ''
                self.tree2.insert("", "end", values=(k, v), tags=(tag,))

    def refresh_table(self):
        for item in self.tree1.get_children():
            self.tree1.delete(item)

        search_query = self.search_var.get().strip().lower()
        filter_today = self.today_filter_var.get()
        filter_past = self.hide_past_var.get()
        today_date = datetime.now().date()
        today_str = today_date.strftime("%Y-%m-%d")

        for data in self.phase1_results:
            order_id = str(data.get("orderId", "")).lower()
            event_date_full = data.get("eventDate", "")
            event_date_only_str = event_date_full.split(" ")[0] if event_date_full else ""
            
            try:
                event_date_obj = datetime.strptime(event_date_only_str, "%Y-%m-%d").date()
            except:
                event_date_obj = None

            matches_search = search_query in order_id
            is_today = event_date_only_str == today_str
            is_past = event_date_obj < today_date if event_date_obj else False

            if matches_search:
                if filter_today and not is_today: continue
                if filter_past and is_past: continue
                self.add_to_tree1(data)

    def start_dual_fetch(self):
        if not self.api_token:
            messagebox.showerror("Error", ".env missing VIVID_API_TOKEN")
            return
        self.btn_fetch.config(state="disabled")
        threading.Thread(target=self.dual_fetch_process, daemon=True).start()

    def dual_fetch_process(self):
        all_new_data = []
        self.root.after(0, lambda: self.info_label.config(text="Pulling Shipments...", fg="orange"))
        all_new_data.extend(self.fetch_helper(self.api_token, "PENDING_SHIPMENT"))
        all_new_data.extend(self.fetch_helper(self.api_token, "PENDING_RETRANSFER"))

        if all_new_data:
            self.auto_save_session(all_new_data)
            self.root.after(0, lambda: self.info_label.config(text=f"Fetched Total: {len(all_new_data)}", fg="blue"))
            threading.Thread(target=self.background_enrichment, args=(self.api_token, all_new_data), daemon=True).start()
        
        time.sleep(5) 
        self.root.after(0, lambda: self.btn_fetch.config(state="normal"))

    def fetch_helper(self, token, status):
        is_retransfer = status == "PENDING_RETRANSFER"
        url = "https://brokers.vividseats.com/webservices/v1/getPendingRetransferOrders" if is_retransfer else "https://brokers.vividseats.com/webservices/v1/getOrders"
        params = {"apiToken": token} if is_retransfer else {"apiToken": token, "status": status}
        try:
            res = requests.get(url, params=params, headers={"Accept": "application/xml"}, timeout=30)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                orders = root.findall("order")
                parsed = []
                for o in orders:
                    data = {child.tag: (child.text.strip() if child.text else "") for child in o}
                    if is_retransfer: data['status'] = "PENDING_RETRANSFER"
                    if not any(d.get('orderId') == data.get("orderId") for d in self.phase1_results):
                        self.phase1_results.append(data)
                        self.root.after(0, self.refresh_table) 
                    parsed.append(data)
                return parsed
        except: return []

    def background_enrichment(self, token, session_data):
        for i, order in enumerate(session_data):
            oid = order.get("orderId")
            url = "https://brokers.vividseats.com/webservices/v1/getOrder"
            try:
                res = requests.get(url, params={"apiToken": token, "orderId": oid}, headers={"Accept": "application/xml"}, timeout=15)
                if res.status_code == 200:
                    root = ET.fromstring(res.content)
                    details = {child.tag: (child.text.strip() if child.text else "") for child in root}
                    self.enriched_data[oid] = details
                    self.root.after(0, self.refresh_table) 
            except: pass

    def add_url_field(self):
        frame = tk.Frame(self.url_container)
        frame.pack(fill="x", pady=2)
        ent = tk.Entry(frame, width=100)
        ent.pack(side="left", padx=5, fill="x", expand=True)
        self.url_entries.append({'frame': frame, 'entry': ent})

    def reset_url_fields(self):
        for item in self.url_entries: item['frame'].destroy()
        self.url_entries = []
        self.add_url_field()

    def execute_url_transfer(self):
        order_id = self.selected_order_id
        details = self.enriched_data.get(order_id)
        final_urls = [item['entry'].get().strip() for item in self.url_entries if item['entry'].get().strip()]
        if not final_urls: return
        payload = {"apiToken": self.api_token, "orderId": order_id, "orderToken": details.get('orderToken', ''),
                   "transferURLList": final_urls, "transferSource": "Vivid_v12", "transferSourceURL": final_urls[0]}
        try:
            res = requests.post("https://brokers.vividseats.com/webservices/v1/transferOrderViaURL", data=payload, headers={"Accept": "application/xml"})
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                self.lbl_transfer_status.config(text=f"SUCCESS: {root.findtext('message')}", fg="green")
                self.reset_url_fields()
        except: pass

    def add_to_tree1(self, data):
        details = self.enriched_data.get(data.get("orderId"), data)
        is_url = "YES (URL)" if details.get('transferViaURL') == 'true' else "Scanning..."
        tag = 'retransfer' if data.get("status") == "PENDING_RETRANSFER" else ''
        self.tree1.insert("", "end", values=(data.get("orderId"), data.get("event"), data.get("eventDate"), data.get("quantity"), data.get("status"), is_url), tags=(tag,))

    def auto_save_session(self, data_list):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"VividOrders_{ts}.csv", "w", newline="", encoding="utf-8") as f:
            headers = set().union(*(d.keys() for d in data_list))
            writer = csv.DictWriter(f, fieldnames=sorted(list(headers)))
            writer.writeheader()
            writer.writerows(data_list)

    def auto_load_existing_csvs(self):
        for file in glob.glob("*.csv"):
            try:
                with open(file, mode='r', encoding='utf-8') as f:
                    for row in csv.DictReader(f):
                        if row.get('orderId') and not any(d.get('orderId') == row['orderId'] for d in self.phase1_results):
                            self.phase1_results.append(row)
                            if len(row) > 10: self.enriched_data[row['orderId']] = row
            except: pass
        self.refresh_table()

if __name__ == "__main__":
    main_root = tk.Tk()
    app = VividMasterApp(main_root)
    main_root.mainloop()
