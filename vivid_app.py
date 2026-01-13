import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import snowflake.connector

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Vivid Seats Manager")
st.title("🎫 Vivid Seats to Snowflake (Cloud)")

# --- CREDENTIALS HANDLING ---
# This checks if you have saved your passwords in Streamlit Secrets.
# If yes, it uses them. If no, it asks you to type them in.
secrets = st.secrets.get("snowflake", {})
vivid_secret = st.secrets.get("vivid", {})

with st.sidebar:
    st.header("1. Snowflake Login")
    
    if "user" in secrets:
        st.success("✅ Credentials loaded from Secrets")
        sf_user = secrets["user"]
        sf_pass = secrets["password"]
        sf_account = secrets["account"]
    else:
        sf_user = st.text_input("Username")
        sf_pass = st.text_input("Password", type="password")
        sf_account = st.text_input("Account ID (e.g., xy12345.us-east-1)")
    
    st.divider()
    
    st.header("2. Vivid Seats")
    if "token" in vivid_secret:
        st.success("✅ Vivid Token loaded")
        vivid_token = vivid_secret["token"]
    else:
        vivid_token = st.text_input("Vivid API Token", type="password")
    
    test_mode = st.checkbox("🛠 Enable Test Mode", value=False)

# --- FUNCTIONS ---
def parse_vivid_xml(xml_string):
    try:
        root = ET.fromstring(xml_string)
        orders_data = []
        for order in root.findall('order'):
            def get_val(tag):
                node = order.find(tag)
                return node.text.strip() if node is not None and node.text else None

            orders_data.append({
                "ORDER_ID": get_val('orderId'),
                "STATUS": get_val('status'),
                "COST": get_val('cost'),
                "EVENT_NAME": get_val('event'),
                "EVENT_DATE": get_val('eventDate'),
                "QUANTITY": get_val('quantity'),
                "SECTION": get_val('section'),
                "ROW_NAME": get_val('row'),
                "VENUE": get_val('venue'),
                "FIRST_NAME": get_val('firstName'),
                "LAST_NAME": get_val('lastName'),
                "EMAIL_ADDRESS": get_val('emailAddress')
            })
        return pd.DataFrame(orders_data)
    except Exception as e:
        st.error(f"Error parsing XML: {e}")
        return pd.DataFrame()

def upload_to_snowflake(df, user, password, account):
    try:
        conn = snowflake.connector.connect(
            user=user,
            password=password,
            account=account,
            warehouse='COMPUTE_WH',
            database='VIVID_SEATS_DB',
            schema='RAW_DATA'
        )
        cur = conn.cursor()
        
        success_count = 0
        progress_bar = st.progress(0)
        
        for index, row in df.iterrows():
            sql = f"""
            INSERT INTO ORDERS_Flat 
            (ORDER_ID, STATUS, COST, EVENT_NAME, EVENT_DATE, QUANTITY, SECTION, ROW_NAME, VENUE, FIRST_NAME, LAST_NAME, EMAIL_ADDRESS)
            VALUES 
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(sql, (
                row['ORDER_ID'], row['STATUS'], row['COST'], row['EVENT_NAME'], 
                row['EVENT_DATE'], row['QUANTITY'], row['SECTION'], row['ROW_NAME'], 
                row['VENUE'], row['FIRST_NAME'], row['LAST_NAME'], row['EMAIL_ADDRESS']
            ))
            success_count += 1
            progress_bar.progress((index + 1) / len(df))
            
        conn.commit()
        cur.close()
        conn.close()
        return success_count
    except Exception as e:
        st.error(f"Snowflake Connection Failed: {e}")
        return 0

# --- MAIN APP ---
col1, col2 = st.columns(2)
with col1:
    target_status = st.selectbox("Order Status", ["PENDING_SHIPMENT", "UNCONFIRMED", "COMPLETED"])

if st.button("🚀 Fetch Orders"):
    if test_mode:
        st.warning("⚠️ Using Fake Data")
        fake_xml = """<orders><order><orderId>12345678</orderId><status>PENDING_SHIPMENT</status><cost>150.00</cost><event>Test Event</event><eventDate>2026-05-20</eventDate><quantity>2</quantity><section>100</section><row>A</row><venue>SoFi</venue><firstName>John</firstName><lastName>Doe</lastName><emailAddress>test@example.com</emailAddress></order></orders>"""
        df = parse_vivid_xml(fake_xml)
        st.session_state['df'] = df
        st.success("Loaded Test Data")
    elif not vivid_token:
        st.warning("Please enter Vivid Token")
    else:
        try:
            url = "https://brokers.vividseats.com/webservices/v1/getOrders"
            params = {'apiToken': vivid_token, 'status': target_status}
            with st.spinner("Calling API..."):
                response = requests.get(url, params=params)
            if response.status_code == 200:
                df = parse_vivid_xml(response.text)
                if not df.empty:
                    st.session_state['df'] = df
                    st.success(f"Found {len(df)} orders!")
                else:
                    st.warning("No orders found.")
            elif response.status_code == 429:
                st.error("⛔ Rate Limit Hit. Wait 60 seconds.")
            else:
                st.error(f"API Error: {response.status_code}")
        except Exception as e:
            st.error(f"Connection Error: {e}")

if 'df' in st.session_state:
    st.dataframe(st.session_state['df'], use_container_width=True)
    if st.button("❄️ Upload to Snowflake"):
        if not sf_user or not sf_pass:
            st.error("Missing Snowflake Credentials")
        else:
            with st.spinner("Uploading..."):
                count = upload_to_snowflake(st.session_state['df'], sf_user, sf_pass, sf_account)
                if count > 0:
                    st.balloons()
                    st.success("Success!")