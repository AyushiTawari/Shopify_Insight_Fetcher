from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import mysql.connector
import json
from mysql.connector import Error
from urllib.parse import urljoin
app = Flask(__name__)
app.secret_key = "mykey"
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='jain@2022',
            port=3307
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS shopify")
    cursor.execute(f"USE shopify")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS brand (
        id INT AUTO_INCREMENT PRIMARY KEY,
        brand_url VARCHAR(255) NOT NULL,
        product_catalog JSON,
        hero_products JSON,
        policies JSON,
        about TEXT,
        contact JSON,
        socials JSON,
        important_links JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    cursor.close()
    conn.close()
def save_to_db(data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"USE shopify")
        query = """
        INSERT INTO brand 
        (brand_url, product_catalog, hero_products, policies, about, contact, socials, important_links)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """

        cursor.execute(query, (
            data["brand_url"],
            json.dumps(data["product_catalog"]),
            json.dumps(data["hero_products"]),
            json.dumps(data["policies"]),
            data["about"],
            json.dumps(data["contact"]),
            json.dumps(data["socials"]),
            json.dumps(data["important_links"])
        ))

        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print("DB Error:", e)
        return False
def extract_social_links(html):
    socials = {}
    patterns = {
        "instagram": r"(https?:\/\/(www\.)?instagram\.com\/[A-Za-z0-9_.-]+)",
        "facebook": r"(https?:\/\/(www\.)?facebook\.com\/[A-Za-z0-9_.-]+)",
        "tiktok": r"(https?:\/\/(www\.)?tiktok\.com\/@[A-Za-z0-9_.-]+)",
        "twitter": r"(https?:\/\/(www\.)?twitter\.com\/[A-Za-z0-9_.-]+)",
        "linkedin": r"(https?:\/\/(www\.)?linkedin\.com\/company\/[A-Za-z0-9_.-]+)"
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, html)
        if match:
            socials[name] = match.group(1)
    return socials

def extract_emails_phones(html):
    emails = list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}", html)))
    phones = list(set(re.findall(r"\+?\d[\d\-\s]{7,}\d", html)))
    return {"emails": emails, "phones": phones}

def fetch_products_json(base_url):
    try:
        r = requests.get(base_url.rstrip("/") + "/products.json", timeout=10)
        if r.status_code == 200:
            return r.json().get("products", [])
    except:
        return []
    return []

# ---------- Flask Route ----------
@app.route("/fetch_insights", methods=["GET"])
def fetch_insights():
    website_url = request.args.get("website_url")
    if not website_url:
        return jsonify({"error": "Missing website_url parameter"}), 400

    try:
        resp = requests.get(website_url, timeout=10)
        if resp.status_code != 200:
            return jsonify({"error": "Website not accessible"}), 401

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        products = fetch_products_json(website_url)

        hero_products = []
        for a in soup.select("a[href*='/products/']")[:5]:
            hero_products.append(a.get_text(strip=True))

        policies = {}
        for link in soup.find_all("a", href=True):
            if any(k in link["href"].lower() for k in ["policy", "return", "refund", "privacy"]):
                policies[link.get_text(strip=True)] = urljoin(website_url, link["href"])

        about_text = ""
        about_page = soup.find("a", href=True, string=re.compile("About", re.I))
        if about_page:
            try:
                about_resp = requests.get(urljoin(website_url, about_page["href"]), timeout=10)
                about_soup = BeautifulSoup(about_resp.text, "html.parser")
                about_text = about_soup.get_text(" ", strip=True)[:500]
            except:
                pass

        contact = extract_emails_phones(html)
        socials = extract_social_links(html)
        footer_links = [urljoin(website_url, a["href"]) for a in soup.select("footer a[href]")]

        result = {
            "brand_url": website_url,
            "product_catalog_count": len(products),
            "product_catalog": [p["title"] for p in products],
            "hero_products": hero_products,
            "policies": policies,
            "about": about_text,
            "contact": contact,
            "socials": socials,
            "important_links": footer_links
        }
        save_to_db(result)

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()   
    app.run(debug=True, port=5000)
