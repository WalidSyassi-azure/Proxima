from __future__ import annotations
from datetime import datetime, date
from dateutil import tz
from flask import render_template, send_file, request
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from flask import make_response
from io import BytesIO
from flask import send_file
import io
import pdfkit
app = Flask(__name__, instance_relative_config=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///proxima.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret"
import os
from functools import wraps
from flask import session, redirect, url_for, request, flash

WKHTMLTOPDF_EXE = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
_pdfkit_config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_EXE)
# make sure the instance folder exists
os.makedirs(app.instance_path, exist_ok=True)

# use the DB inside /instance
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(app.instance_path, 'proxima.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",  # or "Strict"
    # SESSION_COOKIE_SECURE=True,   # enable only when using HTTPS
)
app.config["LOGIN_USERNAME"] = "admin"
from werkzeug.security import check_password_hash, generate_password_hash
app.config["LOGIN_PASSWORD_HASH"] = generate_password_hash("change-me")
app.config["LOGIN_PASSWORD_HASH"] = "scrypt:32768:8:1$T0QbiwVsMsGc29ER$56b5db883656c24db5ce47f00b8e8cb6ef7fe110f525ecebfc800c01e0550474a2b0a9d3eb107c7db5194d73c6dcd72c92a616d65070bd7611f2c344d3ab386b"
db_path = os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "proxima.db"))
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# Example if you're using SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Endpoints that can be visited without login
PUBLIC_ENDPOINTS = {
    "login", "static",  # allow /login and /static/* 
}

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("logged_in"):
            return view(*args, **kwargs)
        return redirect(url_for("login", next=request.path))
    return wrapper

@app.before_request
def _auth_gate():
    # Allow public endpoints (and favicon)
    ep = request.endpoint or ""
    if ep.split(".")[0] in PUBLIC_ENDPOINTS or request.path == "/favicon.ico":
        return
    # If not logged in, bounce to login
    if not session.get("logged_in"):
        return redirect(url_for("login", next=request.path))


db = SQLAlchemy(app)
# ------------ Models ------------
TVA_RATE = 0.20
class Client(db.Model):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom_client: Mapped[str] = mapped_column(nullable=False)
    tel: Mapped[str] = mapped_column(nullable=True)
    adresse: Mapped[str] = mapped_column(nullable=True)
    ville: Mapped[str] = mapped_column(nullable=True)

    factures = relationship("Facture", back_populates="client")
    payments = relationship("Payment", back_populates="client")

class Product(db.Model):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref_produit: Mapped[str] = mapped_column(unique=True, nullable=False)  # Ensure uniqueness
    nom_produit: Mapped[str] = mapped_column(nullable=False)
    prix_achat: Mapped[float] = mapped_column(default=0.0)
    prix_std: Mapped[float] = mapped_column(default=0.0)

    entries = relationship("StockEntry", back_populates="product")
    lines = relationship("InvoiceLine", back_populates="product")

class StockEntry(db.Model):
    __tablename__ = "stock_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    date: Mapped[date] = mapped_column(default=date.today)
    qte_entree: Mapped[int] = mapped_column(default=0)

    product = relationship("Product", back_populates="entries")

class Facture(db.Model):
    __tablename__ = "factures"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(unique=True, nullable=False)  # Ensure uniqueness
    date_vente: Mapped[date] = mapped_column(default=date.today)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    nbr_colis: Mapped[int] = mapped_column(default=0)
    finalized: Mapped[bool] = mapped_column(default=False)

    client = relationship("Client", back_populates="factures")
    lines = relationship("InvoiceLine", back_populates="facture", cascade="all, delete-orphan")
    returns = relationship("ReturnLine", back_populates="facture", cascade="all, delete-orphan")
    applications = relationship("PaymentApplication", back_populates="facture")

    def total_ht(self) -> float:
        return float(sum(l.total() for l in self.lines))

    def total_tva(self, tva_rate: float = TVA_RATE) -> float:
        return float(self.total_ht() * tva_rate)

    def total_ttc(self, tva_rate: float = TVA_RATE) -> float:
        return float(self.total_ht() + self.total_tva(tva_rate))

