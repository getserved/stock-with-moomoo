import json
import os
import time
import urllib.request
import gzip
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "ai-stock-screener" / "src" / "data" / "apiSnapshot.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "stock-with-moomoo local research contact@example.com")
MATERIAL_FORMS = {
    "8-K",
    "8-K/A",
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
    "6-K",
    "20-F",
    "20-F/A",
    "40-F",
    "S-1",
    "S-1/A",
    "S-3",
    "S-3/A",
    "F-1",
    "F-1/A",
    "F-3",
    "F-3/A",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "424B7",
    "EFFECT",
    "NT 10-Q",
    "NT 10-K",
    "DEF 14A",
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
    "4",
}


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(request, timeout=20) as response:
        content = response.read()
        encoding = response.headers.get("Content-Encoding", "")
        if encoding == "gzip":
            content = gzip.decompress(content)
        elif encoding == "deflate":
            content = zlib.decompress(content)
        return json.loads(content.decode("utf-8"))


def normalize_ticker(ticker):
    return ticker.upper().replace(".", "-")


def load_cik_map():
    payload = fetch_json(SEC_TICKERS_URL)
    result = {}
    for item in payload.values():
        ticker = normalize_ticker(str(item.get("ticker", "")))
        cik = str(item.get("cik_str", "")).zfill(10)
        if ticker and cik:
            result[ticker] = cik
    return result


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def classify_form(form):
    if form.startswith("8-K") or form == "6-K":
        return "重大事件公告"
    if form in {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F"}:
        return "财报/年报"
    if form.startswith(("S-", "F-", "424B")) or form == "EFFECT":
        return "融资/增发相关"
    if form.startswith("NT "):
        return "延迟申报风险"
    if form in {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}:
        return "大股东持仓变动"
    if form == "4":
        return "内部人交易"
    return "SEC公告"


def sec_document_url(cik, accession, document):
    if not accession or not document:
        return ""
    cik_int = str(int(cik))
    accession_path = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_path}/{document}"


def recent_material_filings(cik, lookback_days):
    payload = fetch_json(SEC_SUBMISSIONS_URL.format(cik=cik))
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])
    cutoff = date.today() - timedelta(days=lookback_days)
    events = []
    for index, form in enumerate(forms):
        filing_date = parse_date(filing_dates[index] if index < len(filing_dates) else None)
        if not filing_date or filing_date < cutoff:
            continue
        if form not in MATERIAL_FORMS:
            continue
        accession = accessions[index] if index < len(accessions) else ""
        document = documents[index] if index < len(documents) else ""
        description = descriptions[index] if index < len(descriptions) else ""
        events.append(
            {
                "source": "SEC EDGAR",
                "form": form,
                "category": classify_form(form),
                "filingDate": filing_date.isoformat(),
                "reportDate": report_dates[index] if index < len(report_dates) else "",
                "description": description,
                "url": sec_document_url(cik, accession, document),
            }
        )
    return events[:5]


def drawdown_from_52w(row):
    try:
        _, high_text = str(row.get("range52w", "")).split("-", 1)
        high = float(high_text)
        price = float(row.get("price") or 0)
        if high <= 0 or price <= 0:
            return None
        return price / high - 1
    except (TypeError, ValueError):
        return None


def candidate_rows(rows, limit):
    scored = []
    for row in rows:
        position = (row.get("technical") or {}).get("position52w")
        drawdown = drawdown_from_52w(row)
        score = 0
        if drawdown is not None and drawdown <= -0.45:
            score += 4
        if position is not None and position <= 0.3:
            score += 3
        if row.get("ticker") in {"IONQ", "RGTI", "QBTS", "QUBT", "RKLB", "ASTS", "LUNR", "RDW", "BKSY", "PL", "SPIR"}:
            score += 4
        if any(item.get("level") == "risk" for item in row.get("highlights") or []):
            score += 2
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:limit]]


def main():
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    limit = int(os.environ.get("SEC_EVENT_LIMIT", "120"))
    lookback_days = int(os.environ.get("SEC_EVENT_LOOKBACK_DAYS", "45"))
    cik_map = load_cik_map()
    targets = candidate_rows(rows, limit)
    found = 0
    checked = 0
    for row in targets:
        ticker = normalize_ticker(row.get("ticker", ""))
        cik = cik_map.get(ticker)
        if not cik:
            row["fundamentalNews"] = {"source": "SEC EDGAR", "events": [], "note": "No SEC CIK match"}
            continue
        checked += 1
        try:
            events = recent_material_filings(cik, lookback_days)
        except Exception as exc:
            row["fundamentalNews"] = {"source": "SEC EDGAR", "events": [], "note": str(exc)}
            continue
        row["fundamentalNews"] = {"source": "SEC EDGAR", "cik": cik, "events": events}
        if events:
            found += 1
        time.sleep(0.08)
    payload["secFundamentalNews"] = {
        "source": "SEC EDGAR submissions API",
        "userAgent": SEC_USER_AGENT,
        "lookbackDays": lookback_days,
        "checked": checked,
        "withEvents": found,
    }
    with SNAPSHOT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Checked {checked}; rows with SEC events {found}; wrote {SNAPSHOT}")


if __name__ == "__main__":
    main()
