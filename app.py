# ================================================
# ATFM System - Main Application File
# Day 4-5 - Flask Web Application
# ================================================

from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import psycopg2
import pandas as pd
import bcrypt
import os
import math
from datetime import date
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

# ================================================
# Initialize Flask App
# ================================================
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'atfm_secret_key_2020')

# ── Jinja2 filter: format any timestamp as HH:MM UTC (or —) ──
@app.template_filter('utc_time')
def utc_time_filter(value):
    if value is None:
        return '—'
    s = str(value).strip()
    if not s or s in ('None', 'nan', '—', 'NaT', 'nat'):
        return '—'
    try:
        if hasattr(value, 'strftime'):          # datetime / Timestamp object
            return value.strftime('%H:%M')
        if 'T' in s:                             # ISO-8601: 2020-01-01T08:00:00
            return s.split('T')[1][:5]
        if ' ' in s:                             # "2020-01-01 08:00:00"
            return s.split(' ')[1][:5]
        return s[:5]                             # already "08:00" or similar
    except Exception:
        return '—'

# Absolute path for uploads folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================================================
# ONE-TIME MIGRATION: Airport Lat/Lon
# Adds latitude + longitude to airport_master
# using actual IATA/FAA coordinates.
# Runs on startup; skips if already present.
# ================================================
def init_airport_coords():
    COORDS = {
        'AGS': (33.3699, -81.9645), 'AMA': (35.2194, -101.7059),
        'ANC': (61.1741, -149.9963), 'ATL': (33.6407,  -84.4277),
        'AUS': (30.1975,  -97.6664), 'CHO': (38.1386,  -78.4529),
        'CLT': (35.2140,  -80.9431), 'DEN': (39.8561, -104.6737),
        'DTW': (42.2124,  -83.3534), 'ELP': (31.8072, -106.3779),
        'EWR': (40.6895,  -74.1745), 'EYW': (24.5561,  -81.7596),
        'FAR': (46.9207,  -96.8158), 'FLL': (26.0726,  -80.1527),
        'IAH': (29.9902,  -95.3368), 'IND': (39.7173,  -86.2944),
        'JFK': (40.6413,  -73.7781), 'LAS': (36.0840, -115.1537),
        'LAX': (33.9425, -118.4081), 'MCO': (28.4294,  -81.3089),
        'MIA': (25.7959,  -80.2870), 'MKE': (42.9472,  -87.8966),
        'MSP': (44.8820,  -93.2218), 'OKC': (35.3931,  -97.6007),
        'ORD': (41.9742,  -87.9073), 'PDX': (45.5887, -122.5975),
        'PHL': (39.8744,  -75.2424), 'PHX': (33.4373, -112.0078),
        'PSP': (33.8297, -116.5076), 'RDU': (35.8776,  -78.7875),
        'RNO': (39.4991, -119.7681), 'SAN': (32.7338, -117.1933),
        'SBP': (35.2368, -120.6426), 'SEA': (47.4502, -122.3088),
        'SFO': (37.6213, -122.3790), 'SJU': (18.4373,  -66.0041),
        'SLC': (40.7884, -111.9778), 'SMF': (38.6954, -121.5908),
        'STL': (38.7487,  -90.3700), 'STT': (18.3373,  -64.9733),
        'TPA': (27.9755,  -82.5332), 'TUS': (32.1161, -110.9410),
    }
    try:
        conn = psycopg2.connect(
            database=os.getenv('DB_NAME', 'atfm_db'),
            user=os.getenv('DB_ADMIN_USER', 'postgres'),
            password=os.getenv('DB_ADMIN_PASSWORD', '123456'),
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='airport_master' AND column_name='latitude'
        """)
        if not cur.fetchone():
            cur.execute("""
                ALTER TABLE airport_master
                ADD COLUMN latitude  DECIMAL(9,6),
                ADD COLUMN longitude DECIMAL(9,6)
            """)
            for code, (lat, lon) in COORDS.items():
                cur.execute(
                    "UPDATE airport_master SET latitude=%s, longitude=%s WHERE airport_code=%s",
                    (lat, lon, code)
                )
            conn.commit()
            print("✓ Airport coordinates added to airport_master.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠  Airport coord migration skipped: {e}")

init_airport_coords()

# ================================================
# ONE-TIME MIGRATION: Alerts Schema  (Phase 5)
# Creates atfm_alert + alert_dismissal tables,
# grants access to atfm_app, seeds sample alerts.
# ================================================
def init_alerts_schema():
    try:
        conn = psycopg2.connect(
            database=os.getenv('DB_NAME', 'atfm_db'),
            user=os.getenv('DB_ADMIN_USER', 'postgres'),
            password=os.getenv('DB_ADMIN_PASSWORD', '123456'),
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS atfm_alert (
                alert_id   SERIAL PRIMARY KEY,
                severity   VARCHAR(10) NOT NULL
                               CHECK (severity IN ('CRITICAL','CAUTION','ADVISORY')),
                category   VARCHAR(50)  DEFAULT 'OPERATIONS',
                title      VARCHAR(200) NOT NULL,
                body       TEXT,
                valid_from TIMESTAMP    DEFAULT now(),
                valid_to   TIMESTAMP,
                is_active  BOOLEAN      DEFAULT TRUE,
                created_by INTEGER,
                created_at TIMESTAMP    DEFAULT now()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_dismissal (
                dismissal_id SERIAL PRIMARY KEY,
                alert_id     INTEGER REFERENCES atfm_alert(alert_id) ON DELETE CASCADE,
                user_id      INTEGER,
                dismissed_at TIMESTAMP DEFAULT now(),
                UNIQUE(alert_id, user_id)
            )
        """)

        # Grant permissions to the app role
        for stmt in [
            "GRANT SELECT, INSERT, UPDATE ON atfm_alert TO atfm_app",
            "GRANT SELECT, INSERT         ON alert_dismissal TO atfm_app",
            "GRANT USAGE, SELECT ON SEQUENCE atfm_alert_alert_id_seq TO atfm_app",
            "GRANT USAGE, SELECT ON SEQUENCE alert_dismissal_dismissal_id_seq TO atfm_app",
        ]:
            try:
                cur.execute(stmt)
            except Exception:
                conn.rollback()

        # Seed sample alerts if table is empty
        cur.execute("SELECT COUNT(*) FROM atfm_alert")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO atfm_alert (severity, category, title, body) VALUES
                ('ADVISORY', 'WEATHER',
                 'Convective activity near ORD',
                 'Embedded convective cells reported within 40 nm of KORD. '
                 'Expect holding and re-routing 14:00–18:00 UTC.'),
                ('CAUTION',  'CAPACITY',
                 'Ground stop — SFO reduced arrival rate',
                 'SFO AAR reduced to 28 from 56 due to IFR conditions. '
                 'GDP in effect. Expect avg delay 45–60 min for KSFO arrivals.'),
                ('CRITICAL', 'ATC',
                 'Sector 32 staffing shortfall — ZLA',
                 'ZLA sector 32/33 combined. Reduced sector capacity until 20:00 UTC. '
                 'Re-routing via J-80 in effect for all KLAS–KLAX traffic.')
            """)

        conn.commit()
        cur.close()
        conn.close()
        print("✓ Alert schema ready.")
    except Exception as e:
        print(f"⚠  Alert schema migration skipped: {e}")

init_alerts_schema()

# ================================================
# Database Connection
# Connects as atfm_app (non-superuser) so that
# Row-Level Security policies take effect.
# Sets app.current_user_id  → used by audit trigger
# Sets app.current_airline  → used by RLS policy
# ================================================
def get_db():
    conn = psycopg2.connect(
        database=os.getenv('DB_NAME', 'atfm_db'),
        user=os.getenv('DB_USER', 'atfm_app'),
        password=os.getenv('DB_PASSWORD', 'atfm123'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432')
    )
    try:
        # Set session variables for RLS and audit trigger
        user_id = str(session.get('user_id') or '')
        airline_code = session.get('airline_code') or ''
        cur = conn.cursor()
        cur.execute(
            "SELECT set_config('app.current_user_id', %s, false)",
            (user_id,)
        )
        cur.execute(
            "SELECT set_config('app.current_airline', %s, false)",
            (airline_code,)
        )
        cur.close()
    except RuntimeError:
        # No Flask request context (e.g. app startup)
        pass
    return conn

# ================================================
# AUTO-ALERT HELPER  (Phase 5)
# Generates a CAUTION alert when delay rate >20%.
# Throttled: at most one AUTO alert per 2 hours.
# ================================================
def _check_auto_delay_alert(conn, cur):
    try:
        cur.execute("""
            SELECT
                SUM(CASE WHEN status = 'DELAYED' THEN 1 ELSE 0 END)::float /
                NULLIF(COUNT(*), 0) AS delay_rate
            FROM flight_operation
            WHERE status IN ('DEPARTED','DELAYED','CANCELLED')
        """)
        row = cur.fetchone()
        if row and row[0] and row[0] > 0.20:
            cur.execute("""
                SELECT COUNT(*) FROM atfm_alert
                WHERE category = 'AUTO' AND is_active = TRUE
                  AND created_at > now() - INTERVAL '2 hours'
            """)
            if cur.fetchone()[0] == 0:
                delay_pct = round(row[0] * 100, 1)
                cur.execute("""
                    INSERT INTO atfm_alert (severity, category, title, body)
                    VALUES ('CAUTION', 'AUTO', %s, %s)
                """, (
                    f'Network delay rate elevated: {delay_pct}%',
                    f'System-generated alert. Current delay rate is {delay_pct}% '
                    f'(threshold: 20%). Review affected flights in the Flights view.'
                ))
                conn.commit()
    except Exception:
        pass


# ================================================
# CONTEXT PROCESSOR — inject alert count into
# every rendered template automatically
# ================================================
@app.context_processor
def inject_alert_globals():
    if 'user_id' not in session:
        return {'alert_count': 0, 'critical_alerts': []}
    try:
        conn = get_db()
        cur  = conn.cursor()
        uid  = session['user_id']

        cur.execute("""
            SELECT COUNT(*) FROM atfm_alert a
            WHERE a.is_active = TRUE
              AND (a.valid_to IS NULL OR a.valid_to > now())
              AND NOT EXISTS (
                  SELECT 1 FROM alert_dismissal d
                  WHERE d.alert_id = a.alert_id AND d.user_id = %s
              )
        """, (uid,))
        alert_count = cur.fetchone()[0]

        cur.execute("""
            SELECT alert_id, title FROM atfm_alert
            WHERE severity = 'CRITICAL' AND is_active = TRUE
              AND (valid_to IS NULL OR valid_to > now())
              AND NOT EXISTS (
                  SELECT 1 FROM alert_dismissal d
                  WHERE d.alert_id = atfm_alert.alert_id AND d.user_id = %s
              )
            ORDER BY created_at DESC LIMIT 3
        """, (uid,))
        critical_alerts = [{'id': r[0], 'title': r[1]} for r in cur.fetchall()]

        cur.close()
        conn.close()
        return {'alert_count': alert_count, 'critical_alerts': critical_alerts}
    except Exception:
        return {'alert_count': 0, 'critical_alerts': []}


# ================================================
# HOME ROUTE
# Opens login page by default
# ================================================
@app.route('/')
def home():
    return redirect(url_for('login'))

# ================================================
# LOGIN ROUTE
# Validates username and password
# against app_user table in database
# Stores role and airline_code in session
# ================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            conn = get_db()
            cur = conn.cursor()

            cur.execute("""
                SELECT user_id, username,
                password_hash, full_name
                FROM app_user
                WHERE username = %s
                AND is_active = true
            """, (username,))

            user = cur.fetchone()

            if user:
                stored_hash = user[2]
                password_bytes = password.encode('utf-8')
                hash_bytes = stored_hash.encode('utf-8')

                if bcrypt.checkpw(password_bytes, hash_bytes):
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    session['full_name'] = user[3]

                    # Get user role
                    cur.execute("""
                        SELECT r.role_name
                        FROM user_role ur
                        JOIN role r
                        ON ur.role_id = r.role_id
                        WHERE ur.user_id = %s
                    """, (user[0],))
                    role = cur.fetchone()
                    session['role'] = role[0] if role else 'observer'

                    # Get airline code for airline operators
                    cur.execute("""
                        SELECT airline_code
                        FROM app_user
                        WHERE user_id = %s
                    """, (user[0],))
                    airline = cur.fetchone()
                    session['airline_code'] = airline[0] if airline and airline[0] else None

                    # Update last_login timestamp
                    cur.execute("""
                        UPDATE app_user
                        SET last_login = now()
                        WHERE user_id = %s
                    """, (user[0],))

                    # Record successful login in history
                    cur.execute("""
                        INSERT INTO user_login_history
                        (user_id, ip_address, success)
                        VALUES (%s, %s, %s)
                    """, (
                        user[0],
                        request.remote_addr,
                        True
                    ))

                    conn.commit()
                    cur.close()
                    conn.close()
                    return redirect(url_for('dashboard'))
                else:
                    # Record failed login attempt
                    cur.execute("""
                        INSERT INTO user_login_history
                        (user_id, ip_address, success)
                        VALUES (%s, %s, %s)
                    """, (
                        user[0],
                        request.remote_addr,
                        False
                    ))
                    conn.commit()
                    flash('Wrong password! Try again.', 'danger')
            else:
                flash('Username not found!', 'danger')

            cur.close()
            conn.close()

        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')

    return render_template('login.html')

# ================================================
# LOGOUT ROUTE
# Clears session and returns to login
# ================================================
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out!', 'info')
    return redirect(url_for('login'))

# ================================================
# DASHBOARD ROUTE
# Shows flight summary cards and charts
# Chart 1: Flights by airline
# Chart 2: Flights by status
# Filters by airline if airline_operator
# ================================================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db()
        role = session.get('role')

        # Resolve active filters
        # airline_operator is always locked to their airline
        if role == 'airline_operator' and session.get('airline_code'):
            airline_filter = session.get('airline_code')
        else:
            airline_filter = request.args.get('airline_filter', '')

        status_filter = request.args.get('status_filter', '')

        # Fetch airlines list for dropdown (admin/non-operator roles)
        df_airlines_list = pd.read_sql(
            "SELECT airline_code, airline_name FROM airline_master ORDER BY airline_code",
            conn
        )
        airlines_list = df_airlines_list.to_dict('records')

        # Build WHERE conditions
        conditions = []
        params = {}
        if airline_filter:
            conditions.append("fp.airline_code = %(airline_filter)s")
            params['airline_filter'] = airline_filter
        if status_filter:
            conditions.append("fo.status = %(status_filter)s")
            params['status_filter'] = status_filter

        where_fp = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # For queries that only touch flight_operation (no fp join needed for summary without airline filter)
        fo_conditions = []
        fo_params = {}
        if airline_filter:
            fo_conditions.append("fp.airline_code = %(airline_filter)s")
            fo_params['airline_filter'] = airline_filter
        if status_filter:
            fo_conditions.append("fo.status = %(status_filter)s")
            fo_params['status_filter'] = status_filter

        fo_join = "JOIN flight_plan fp ON fo.flight_plan_id = fp.flight_plan_id" if fo_conditions else ""
        fo_where = ("WHERE " + " AND ".join(fo_conditions)) if fo_conditions else ""

        df_airline = pd.read_sql(f"""
            SELECT fp.airline_code,
                   am.airline_name,
                   COUNT(*) as total
            FROM flight_plan fp
            JOIN airline_master am ON fp.airline_code = am.airline_code
            JOIN flight_operation fo ON fo.flight_plan_id = fp.flight_plan_id
            {where_fp}
            GROUP BY fp.airline_code, am.airline_name
            ORDER BY total DESC
        """, conn, params=params if params else None)

        df_status = pd.read_sql(f"""
            SELECT fo.status, COUNT(*) as total
            FROM flight_operation fo
            {fo_join}
            {fo_where}
            GROUP BY fo.status
            ORDER BY CASE
                WHEN fo.status = 'DEPARTED' THEN 1
                WHEN fo.status = 'DELAYED'  THEN 2
                WHEN fo.status = 'CANCELLED' THEN 3
                ELSE 4
            END
        """, conn, params=fo_params if fo_params else None)

        # --- Summary KPIs (now includes planned) ---
        df_summary = pd.read_sql(f"""
            SELECT
                COUNT(*) as total_flights,
                SUM(CASE WHEN fo.status='DEPARTED'  THEN 1 ELSE 0 END) as departed,
                SUM(CASE WHEN fo.status='DELAYED'   THEN 1 ELSE 0 END) as delayed,
                SUM(CASE WHEN fo.status='CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                SUM(CASE WHEN fo.status='PLANNED'   THEN 1 ELSE 0 END) as planned
            FROM flight_operation fo
            {fo_join}
            {fo_where}
        """, conn, params=fo_params if fo_params else None)

        # --- Hourly departures (demand/capacity view) ---
        df_hourly = pd.read_sql(f"""
            SELECT
                EXTRACT(HOUR FROM fp.sobt)::int AS hour_bucket,
                COUNT(*) AS flight_count
            FROM flight_plan fp
            JOIN flight_operation fo ON fo.flight_plan_id = fp.flight_plan_id
            {where_fp}
            GROUP BY hour_bucket
            ORDER BY hour_bucket
        """, conn, params=params if params else None)

        conn.close()

        # --- Derived KPIs ---
        summary     = df_summary.iloc[0]
        total_flights = int(summary['total_flights'] or 0)
        departed      = int(summary['departed']      or 0)
        delayed       = int(summary['delayed']       or 0)
        cancelled     = int(summary['cancelled']     or 0)
        planned       = int(summary['planned']       or 0)

        # On-Time Performance % (only meaningful when flights have operated)
        operated = departed + delayed
        otp = round((departed / operated) * 100, 1) if operated > 0 else None

        # OTP colour band for gauge: green ≥85, amber 70-84, red <70
        if otp is None:
            otp_color = '#4a6080'
        elif otp >= 85:
            otp_color = '#1eb87a'
        elif otp >= 70:
            otp_color = '#f5a623'
        else:
            otp_color = '#e63946'

        # --- Hourly data — full 00-23 array ---
        hourly_dict   = dict(zip(df_hourly['hour_bucket'].tolist(),
                                 df_hourly['flight_count'].tolist()))
        hourly_counts = [int(hourly_dict.get(h, 0)) for h in range(24)]
        hour_labels   = [f'{h:02d}' for h in range(24)]

        # Capacity threshold: 30% above observed peak (simulates declared airport capacity)
        peak = max(hourly_counts) if any(hourly_counts) else 0
        capacity_threshold = math.ceil(peak * 1.35) if peak > 0 else 5

        airline_labels = df_airline['airline_code'].tolist()
        airline_counts = df_airline['total'].tolist()
        status_labels  = df_status['status'].tolist()
        status_counts  = df_status['total'].tolist()

        return render_template('dashboard.html',
            # KPI tiles
            total_flights=total_flights,
            departed=departed,
            delayed=delayed,
            cancelled=cancelled,
            planned=planned,
            otp=otp,
            otp_color=otp_color,
            # Charts
            airline_labels=airline_labels,
            airline_counts=airline_counts,
            status_labels=status_labels,
            status_counts=status_counts,
            hourly_counts=hourly_counts,
            hour_labels=hour_labels,
            capacity_threshold=capacity_threshold,
            # Meta
            today_date=date.today().strftime('%d %b %Y'),
            username=session.get('full_name'),
            role=role,
            airlines_list=airlines_list,
            airline_filter=airline_filter,
            status_filter=status_filter,
        )

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('login'))

# ================================================
# FLIGHTS ROUTE  — Phase 3
# ICAO columns · filters · delay · pagination
# ================================================
@app.route('/flights')
def flights():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn     = get_db()
        role     = session.get('role')
        PER_PAGE = 25

        # ── Resolve filter params ──────────────────────
        # airline_operator is always locked to their airline
        if role == 'airline_operator' and session.get('airline_code'):
            airline_filter = session.get('airline_code')
        else:
            airline_filter = request.args.get('airline_filter', '').strip()

        status_filter = request.args.get('status_filter', '').strip()
        search_q      = request.args.get('q', '').strip()

        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1

        # ── Airlines dropdown list ─────────────────────
        df_airlines = pd.read_sql(
            "SELECT airline_code, airline_name FROM airline_master ORDER BY airline_code",
            conn
        )
        airlines_list = df_airlines.to_dict('records')

        # ── Build WHERE clause ─────────────────────────
        conditions, params = [], {}

        if airline_filter:
            conditions.append("fp.airline_code = %(airline_filter)s")
            params['airline_filter'] = airline_filter
        if status_filter:
            conditions.append("fo.status = %(status_filter)s")
            params['status_filter'] = status_filter
        if search_q:
            conditions.append("""(
                fp.flight_no   ILIKE %(search)s OR
                fp.origin      ILIKE %(search)s OR
                fp.destination ILIKE %(search)s OR
                am.airline_name ILIKE %(search)s
            )""")
            params['search'] = f'%{search_q}%'

        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

        # ── Total count for pagination ─────────────────
        cnt_df = pd.read_sql(f"""
            SELECT COUNT(*) AS cnt
            FROM flight_plan fp
            JOIN flight_operation fo ON fp.flight_plan_id = fo.flight_plan_id
            JOIN airline_master am   ON fp.airline_code   = am.airline_code
            {where}
        """, conn, params=params if params else None)

        total_count = int(cnt_df.iloc[0]['cnt'])
        total_pages = max(1, math.ceil(total_count / PER_PAGE))
        page        = min(page, total_pages)
        offset      = (page - 1) * PER_PAGE

        # ── Main query with ICAO fields + delay ────────
        paged_params = {**params, 'limit': PER_PAGE, 'offset': offset}
        df = pd.read_sql(f"""
            SELECT
                fp.flight_plan_id,
                fp.flight_no,
                fp.airline_code,
                am.airline_name,
                fp.origin,
                ap1.airport_name  AS origin_name,
                fp.destination,
                ap2.airport_name  AS dest_name,
                fp.sobt,
                fo.aobt,
                fo.atot,
                fo.stand,
                fo.runway,
                fo.status,
                CASE
                    WHEN fo.aobt IS NOT NULL AND fp.sobt IS NOT NULL
                    THEN ROUND(EXTRACT(EPOCH FROM (fo.aobt - fp.sobt)) / 60)
                    ELSE NULL
                END AS delay_minutes
            FROM flight_plan fp
            JOIN flight_operation fo  ON fp.flight_plan_id = fo.flight_plan_id
            JOIN airline_master am    ON fp.airline_code   = am.airline_code
            JOIN airport_master ap1   ON fp.origin        = ap1.airport_code
            JOIN airport_master ap2   ON fp.destination   = ap2.airport_code
            {where}
            ORDER BY fp.sobt ASC, fp.flight_plan_id ASC
            LIMIT %(limit)s OFFSET %(offset)s
        """, conn, params=paged_params)

        conn.close()

        # Sanitise NaN → None so Jinja2 `is none` works
        flights_list = df.to_dict('records')
        for f in flights_list:
            dm = f.get('delay_minutes')
            if dm is not None:
                try:
                    f['delay_minutes'] = None if math.isnan(float(dm)) else float(dm)
                except (TypeError, ValueError):
                    f['delay_minutes'] = None

        # ── Build base query string for pagination links ──
        qs_parts = {k: v for k, v in [
            ('airline_filter', airline_filter),
            ('status_filter',  status_filter),
            ('q',              search_q),
        ] if v}
        base_qs = urlencode(qs_parts)

        return render_template('flights.html',
            flights=flights_list,
            username=session.get('full_name'),
            role=role,
            # filters
            airlines_list=airlines_list,
            airline_filter=airline_filter,
            status_filter=status_filter,
            search_q=search_q,
            # pagination
            page=page,
            total_pages=total_pages,
            total_count=total_count,
            per_page=PER_PAGE,
            base_qs=base_qs,
        )

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('login'))

# ================================================
# MAP ROUTE  — Phase 4
# Leaflet.js flight map with dark CartoDB tiles,
# airport markers, colour-coded route arcs,
# and per-status layer toggles.
# ================================================
@app.route('/map')
def map_view():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        conn = get_db()
        role = session.get('role')

        # Airport markers (sized by operation count)
        df_apt = pd.read_sql("""
            SELECT am.airport_code, am.airport_name,
                   am.latitude, am.longitude,
                   COUNT(DISTINCT fp.flight_plan_id) AS ops_count
            FROM airport_master am
            LEFT JOIN flight_plan fp
                   ON am.airport_code = fp.origin
                   OR am.airport_code = fp.destination
            WHERE am.latitude IS NOT NULL
            GROUP BY am.airport_code, am.airport_name,
                     am.latitude, am.longitude
            ORDER BY am.airport_code
        """, conn)

        # Flight routes with origin/dest coordinates
        conds  = ["ap1.latitude IS NOT NULL", "ap2.latitude IS NOT NULL"]
        params = {}
        if role == 'airline_operator' and session.get('airline_code'):
            conds.append("fp.airline_code = %(airline)s")
            params['airline'] = session.get('airline_code')
        where = 'WHERE ' + ' AND '.join(conds)

        df_routes = pd.read_sql(f"""
            SELECT fp.flight_plan_id,
                   fp.flight_no,
                   fp.airline_code,
                   am.airline_name,
                   fp.origin,
                   ap1.latitude   AS orig_lat,
                   ap1.longitude  AS orig_lon,
                   fp.destination AS dest,
                   ap2.latitude   AS dest_lat,
                   ap2.longitude  AS dest_lon,
                   fp.sobt,
                   fo.status,
                   CASE
                     WHEN fo.aobt IS NOT NULL AND fp.sobt IS NOT NULL
                     THEN ROUND(EXTRACT(EPOCH FROM (fo.aobt - fp.sobt))/60)
                     ELSE NULL
                   END AS delay_minutes
            FROM flight_plan fp
            JOIN flight_operation fo  ON fp.flight_plan_id = fo.flight_plan_id
            JOIN airline_master am    ON fp.airline_code   = am.airline_code
            JOIN airport_master ap1   ON fp.origin        = ap1.airport_code
            JOIN airport_master ap2   ON fp.destination   = ap2.airport_code
            {where}
            ORDER BY fp.sobt ASC
        """, conn, params=params if params else None)

        conn.close()

        # Serialise airports
        airports = []
        for _, r in df_apt.iterrows():
            try:
                lat = float(r['latitude'])
                lon = float(r['longitude'])
                if math.isnan(lat) or math.isnan(lon):
                    continue
                airports.append({
                    'code': r['airport_code'],
                    'name': r['airport_name'],
                    'lat':  lat,
                    'lon':  lon,
                    'ops':  int(r['ops_count']),
                })
            except (TypeError, ValueError):
                continue

        # Serialise routes
        routes = []
        for _, r in df_routes.iterrows():
            dm = r.get('delay_minutes')
            try:
                dm = None if dm is None or math.isnan(float(dm)) else int(dm)
            except (TypeError, ValueError):
                dm = None
            routes.append({
                'id':           int(r['flight_plan_id']),
                'callsign':     r['flight_no'],
                'airline':      r['airline_code'],
                'airline_name': r['airline_name'],
                'origin':       r['origin'],
                'dest':         r['dest'],
                'orig_lat':     float(r['orig_lat']),
                'orig_lon':     float(r['orig_lon']),
                'dest_lat':     float(r['dest_lat']),
                'dest_lon':     float(r['dest_lon']),
                'sobt':         utc_time_filter(r['sobt']),
                'status':       str(r['status'] or ''),
                'delay':        dm,
            })

        # Status counts for layer panel
        status_counts = {}
        for rt in routes:
            s = rt['status']
            status_counts[s] = status_counts.get(s, 0) + 1

        return render_template('map.html',
            airports=airports,
            routes=routes,
            status_counts=status_counts,
            total_routes=len(routes),
            username=session.get('full_name'),
            role=role,
        )
    except Exception as e:
        flash(f'Map error: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

# ================================================
# UPLOAD ROUTE
# Saves CSV and inserts data to database
# Only system_admin and airline_operator
# have permission to upload
# ================================================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') not in [
        'system_admin', 'airline_operator'
    ]:
        flash('You do not have permission!', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        file = request.files['file']

        if file and file.filename.endswith('.csv'):
            try:
                # Step 1: Save file to uploads folder
                filepath = os.path.join(
                    UPLOAD_FOLDER, file.filename
                )
                file.save(filepath)

                # Step 2: Read CSV file
                df = pd.read_csv(filepath)

                # Step 3: Connect to database
                conn = get_db()
                cur = conn.cursor()

                success = 0
                skipped = 0

                # Step 4: Loop through each row
                for index, row in df.iterrows():
                    try:
                        airline = str(row['airline_code']).strip()
                        origin = str(row['origin']).strip()
                        dest = str(row['destination']).strip()
                        sobt = str(row['sobt']).strip()
                        status = str(row['status']).strip()
                        flight_no = str(row['flight_no']).strip()

                        # Check airline exists
                        cur.execute("""
                            SELECT airline_code
                            FROM airline_master
                            WHERE airline_code = %s
                        """, (airline,))
                        airline_exists = cur.fetchone()

                        # Check origin exists
                        cur.execute("""
                            SELECT airport_code
                            FROM airport_master
                            WHERE airport_code = %s
                        """, (origin,))
                        origin_exists = cur.fetchone()

                        # Check destination exists
                        cur.execute("""
                            SELECT airport_code
                            FROM airport_master
                            WHERE airport_code = %s
                        """, (dest,))
                        dest_exists = cur.fetchone()

                        # Check duplicate
                        cur.execute("""
                            SELECT flight_no
                            FROM flight_plan
                            WHERE flight_no = %s
                        """, (flight_no,))
                        already_exists = cur.fetchone()

                        # Insert if valid and not duplicate
                        if (airline_exists and
                            origin_exists and
                            dest_exists and
                            not already_exists):

                            # Insert into flight_plan
                            cur.execute("""
                                INSERT INTO flight_plan
                                (flight_no, airline_code,
                                origin, destination,
                                sobt, created_by)
                                VALUES (%s,%s,%s,%s,%s,%s)
                            """, (
                                flight_no,
                                airline,
                                origin,
                                dest,
                                sobt,
                                session['user_id']
                            ))

                            # Insert into flight_operation
                            cur.execute("""
                                INSERT INTO flight_operation
                                (flight_plan_id, status)
                                VALUES (
                                    currval('flight_plan_flight_plan_id_seq'),
                                    %s
                                )
                            """, (status,))

                            success += 1
                        else:
                            skipped += 1

                    except Exception as e:
                        skipped += 1
                        continue

                # Save all to database
                conn.commit()
                cur.close()
                conn.close()

                flash(
                    f'Upload successful! '
                    f'{success} new flights added, '
                    f'{skipped} rows skipped!',
                    'success'
                )

            except Exception as e:
                flash(f'Error: {str(e)}', 'danger')

        else:
            flash('Please upload a CSV file!', 'danger')

    return render_template('upload.html',
        username=session.get('full_name'),
        role=session.get('role')
    )

# ================================================
# EDIT FLIGHT ROUTE  (Day 5)
# Updates stand, runway, or status depending on
# the user's role:
#   system_admin    → stand + runway + status
#   atc_controller  → runway only
#   airport_ops     → stand only
#   airline_operator → status only
#   observer / ai_analyst → forbidden
# ================================================
@app.route('/edit_flight/<int:flight_plan_id>',
           methods=['POST'])
def edit_flight(flight_plan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    role = session.get('role')

    # Only these roles can edit
    allowed = [
        'system_admin',
        'atc_controller',
        'airport_ops',
        'airline_operator'
    ]
    if role not in allowed:
        flash('You do not have permission to edit flights!',
              'danger')
        return redirect(url_for('flights'))

    try:
        conn = get_db()
        cur = conn.cursor()

        if role == 'system_admin':
            cur.execute("""
                UPDATE flight_operation
                SET stand  = %s,
                    runway = %s,
                    status = %s
                WHERE flight_plan_id = %s
            """, (
                request.form.get('stand', '').strip(),
                request.form.get('runway', '').strip(),
                request.form.get('status', '').strip(),
                flight_plan_id
            ))

        elif role == 'atc_controller':
            cur.execute("""
                UPDATE flight_operation
                SET runway = %s
                WHERE flight_plan_id = %s
            """, (
                request.form.get('runway', '').strip(),
                flight_plan_id
            ))

        elif role == 'airport_ops':
            cur.execute("""
                UPDATE flight_operation
                SET stand = %s
                WHERE flight_plan_id = %s
            """, (
                request.form.get('stand', '').strip(),
                flight_plan_id
            ))

        elif role == 'airline_operator':
            cur.execute("""
                UPDATE flight_operation
                SET status = %s
                WHERE flight_plan_id = %s
            """, (
                request.form.get('status', '').strip(),
                flight_plan_id
            ))

        conn.commit()
        cur.close()
        conn.close()
        flash(f'Flight #{flight_plan_id} updated successfully!',
              'success')

    except Exception as e:
        flash(f'Error updating flight: {str(e)}', 'danger')

    return redirect(url_for('flights'))


# ================================================
# AUDIT LOG ROUTE  (Day 5)
# Shows audit_log table — system_admin only
# ================================================
@app.route('/audit')
def audit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'system_admin':
        flash('Access denied — admin only.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        conn = get_db()
        df = pd.read_sql("""
            SELECT
                al.audit_id,
                al.table_name,
                al.record_id,
                al.action,
                u.username   AS changed_by,
                al.changed_at
            FROM audit_log al
            LEFT JOIN app_user u
                ON al.changed_by = u.user_id
            ORDER BY al.changed_at DESC
            LIMIT 100
        """, conn)
        conn.close()
        logs = df.to_dict('records')
        return render_template('audit.html',
            logs=logs,
            username=session.get('full_name'),
            role=session.get('role')
        )
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))


# ================================================
# ALERTS ROUTE  — Phase 5
# Lists active alerts with per-user dismissal state.
# system_admin can create / deactivate alerts.
# ================================================
@app.route('/alerts')
def alerts():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        conn = get_db()
        cur  = conn.cursor()
        uid  = session['user_id']

        # Run auto-alert check on page load
        _check_auto_delay_alert(conn, cur)

        severity_filter = request.args.get('severity', '').strip().upper()
        sev_cond  = 'AND a.severity = %s' if severity_filter else ''
        sev_param = [severity_filter] if severity_filter else []

        cur.execute(f"""
            SELECT a.alert_id, a.severity, a.category, a.title, a.body,
                   a.valid_from, a.valid_to, a.created_at,
                   u.username AS created_by,
                   EXISTS(
                       SELECT 1 FROM alert_dismissal d
                       WHERE d.alert_id = a.alert_id AND d.user_id = %s
                   ) AS dismissed
            FROM atfm_alert a
            LEFT JOIN app_user u ON a.created_by = u.user_id
            WHERE a.is_active = TRUE
            {sev_cond}
            ORDER BY
                CASE a.severity WHEN 'CRITICAL' THEN 1
                                WHEN 'CAUTION'  THEN 2 ELSE 3 END,
                a.created_at DESC
        """, [uid] + sev_param)

        rows = cur.fetchall()
        cols = ['alert_id','severity','category','title','body',
                'valid_from','valid_to','created_at','created_by','dismissed']
        alerts_list = [dict(zip(cols, r)) for r in rows]

        cur.close()
        conn.close()

        return render_template('alerts.html',
            alerts=alerts_list,
            severity_filter=severity_filter,
            username=session.get('full_name'),
            role=session.get('role'),
        )
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/alerts/create', methods=['POST'])
def alerts_create():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'system_admin':
        flash('Admin only.', 'danger')
        return redirect(url_for('alerts'))

    severity = request.form.get('severity', '').strip()
    category = request.form.get('category', 'OPERATIONS').strip()
    title    = request.form.get('title', '').strip()
    body     = request.form.get('body', '').strip()
    valid_to = request.form.get('valid_to', '').strip() or None

    if not severity or not title:
        flash('Severity and title are required.', 'danger')
        return redirect(url_for('alerts'))

    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO atfm_alert (severity, category, title, body, valid_to, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (severity, category, title, body, valid_to, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        flash('Alert issued successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('alerts'))


@app.route('/alerts/dismiss/<int:alert_id>', methods=['POST'])
def alerts_dismiss(alert_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO alert_dismissal (alert_id, user_id)
            VALUES (%s, %s)
            ON CONFLICT (alert_id, user_id) DO NOTHING
        """, (alert_id, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass
    return redirect(request.referrer or url_for('alerts'))


@app.route('/alerts/deactivate/<int:alert_id>', methods=['POST'])
def alerts_deactivate(alert_id):
    """system_admin only — hard-deactivate an alert for all users."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'system_admin':
        flash('Admin only.', 'danger')
        return redirect(url_for('alerts'))
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("UPDATE atfm_alert SET is_active = FALSE WHERE alert_id = %s",
                    (alert_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Alert deactivated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('alerts'))


@app.route('/api/alerts/count')
def api_alerts_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM atfm_alert a
            WHERE a.is_active = TRUE
              AND (a.valid_to IS NULL OR a.valid_to > now())
              AND NOT EXISTS (
                  SELECT 1 FROM alert_dismissal d
                  WHERE d.alert_id = a.alert_id AND d.user_id = %s
              )
        """, (session['user_id'],))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({'count': count})
    except Exception:
        return jsonify({'count': 0})


# ================================================
# RUN THE APPLICATION
# debug=True shows errors clearly
# ================================================
if __name__ == '__main__':
    # Port 8080 used because macOS AirPlay occupies port 5000
    app.run(port=8081, debug=True)