class InvoiceLine(db.Model):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    facture_id: Mapped[int] = mapped_column(ForeignKey("factures.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    prix_vnt: Mapped[float] = mapped_column(default=0.0)
    qte_vnd: Mapped[int] = mapped_column(default=0)

    facture = relationship("Facture", back_populates="lines")
    product = relationship("Product", back_populates="lines")

    def total(self) -> float:
        return float(self.prix_vnt * self.qte_vnd)

class ReturnLine(db.Model):
    __tablename__ = "return_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    facture_id: Mapped[int] = mapped_column(ForeignKey("factures.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    prix_vnt: Mapped[float] = mapped_column(default=0.0)
    qte_retour: Mapped[int] = mapped_column(default=0)
    date: Mapped[date] = mapped_column(default=date.today)

    facture = relationship("Facture", back_populates="returns")
    product = relationship("Product")

    def total(self) -> float:
        return float(self.prix_vnt * self.qte_retour)

class Payment(db.Model):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(unique=True, nullable=False)  # Ensure uniqueness
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    date_pymt: Mapped[date] = mapped_column(default=date.today)
    montant_pymt: Mapped[float] = mapped_column(default=0.0)
    banque: Mapped[str] = mapped_column(nullable=True)
    date_echeance: Mapped[date] = mapped_column(nullable=True)

    client = relationship("Client", back_populates="payments")
    applications = relationship("PaymentApplication", back_populates="payment", cascade="all, delete-orphan")

class PaymentApplication(db.Model):
    __tablename__ = "payment_applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    facture_id: Mapped[int] = mapped_column(ForeignKey("factures.id"))
    amount_applied: Mapped[float] = mapped_column(default=0.0)

    payment = relationship("Payment", back_populates="applications")
    facture = relationship("Facture", back_populates="applications")

# ------------ Helpers ------------

def ensure_db():
    db.create_all()

@app.context_processor
def inject_now():
    from dateutil import tz
    return {"now": datetime.now(tz.tzlocal()), "TVA_RATE": TVA_RATE}
def render_pdf_from_template(template_name: str, **context) -> BytesIO:
    """Render a Jinja template + css to a PDF with pdfkit and return a BytesIO."""
    html = render_template(template_name, **context)
    css_path = os.path.join(app.root_path, "static", "css", "pdf.css")

    # Standard options – tweak margins, DPI as you like
    options = {
        "encoding": "UTF-8",
        "enable-local-file-access": None,
        "quiet": "",
        "margin-top": "16mm",
        "margin-right": "14mm",
        "margin-bottom": "40mm",   # same “family” as @page bottom
        "margin-left": "14mm",
    }

    pdf_bytes = pdfkit.from_string(
        html,
        False,  # return bytes, not write to file
        options=options,
        configuration=_pdfkit_config,
        css=[css_path],
    )
    return BytesIO(pdf_bytes)

def stock_summary_for_product(prod_id: int) -> dict:
    # Qty in
    qin = db.session.scalar(
        db.select(func.coalesce(func.sum(StockEntry.qte_entree), 0)).where(StockEntry.product_id == prod_id)
    ) or 0
    # Qty sold from finalized invoices
    qsold = db.session.scalar(
        db.select(func.coalesce(func.sum(InvoiceLine.qte_vnd), 0))
        .join(Facture, Facture.id == InvoiceLine.facture_id)
        .where(InvoiceLine.product_id == prod_id, Facture.finalized == True)
    ) or 0
    # Qty returned
    qret = db.session.scalar(
        db.select(func.coalesce(func.sum(ReturnLine.qte_retour), 0)).where(ReturnLine.product_id == prod_id)
    ) or 0
    available = (qin - qsold + qret)
    return {"qte_entree": qin, "qte_vendue": max(qsold - qret, 0), "stock_disponible": available}

# ------------ Routes ------------

@app.route("/")
def index():
    return render_template("index.html")

def invoice_totals_by_client(client_id: int) -> float:
    # sum of finalized invoice totals (TTC) for this client
    invs = Facture.query.filter_by(client_id=client_id, finalized=True).all()
    return sum(i.total_ttc() for i in invs)

def payments_applied_by_client(client_id: int) -> float:
    # sum of all amounts applied to invoices of this client
    from sqlalchemy import select
    q = (
        db.session.query(func.coalesce(func.sum(PaymentApplication.amount_applied), 0.0))
        .join(Facture, Facture.id == PaymentApplication.facture_id)
        .filter(Facture.client_id == client_id)
    ).scalar() or 0.0
    return float(q)

def client_balance(client_id: int) -> float:
    return float(invoice_totals_by_client(client_id) - payments_applied_by_client(client_id))

# Clients
@app.get("/clients/export.pdf")
def clients_export_pdf():
    rows = Client.query.order_by(Client.nom_client).all()
    pdf_io = render_pdf_from_template("clients_pdf.html", rows=rows)
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="clients.pdf",
    )




@app.route("/clients", methods=["GET", "POST"])
def clients():
    if request.method == "POST":
        c = Client(
            nom_client=request.form["nom_client"],
            tel=request.form.get("tel"),
            adresse=request.form.get("adresse"),
            ville=request.form.get("ville"),
        )
        db.session.add(c)
        db.session.commit()
        flash("Client added.", "success")
        return redirect(url_for("clients"))
    items = Client.query.order_by(Client.nom_client).all()
    return render_template("clients.html", items=items, client_balance=client_balance)

@app.post("/clients/<int:client_id>/update")
def client_update(client_id: int):
    c = Client.query.get_or_404(client_id)
    c.nom_client = request.form.get("nom_client", c.nom_client)
    c.tel = request.form.get("tel", c.tel)
    c.adresse = request.form.get("adresse", c.adresse)
    c.ville = request.form.get("ville", c.ville)
    db.session.commit()
    flash("Client mis à jour.", "success")
    return redirect(url_for("clients"))

@app.post("/clients/<int:client_id>/delete")
def client_delete(client_id: int):
    c = Client.query.get_or_404(client_id)
    # Safe guard: block delete if there are invoices or payments
    factures_count = db.session.scalar(
        db.select(func.count()).select_from(Facture).where(Facture.client_id == c.id)
    ) or 0
    payments_count = db.session.scalar(
        db.select(func.count()).select_from(Payment).where(Payment.client_id == c.id)
    ) or 0
    if factures_count or payments_count:
        flash("Impossible de supprimer: client lié à des factures ou paiements.", "warning")
        return redirect(url_for("clients"))

    db.session.delete(c)
    db.session.commit()
    flash("Client supprimé.", "success")
    return redirect(url_for("clients"))


@app.get("/clients/export.csv")
def clients_export_csv():
    rows = Client.query.order_by(Client.nom_client).all()
    lines = ["NOM_CLIENT;TEL;ADRESSE;VILLE"]
    for r in rows:
        def s(x): return (x or "").replace(";", ",")
        lines.append(f"{s(r.nom_client)};{s(r.tel)};{s(r.adresse)};{s(r.ville)}")
    csv = "\n".join(lines)
    resp = make_response(csv)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=clients.csv"
    return resp
@app.context_processor
def expose_helpers_to_jinja():
    # Make helpers callable from ANY template (HTML or PDF)
    return {
        "client_balance": client_balance,
        "invoice_totals_by_client": invoice_totals_by_client,
        "payments_applied_by_client": payments_applied_by_client,
    }


@app.get("/clients/print")
def clients_print():
    items = Client.query.order_by(Client.nom_client).all()
    return render_template("clients_print.html", items=items)
# Products & Stock Entries
@app.route("/products", methods=["GET", "POST"])
def products():
    if request.method == "POST":
        ref = request.form["ref_produit"].strip()
        p = Product(
            ref_produit=ref,
            nom_produit=request.form["nom_produit"].strip(),
            prix_achat=float(request.form.get("prix_achat", 0) or 0),
            prix_std=float(request.form.get("prix_std", 0) or 0),
        )
        db.session.add(p)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
            return redirect(url_for("products"))

        # NEW: create an initial stock entry if provided
        qte_entree = int(request.form.get("qte_entree", 0) or 0)
        date_entry = request.form.get("date_entry")
        if qte_entree > 0:
            entry = StockEntry(
                product_id=p.id,
                date=datetime.strptime(date_entry, "%Y-%m-%d").date() if date_entry else date.today(),
                qte_entree=qte_entree,
            )
            db.session.add(entry)
            db.session.commit()

        flash("Product added.", "success")
        return redirect(url_for("products"))

    # GET: list products + total QTE_IN per product
    items = Product.query.order_by(Product.nom_produit).all()

    # totals of stock entries per product
    qte_map = dict(
        db.session.query(
            StockEntry.product_id,
            func.coalesce(func.sum(StockEntry.qte_entree), 0)
        ).group_by(StockEntry.product_id).all()
    )
    # pass a simple accessor to the template
    def qin(pid): return int(qte_map.get(pid, 0))
    return render_template("products.html", items=items, qin=qin)

@app.post("/products/<int:product_id>/update")
def product_update(product_id: int):
    p = Product.query.get_or_404(product_id)
    # Allow editing ref too (unique)
    new_ref = request.form.get("ref_produit", p.ref_produit).strip()
    p.ref_produit = new_ref
    p.nom_produit = request.form.get("nom_produit", p.nom_produit)
    p.prix_achat = float(request.form.get("prix_achat", p.prix_achat) or 0)
    p.prix_std = float(request.form.get("prix_std", p.prix_std) or 0)
    try:
        db.session.commit()
        flash("Produit mis à jour.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur mise à jour (ref unique ?) : {e}", "danger")
    return redirect(url_for("products"))

@app.post("/products/<int:product_id>/delete")
def product_delete(product_id: int):
    p = Product.query.get_or_404(product_id)
    # Safe guard: block delete if referenced in lines or stock entries
    used_lines = db.session.scalar(
        db.select(func.count()).select_from(InvoiceLine).where(InvoiceLine.product_id == p.id)
    ) or 0
    has_entries = db.session.scalar(
        db.select(func.count()).select_from(StockEntry).where(StockEntry.product_id == p.id)
    ) or 0
    if used_lines or has_entries:
        flash("Impossible de supprimer: produit utilisé (lignes facture ou entrées stock).", "warning")
        return redirect(url_for("products"))

    db.session.delete(p)
    db.session.commit()
    flash("Produit supprimé.", "success")
    return redirect(url_for("products"))

@app.get("/clients/<int:client_id>/history")
def client_history(client_id: int):
    c = Client.query.get_or_404(client_id)
    invs = Facture.query.filter_by(client_id=client_id, finalized=True).order_by(Facture.date_vente.desc()).all()
    pays = Payment.query.filter_by(client_id=client_id).order_by(Payment.date_pymt.desc()).all()
    applied_total = payments_applied_by_client(client_id)
    remaining = client_balance(client_id)
    return render_template("client_history.html", c=c, invs=invs, pays=pays, remaining=remaining, applied_total=applied_total)

@app.route("/stock_entry", methods=["POST"])
def stock_entry():
    entry = StockEntry(
        product_id=int(request.form["product_id"]),
        date=datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
        qte_entree=int(request.form["qte_entree"]),
    )
    db.session.add(entry)
    db.session.commit()
    flash("Stock entry recorded.", "success")
    return redirect(url_for("products"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd  = request.form.get("password", "")
        if (
            user == app.config["LOGIN_USERNAME"]
            and check_password_hash(app.config["LOGIN_PASSWORD_HASH"], pwd)
        ):
            session["logged_in"] = True
            # Optional: keep session alive for browser session only (default)
            next_url = request.args.get("next") or url_for("index")
            flash("Connecté.", "success")
            return redirect(next_url)
        flash("Identifiants invalides.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for("login"))


# Invoices (Factures)
@app.route("/invoices/new", methods=["GET", "POST"])
def invoice_new():
    if request.method == "POST":
        inv = Facture(
            numero=request.form["numero"].strip(),
            date_vente=datetime.strptime(request.form["date_vente"], "%Y-%m-%d").date(),
            client_id=int(request.form["client_id"]),
            nbr_colis=int(request.form.get("nbr_colis", 0) or 0),
        )
        db.session.add(inv)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
            return redirect(url_for("invoice_new"))
        return redirect(url_for("invoice_view", invoice_id=inv.id))

    clients = Client.query.order_by(Client.nom_client).all()

    # Build a lightweight list with totals, paid, remaining
    invs = (Facture.query
            .order_by(Facture.date_vente.desc(), Facture.id.desc())
            .all())

    invoice_rows = []
    for i in invs:
        total = i.total_ttc()
        paid = db.session.query(func.coalesce(func.sum(PaymentApplication.amount_applied), 0.0)) \
            .filter(PaymentApplication.facture_id == i.id).scalar() or 0.0
        remaining = total - paid
        invoice_rows.append({
            "i": i, "total": float(total), "paid": float(paid), "remaining": float(remaining)
        })

    return render_template("invoice_new.html", clients=clients, invoice_rows=invoice_rows)

@app.post("/invoices/<int:invoice_id>/update")
def invoice_update(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    # allow changing numero (unique), date, client, nbr_colis
    inv.numero = request.form.get("numero", inv.numero).strip()
    if request.form.get("date_vente"):
        inv.date_vente = datetime.strptime(request.form["date_vente"], "%Y-%m-%d").date()
    if request.form.get("client_id"):
        inv.client_id = int(request.form["client_id"])
    if request.form.get("nbr_colis") is not None:
        inv.nbr_colis = int(request.form.get("nbr_colis") or 0)
    try:
        db.session.commit()
        flash("Facture mise à jour.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur de mise à jour (numéro unique ?) : {e}", "danger")
    return redirect(url_for("invoice_new"))

@app.post("/invoices/<int:invoice_id>/delete")
def invoice_delete(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    # Block delete if any payments are applied
    apps = db.session.scalar(
        db.select(func.count()).select_from(PaymentApplication).where(PaymentApplication.facture_id == inv.id)
    ) or 0
    if apps:
        flash("Impossible de supprimer: des paiements sont appliqués sur cette facture.", "warning")
        return redirect(url_for("invoice_new"))
    db.session.delete(inv)  # cascades delete-orphan lines/returns
    db.session.commit()
    flash("Facture supprimée.", "success")
    return redirect(url_for("invoice_new"))

@app.post("/invoices/<int:invoice_id>/toggle_finalize")
def invoice_toggle_finalize(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    inv.finalized = not inv.finalized
    db.session.commit()
    flash("Statut de finalisation mis à jour.", "success")
    return redirect(url_for("invoice_new"))

@app.route("/invoices/<int:invoice_id>")
def invoice_view(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    products = Product.query.order_by(Product.nom_produit).all()
    return render_template("invoice_view.html", inv=inv, products=products)

@app.route("/invoices/<int:invoice_id>/add_line", methods=["POST"])
def invoice_add_line(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    line = InvoiceLine(
        facture_id=inv.id,
        product_id=int(request.form["product_id"]),
        prix_vnt=float(request.form["prix_vnt"]),
        qte_vnd=int(request.form["qte_vnd"]),
    )
    db.session.add(line)
    db.session.commit()
    return redirect(url_for("invoice_view", invoice_id=inv.id))

@app.route("/invoices/<int:invoice_id>/add_return", methods=["POST"])
def invoice_add_return(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    ret = ReturnLine(
        facture_id=inv.id,
        product_id=int(request.form["product_id"]),
        prix_vnt=float(request.form["prix_vnt"]),
        qte_retour=int(request.form["qte_retour"]),
        date=datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
    )
    db.session.add(ret)
    db.session.commit()
    return redirect(url_for("invoice_view", invoice_id=inv.id))

@app.route("/invoices/<int:invoice_id>/finalize", methods=["POST"])
def invoice_finalize(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    inv.finalized = True  # Sales from this invoice will count in inventory
    db.session.commit()
    flash("Invoice finalized.", "success")
    return redirect(url_for("invoice_view", invoice_id=inv.id))

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file

@app.route("/invoices/<int:invoice_id>/receipt")
def invoice_receipt(invoice_id: int):
    inv = Facture.query.get_or_404(invoice_id)
    pdf_io = render_pdf_from_template("receipt_invoice.html", inv=inv)
    return send_file(pdf_io, as_attachment=True,
                     download_name=f"Facture_{inv.numero}.pdf",
                     mimetype="application/pdf")



# Payments
@app.route("/payments/new", methods=["GET", "POST"])
def payment_new():
    if request.method == "POST":
        pay = Payment(
            numero=request.form["numero"],
            client_id=int(request.form["client_id"]),
            date_pymt=datetime.strptime(request.form["date_pymt"], "%Y-%m-%d").date(),
            montant_pymt=float(request.form["montant_pymt"]),
            banque=request.form.get("banque"),
            date_echeance=datetime.strptime(request.form["date_echeance"], "%Y-%m-%d").date()
                if request.form.get("date_echeance") else None,
        )
        db.session.add(pay)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
            return redirect(url_for("payment_new"))
        return redirect(url_for("payment_view", payment_id=pay.id))

    # ---------- GET (with optional filter) ----------
    clients = Client.query.order_by(Client.nom_client).all()
    filter_id = request.args.get("filter_client_id")

    if filter_id:
        # Focused view for a single client
        c = Client.query.get_or_404(int(filter_id))

        # FINALIZED invoices for client, newest first
        invs = (Facture.query
                .filter_by(client_id=c.id, finalized=True)
                .order_by(Facture.date_vente.desc(), Facture.id.desc())
                .all())

        # All payments by this client, newest first
        pays = (Payment.query
                .filter_by(client_id=c.id)
                .order_by(Payment.date_pymt.desc(), Payment.id.desc())
                .all())

        # Totals
        total_ttc = sum(i.total_ttc() for i in invs)
        total_paid = db.session.query(func.coalesce(func.sum(PaymentApplication.amount_applied), 0.0)) \
            .join(Facture, Facture.id == PaymentApplication.facture_id) \
            .filter(Facture.client_id == c.id).scalar() or 0.0
        remaining = total_ttc - total_paid

        # Prepare light rows for the template, with paid per invoice
        detail_invoices = []
        for i in invs:
            paid_i = db.session.query(func.coalesce(func.sum(PaymentApplication.amount_applied), 0.0)) \
                .filter(PaymentApplication.facture_id == i.id).scalar() or 0.0
            detail_invoices.append({
                "i": i,
                "total": float(i.total_ttc()),
                "paid": float(paid_i),
                "remaining": float(i.total_ttc() - paid_i),
            })

        detail_totals = {
            "total_ttc": float(total_ttc),
            "total_paid": float(total_paid),
            "remaining": float(remaining),
        }

        return render_template(
            "payment_new.html",
            clients=clients,
            selected_client=c,
            detail_invoices=detail_invoices,
            detail_payments=pays,
            detail_totals=detail_totals,
            client_rows=None,  # hide global table
        )

    # Default global list (no filter)
    client_rows = []
    for c in clients:
        total = invoice_totals_by_client(c.id)
        paid  = payments_applied_by_client(c.id)
        remaining = total - paid
        client_rows.append({"c": c, "total": total, "paid": paid, "remaining": remaining})

    return render_template("payment_new.html",
                           clients=clients,
                           client_rows=client_rows,
                           selected_client=None)


@app.route("/payments/<int:payment_id>", methods=["GET", "POST"])
def payment_view(payment_id: int):
    pay = Payment.query.get_or_404(payment_id)
    if request.method == "POST":
        appl = PaymentApplication(
            payment_id=pay.id,
            facture_id=int(request.form["invoice_id"]),
            amount_applied=float(request.form["amount_applied"]),
        )
        db.session.add(appl)
        db.session.commit()
        flash("Payment applied to invoice.", "success")
        return redirect(url_for("payment_view", payment_id=pay.id))
    applied = sum(a.amount_applied for a in pay.applications)
    remaining = pay.montant_pymt - applied
    invoices = Facture.query.order_by(Facture.date_vente.desc()).all()
    return render_template("payment_view.html", pay=pay, invoices=invoices, remaining=remaining)

@app.route("/payments/<int:payment_id>/receipt")
def payment_receipt(payment_id: int):
    pay = Payment.query.get_or_404(payment_id)

    # total applied by this payment (for the table)
    total_applied = float(sum(a.amount_applied for a in pay.applications))

    # what you want to show: remaining balance for the client (all invoices - all payments)
    remaining_client = float(client_balance(pay.client_id))

    # clean tiny floating point noise and avoid negative zero in the PDF
    if abs(remaining_client) < 1e-6:
        remaining_client = 0.0

    pdf_io = render_pdf_from_template(
        "receipt_payment.html",
        pay=pay,
        total_applied=total_applied,     # show in the “Total paiement” row
        remaining=remaining_client,      # show in the “Montant restant” row
    )
    return send_file(
        pdf_io,
        as_attachment=True,
        download_name=f"Paiement_{pay.numero}.pdf",
        mimetype="application/pdf",
    )

# Inventory
@app.route("/inventory")
def inventory():
    products = Product.query.order_by(Product.nom_produit).all()
    rows = []
    total_achat = 0.0
    total_vente = 0.0
    for p in products:
        # summary
        qin = db.session.scalar(db.select(func.coalesce(func.sum(StockEntry.qte_entree), 0)).where(StockEntry.product_id == p.id)) or 0
        qsold = db.session.scalar(
            db.select(func.coalesce(func.sum(InvoiceLine.qte_vnd), 0))
            .join(Facture, Facture.id == InvoiceLine.facture_id)
            .where(InvoiceLine.product_id == p.id, Facture.finalized == True)
        ) or 0
        qret = db.session.scalar(db.select(func.coalesce(func.sum(ReturnLine.qte_retour), 0)).where(ReturnLine.product_id == p.id)) or 0
        available = qin - qsold + qret
        prod_sales = db.session.scalar(
            db.select(func.coalesce(func.sum(InvoiceLine.qte_vnd * InvoiceLine.prix_vnt), 0.0))
            .join(Facture, Facture.id == InvoiceLine.facture_id)
            .where(InvoiceLine.product_id == p.id, Facture.finalized == True)
        ) or 0.0
        prod_returns = db.session.scalar(
            db.select(func.coalesce(func.sum(ReturnLine.qte_retour * ReturnLine.prix_vnt), 0.0))
            .where(ReturnLine.product_id == p.id)
        ) or 0.0
        totalvente = float(prod_sales - prod_returns)
        totalachat = float(qin * (p.prix_achat or 0.0))

        rows.append({
            "ref": p.ref_produit, "nom": p.nom_produit,
            "qte_entree": qin, "prix_achat": p.prix_achat,
            "total_achat": totalachat, "prix_vente_std": p.prix_std,
            "qte_vendu": max(qsold - qret, 0), "total_vente": totalvente,
            "stock": available
        })
        total_achat += totalachat
        total_vente += totalvente
    total_benef = total_vente - total_achat
    return render_template("inventory.html", rows=rows, total_achat=total_achat, total_vente=total_vente, total_benef=total_benef)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
