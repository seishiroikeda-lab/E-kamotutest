import os
import sqlite3
from flask import Flask, render_template, request, jsonify, url_for

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "hainyu.db")


# ===== DB 初期化 =====

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ヘッダー情報テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hainyu_headers (
            hainyu_id   TEXT PRIMARY KEY,
            date        TEXT,
            shipper     TEXT,
            dest        TEXT,
            item_name   TEXT,
            mark        TEXT
        )
        """
    )

    # 明細テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hainyu_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            hainyu_id    TEXT,
            package_type TEXT,
            no_from      INTEGER,
            no_to        INTEGER,
            qty          INTEGER,
            L            REAL,
            W            REAL,
            H            REAL,
            weight_kg    REAL,
            m3           REAL
        )
        """
    )

    # ★ 追加: OCRで撮ったマーク画像テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ocr_images (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            hainyu_id  TEXT NOT NULL,
            image_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


# モジュール読み込み時に一度だけ実行
init_db()


def get_db():
    """毎回新しいコネクションを返す簡易版"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ===== ページルーティング =====

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/edit")
def edit_page():
    return render_template("edit.html")


@app.route("/mobile-edit")
def mobile_edit_page():
    """従来のスマホ入力画面"""
    return render_template("mobile_edit.html")


@app.route("/test-mobile")
def test_mobile_page():
    """★ 新しいスマホ入力UIテスト画面（testmobile.html を割り当て）"""
    return render_template("testmobile.html")


@app.route("/report")
def report_page():
    return render_template("report.html")


@app.route("/search")
def search_page():
    return render_template("search.html")


@app.route("/list")
def list_page():
    """PC版一覧画面（list.html 側で /api/summary を叩いて使う想定）"""
    return render_template("list.html")


# ===== API: 搬入データ 取得 =====

@app.route("/api/hainyu/<hainyu_id>", methods=["GET"])
def api_get_hainyu(hainyu_id):
    conn = get_db()
    cur = conn.cursor()

    # ヘッダー
    cur.execute(
        """
        SELECT
            hainyu_id,
            date,
            shipper,
            dest,
            item_name,
            mark
        FROM hainyu_headers
        WHERE hainyu_id = ?
        """,
        (hainyu_id,),
    )
    header_row = cur.fetchone()

    if not header_row:
        conn.close()
        return jsonify({"error": "not found"}), 404

    # 明細
    cur.execute(
        """
        SELECT
            id,
            package_type,
            no_from,
            no_to,
            qty,
            L,
            W,
            H,
            weight_kg,
            m3
        FROM hainyu_items
        WHERE hainyu_id = ?
        ORDER BY id
        """,
        (hainyu_id,),
    )
    rows = cur.fetchall()
    conn.close()

    header = {
        "hainyu_id": header_row["hainyu_id"],
        "date": header_row["date"],
        "shipper": header_row["shipper"],
        "dest": header_row["dest"],
        "itemName": header_row["item_name"],
        "mark": header_row["mark"],
    }

    items = []
    for r in rows:
        items.append(
            {
                "id": r["id"],
                "packageType": r["package_type"],
                "noFrom": r["no_from"],
                "noTo": r["no_to"],
                "qty": r["qty"],
                "L": r["L"],
                "W": r["W"],
                "H": r["H"],
                "weightKg": r["weight_kg"],
                "m3": r["m3"],
            }
        )

    return jsonify({"header": header, "items": items})


# ===== API: 搬入データ 登録 / 更新 =====

@app.route("/api/hainyu/<hainyu_id>", methods=["POST"])
def api_save_hainyu(hainyu_id):
    data = request.get_json(force=True)

    header = data.get("header") or {}
    items = data.get("items") or []

    date = header.get("date")
    shipper = header.get("shipper", "")
    dest = header.get("dest", "")
    item_name = header.get("itemName", "")
    mark = header.get("mark", "")

    conn = get_db()
    cur = conn.cursor()

    # ヘッダー upsert
    cur.execute(
        """
        INSERT INTO hainyu_headers (hainyu_id, date, shipper, dest, item_name, mark)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(hainyu_id) DO UPDATE SET
          date      = excluded.date,
          shipper   = excluded.shipper,
          dest      = excluded.dest,
          item_name = excluded.item_name,
          mark      = excluded.mark
        """,
        (hainyu_id, date, shipper, dest, item_name, mark),
    )

    # 明細は一度削除してから挿入し直し（単純化のため）
    cur.execute("DELETE FROM hainyu_items WHERE hainyu_id = ?", (hainyu_id,))

    for it in items:
        cur.execute(
            """
            INSERT INTO hainyu_items (
                hainyu_id,
                package_type,
                no_from,
                no_to,
                qty,
                L,
                W,
                H,
                weight_kg,
                m3
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hainyu_id,
                it.get("packageType"),
                it.get("noFrom"),
                it.get("noTo"),
                it.get("qty"),
                it.get("L"),
                it.get("W"),
                it.get("H"),
                it.get("weightKg"),
                it.get("m3"),
            ),
        )

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# ===== API: 検索（キーワード検索用） =====

