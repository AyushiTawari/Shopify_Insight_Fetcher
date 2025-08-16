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
        faqs JSON,
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
        (brand_url, product_catalog, hero_products, policies,faqs, about, contact, socials, important_links)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """

        cursor.execute(query, (
            data["brand_url"],
            json.dumps(data["product_catalog"]),
            json.dumps(data["hero_products"]),
            json.dumps(data["policies"]),
            json.dumps(data["faqs"]),
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
def extract_faqs(html):
    faqs = []
    soup = BeautifulSoup(html, "html.parser")
    questions = soup.find_all(string=lambda text: text and text.strip().endswith("?"))
    for q in questions:
        question_text = q.strip()
        answer_tag = None
        if q.parent:
            answer_tag = q.parent.find_next_sibling(["p", "div"])
        answer_text = answer_tag.get_text(" ", strip=True) if answer_tag else ""
        faqs.append({"question": question_text, "answer": answer_text})
    faq_sections = soup.find_all(
        lambda tag: tag.name in ["div", "section"]
        and (
            "faq" in (tag.get("id") or "").lower()
            or any("faq" in c.lower() for c in (tag.get("class") or []))
        )
    )
    for section in faq_sections:
        questions = section.find_all(["h2", "h3", "h4", "button", "strong", "summary"])
        for q in questions:
            question_text = q.get_text(" ", strip=True)
            if not question_text:
                continue
            answer_tag = q.find_next_sibling(["p", "div"])
            if answer_tag:
                answer_text = answer_tag.get_text(" ", strip=True)
                if answer_text:
                    faqs.append({"question": question_text, "answer": answer_text})

    for d in soup.find_all("details"):
        q = d.find("summary")
        a = d.find("p") or d.find("div")
        if q and a:
            faqs.append({"question": q.get_text(" ", strip=True), "answer": a.get_text(" ", strip=True)})

    for btn in soup.find_all("button"):
        if "faq" in (btn.get("class") or []) or "faq" in btn.get_text(" ", strip=True).lower():
            q = btn.get_text(" ", strip=True)
            a = btn.find_next_sibling("div")
            if a:
                faqs.append({"question": q, "answer": a.get_text(" ", strip=True)})

    return faqs


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

        hero_products = [a.get_text(strip=True) for a in soup.select("a[href*='/products/']")[:5]]

        policies = {}
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            if "privacy" in href:
                policies["Privacy Policy"] = urljoin(website_url, link["href"])
            elif "return" in href or "refund" in href:
                policies["Return/Refund Policy"] = urljoin(website_url, link["href"])
            elif "policy" in href:
                policies[link.get_text(strip=True) or "Policy"] = urljoin(website_url, link["href"])

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

        faqs = extract_faqs(html)

        result = {
            "brand_url": website_url,
            "product_catalog_count": len(products),
            "product_catalog": [p["title"] for p in products],
            "hero_products": hero_products,
            "policies": policies,
            "faqs": faqs,
            "about": about_text,
            "socials": socials,
            "important_links": footer_links,
            "contact": contact  
        }

        save_to_db(result)
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()   
    app.run(debug=True, port=5000)

