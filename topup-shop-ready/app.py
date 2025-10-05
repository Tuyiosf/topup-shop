\
        import os
        import uuid
        from urllib.parse import urlencode

        from dotenv import load_dotenv
        from flask import Flask, session, redirect, request, url_for, render_template, flash, jsonify
        from flask_session import Session
        from flask_socketio import SocketIO, join_room, leave_room, emit
        from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
        from sqlalchemy.orm import sessionmaker, declarative_base, relationship
        from datetime import datetime
        import requests

        load_dotenv()

        FLASK_SECRET = os.environ.get("FLASK_SECRET", "devsecret")
        DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
        DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
        DISCORD_REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
        ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")
        BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
        DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///shop.db")

        app = Flask(__name__, static_folder="static", template_folder="templates")
        app.secret_key = FLASK_SECRET
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_PERMANENT"] = False
        Session(app)

        socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

        engine = create_engine(DATABASE_URL, echo=False, future=True)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        Base = declarative_base()

        class User(Base):
            __tablename__ = "users"
            id = Column(Integer, primary_key=True)
            discord_id = Column(String, unique=True, index=True)
            username = Column(String)
            discriminator = Column(String)
            avatar = Column(String)
            orders = relationship("Order", back_populates="user")

        class Order(Base):
            __tablename__ = "orders"
            id = Column(Integer, primary_key=True)
            order_id = Column(String, unique=True, index=True)
            game = Column(String)
            created_at = Column(DateTime, default=datetime.utcnow)
            user_id = Column(Integer, ForeignKey("users.id"))
            status = Column(String, default="open")
            user = relationship("User", back_populates="orders")
            messages = relationship("Message", back_populates="order", cascade="all, delete-orphan")

        class Message(Base):
            __tablename__ = "messages"
            id = Column(Integer, primary_key=True)
            order_id = Column(Integer, ForeignKey("orders.id"))
            sender = Column(String)
            content = Column(Text)
            created_at = Column(DateTime, default=datetime.utcnow)
            order = relationship("Order", back_populates="messages")

        Base.metadata.create_all(engine)

        def db_session():
            return SessionLocal()

        def generate_order_id():
            return "ORD-" + uuid.uuid4().hex[:10].upper()

        @app.route("/")
        def index():
            user = session.get("user")
            shop_name = "เติมเกมราคาถูก by กก"
            return render_template("index.html", user=user, shop_name=shop_name)

        @app.route("/login")
        def login():
            next_url = request.args.get("next") or request.referrer or "/"
            session["next"] = next_url
            params = {
                "client_id": DISCORD_CLIENT_ID,
                "redirect_uri": DISCORD_REDIRECT_URI,
                "response_type": "code",
                "scope": "identify"
            }
            return redirect("https://discord.com/api/oauth2/authorize?" + urlencode(params))

        @app.route("/callback")
        def callback():
            code = request.args.get("code")
            if not code:
                flash("ไม่พบ code จาก Discord")
                return redirect(url_for("index"))

            data = {
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
                "scope": "identify"
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            try:
                r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers, timeout=10)
                r.raise_for_status()
            except Exception:
                flash("การแลก token ล้มเหลว")
                return redirect(url_for("index"))

            token = r.json().get("access_token")
            if not token:
                flash("ไม่สามารถรับ access token")
                return redirect(url_for("index"))
            hdr = {"Authorization": f"Bearer {token}"}
            try:
                r2 = requests.get("https://discord.com/api/users/@me", headers=hdr, timeout=10)
                r2.raise_for_status()
            except Exception:
                flash("ไม่สามารถเรียกข้อมูลผู้ใช้จาก Discord")
                return redirect(url_for("index"))

            me = r2.json()
            session["user"] = {
                "discord_id": me["id"],
                "username": me["username"],
                "discriminator": me.get("discriminator"),
                "avatar": me.get("avatar")
            }

            db = db_session()
            u = db.query(User).filter_by(discord_id=me["id"]).first()
            if not u:
                u = User(discord_id=me["id"], username=me["username"], discriminator=me.get("discriminator"), avatar=me.get("avatar"))
                db.add(u)
            else:
                u.username = me["username"]
                u.discriminator = me.get("discriminator")
                u.avatar = me.get("avatar")
            db.commit()
            db.close()

            flash("ล็อกอินสำเร็จ")
            return redirect(session.pop("next", url_for("index")))

        @app.route("/logout")
        def logout():
            session.pop("user", None)
            flash("ออกจากระบบแล้ว")
            return redirect(url_for("index"))

        @app.route("/topup")
        def topup():
            user = session.get("user")
            games = ["Free Fire", "ROV", "Roblox"]
            return render_template("topup.html", user=user, games=games)

        @app.route("/create_order", methods=["POST"])
        def create_order():
            user = session.get("user")
            if not user:
                session["next"] = request.referrer or url_for("topup")
                return jsonify({"error": "not_logged_in", "login_url": url_for("login")}), 401
            data = request.get_json() or {}
            game = data.get("game")
            if game not in ["Free Fire", "ROV", "Roblox", "Other"]:
                return jsonify({"error": "invalid_game"}), 400
            db = db_session()
            u = db.query(User).filter_by(discord_id=user["discord_id"]).first()
            if not u:
                u = User(discord_id=user["discord_id"], username=user["username"], discriminator=user.get("discriminator"), avatar=user.get("avatar"))
                db.add(u)
                db.commit()
                db.refresh(u)
            for _ in range(10):
                oid = generate_order_id()
                if not db.query(Order).filter_by(order_id=oid).first():
                    break
            order = Order(order_id=oid, game=game, user=u)
            db.add(order)
            db.commit()
            db.refresh(order)
            init = Message(order=order, sender="system", content=f"Order {oid} สร้างสำหรับ {game}")
            db.add(init)
            db.commit()
            db.close()
            return jsonify({"order_id": oid, "order_url": url_for("order_page", order_id=oid)}), 201

        @app.route("/order/<order_id>")
        def order_page(order_id):
            user = session.get("user")
            db = db_session()
            o = db.query(Order).filter_by(order_id=order_id).first()
            if not o:
                db.close()
                return render_template("error.html", message="Order ไม่พบ"), 404
            if not user or user["discord_id"] != o.user.discord_id:
                db.close()
                return render_template("error.html", message="ไม่อนุญาตให้เข้าถึง (ต้องเป็นเจ้าของคำสั่งซื้อ)"), 403
            messages = [{"sender": m.sender, "content": m.content, "created_at": m.created_at.isoformat()} for m in o.messages]
            db.close()
            return render_template("order.html", user=user, order=o, messages=messages)

        @app.route("/admin", methods=["GET", "POST"])
        def admin_panel():
            if request.method == "POST":
                pw = request.form.get("password")
                if pw == ADMIN_PASSWORD:
                    session["admin"] = True
                    return redirect(url_for("admin_panel"))
                flash("รหัสผ่านไม่ถูกต้อง")
                return redirect(url_for("admin_panel"))
            if not session.get("admin"):
                return render_template("admin.html", logged_in=False)
            db = db_session()
            orders = db.query(Order).order_by(Order.created_at.desc()).all()
            db.close()
            return render_template("admin.html", logged_in=True, orders=orders)

        @app.route("/admin/order/<order_id>/messages", methods=["GET"])
        def admin_get_messages(order_id):
            if not session.get("admin"):
                return jsonify({"error": "unauth"}), 403
            db = db_session()
            o = db.query(Order).filter_by(order_id=order_id).first()
            if not o:
                db.close()
                return jsonify({"error": "not_found"}), 404
            msgs = [{"sender": m.sender, "content": m.content, "created_at": m.created_at.isoformat()} for m in o.messages]
            db.close()
            return jsonify({"messages": msgs})

        @app.route("/admin/send_message", methods=["POST"])
        def admin_send_message():
            if not session.get("admin"):
                return jsonify({"error": "unauth"}), 403
            payload = request.get_json() or {}
            order_id = payload.get("order_id")
            content = payload.get("content", "").strip()
            if not content:
                return jsonify({"error": "empty"}), 400
            db = db_session()
            o = db.query(Order).filter_by(order_id=order_id).first()
            if not o:
                db.close()
                return jsonify({"error": "not_found"}), 404
            m = Message(order=o, sender="admin", content=content)
            db.add(m)
            db.commit()
            socketio.emit("new_message", {"sender": "admin", "content": content, "created_at": m.created_at.isoformat()}, to=order_id)
            db.close()
            return jsonify({"ok": True}), 200

        @socketio.on("join")
        def handle_join(data):
            order_id = data.get("order_id")
            user = session.get("user")
            if not user and not session.get("admin"):
                emit("error", {"msg": "not_logged_in"})
                return
            join_room(order_id)
            emit("system", {"msg": f"{user['username'] if user else 'Admin'} เข้าร่วมห้อง {order_id}"}, to=order_id)

        @socketio.on("leave")
        def handle_leave(data):
            order_id = data.get("order_id")
            leave_room(order_id)

        @socketio.on("send_message")
        def handle_message(data):
            order_id = data.get("order_id")
            content = (data.get("content") or "").strip()
            user = session.get("user")
            sender_label = "admin" if session.get("admin") else "user"
            if not content:
                return
            db = db_session()
            o = db.query(Order).filter_by(order_id=order_id).first()
            if not o:
                db.close()
                emit("error", {"msg": "order_not_found"})
                return
            m = Message(order=o, sender=sender_label, content=content)
            db.add(m)
            db.commit()
            emit("new_message", {"sender": sender_label, "content": content, "created_at": m.created_at.isoformat()}, to=order_id)
            db.close()

        @app.route("/error")
        def error_page():
            msg = request.args.get("msg", "เกิดข้อผิดพลาด")
            return render_template("error.html", message=msg)

        if __name__ == "__main__":
            print("Starting app on", BASE_URL)
            socketio.run(app, host="0.0.0.0", port=5000)