@app.route("/api/search", methods=["GET"])
def api_search():
    q = request.args.get("q", "").strip()

    conn = get_db()
    cur = conn.cursor()

    base_sql = """
        SELECT
            hainyu_id,
            date,
            shipper,
            dest,
            item_name,
            mark
        FROM hainyu_headers
    """
    params = []

    if q:
        like = f"%{q}%"
        base_sql += """
            WHERE
                hainyu_id LIKE ?
                OR shipper LIKE ?
                OR dest LIKE ?
                OR item_name LIKE ?
                OR mark LIKE ?
        """
        params.extend([like, like, like, like, like])

    base_sql += " ORDER BY date DESC, hainyu_id ASC LIMIT 100"

    cur.execute(base_sql, params)
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append(
            {
                "hainyuId": r["hainyu_id"],
                "date": r["date"],
                "shipper": r["shipper"],
                "dest": r["dest"],
                "itemName": r["item_name"],
                "lastUpdated": r["date"],
            }
        )

    return jsonify({"results": result})


# ===== API: 一覧 / 集計用 =====
# ★ ここで「サムネ用画像パス」も集計に含める

@app.route("/api/summary", methods=["GET"])
def api_summary():
    date_from = (request.args.get("dateFrom") or "").strip()
    date_to = (request.args.get("dateTo") or "").strip()
    shipper = (request.args.get("shipper") or "").strip()
    dest = (request.args.get("dest") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    # ocr_images をサブクエリでまとめて、各 hainyu_id の代表サムネ画像を取得
    base_sql = """
        SELECT
            h.hainyu_id,
            h.date,
            h.shipper,
            h.dest,
            h.item_name,
            COUNT(i.id)                      AS item_count,
            COALESCE(SUM(i.qty), 0)          AS total_qty,
            COALESCE(SUM(i.m3), 0)           AS total_m3,
            COALESCE(SUM(i.qty * i.weight_kg),0) AS total_weight,
            oi.thumb_image_path              AS thumb_image_path
        FROM hainyu_headers h
        LEFT JOIN hainyu_items i
          ON i.hainyu_id = h.hainyu_id
        LEFT JOIN (
            SELECT
                hainyu_id,
                MIN(image_path) AS thumb_image_path
            FROM ocr_images
            GROUP BY hainyu_id
        ) oi
          ON oi.hainyu_id = h.hainyu_id
    """

    conditions = []
    params = []

    if date_from:
        conditions.append("h.date >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("h.date <= ?")
        params.append(date_to)

    if shipper:
        conditions.append("h.shipper LIKE ?")
        params.append(f"%{shipper}%")

    if dest:
        conditions.append("h.dest LIKE ?")
        params.append(f"%{dest}%")

    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)

    base_sql += """
        GROUP BY
            h.hainyu_id,
            h.date,
            h.shipper,
            h.dest,
            h.item_name,
            oi.thumb_image_path
        ORDER BY
            h.date DESC,
            h.hainyu_id ASC
        LIMIT 500
    """

    cur.execute(base_sql, params)
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        thumb_path = r["thumb_image_path"]
        thumb_url = url_for("static", filename=thumb_path) if thumb_path else None

        results.append(
            {
                "hainyuId": r["hainyu_id"],
                "date": r["date"],
                "shipper": r["shipper"],
                "dest": r["dest"],
                "itemName": r["item_name"],
                "itemCount": r["item_count"],
                "totalQty": r["total_qty"],
                "totalM3": float(r["total_m3"] or 0),
                "totalWeight": float(r["total_weight"] or 0),
                # ★ 追加: 一覧画面用のサムネURL
                "thumbUrl": thumb_url,
            }
        )

    return jsonify({"results": results})


# ===== API: OCRマーク画像 アップロード & 取得 =====

@app.route("/api/hainyu/<hainyu_id>/mark_image", methods=["POST"])
def upload_mark_image(hainyu_id):
    """
    スマホ側の OCR 用ファイル入力から呼ばれる。
    元画像を static/ocr_images 以下に保存し、DB(ocr_images)に紐づける。
    """
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no file"}), 400

    # 保存先フォルダ: static/ocr_images
    save_dir = os.path.join(app.static_folder, "ocr_images")
    os.makedirs(save_dir, exist_ok=True)

    orig_name = file.filename or "mark.jpg"
    _, ext = os.path.splitext(orig_name)
    if not ext:
        ext = ".jpg"

    # ファイル名: {hainyu_id}_{timestamp}.ext
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{hainyu_id}_{ts}{ext}"

    filepath = os.path.join(save_dir, filename)
    file.save(filepath)

    # static からの相対パスをDBに保存
    rel_path = f"ocr_images/{filename}"

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ocr_images (hainyu_id, image_path, created_at)
        VALUES (?, ?, datetime('now','localtime'))
        """,
        (hainyu_id, rel_path),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "imageUrl": url_for("static", filename=rel_path)
    })


@app.route("/api/hainyu/<hainyu_id>/mark_images", methods=["GET"])
def list_mark_images(hainyu_id):
    """
    搬入番号に紐づいたマーク画像一覧（PCの詳細画面などで使いたくなった時用）
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, image_path, created_at
        FROM ocr_images
        WHERE hainyu_id = ?
        ORDER BY created_at DESC
        """,
        (hainyu_id,),
    )
    rows = cur.fetchall()
    conn.close()

    images = [
        {
            "id": r["id"],
            "imageUrl": url_for("static", filename=r["image_path"]),
            "createdAt": r["created_at"],
        }
        for r in rows
    ]
    return jsonify(images)


if __name__ == "__main__":
    # 開発サーバー起動
    # 外部公開する場合は host='0.0.0.0' にする等
    app.run(debug=True, port=5000)
