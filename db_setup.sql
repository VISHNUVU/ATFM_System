-- ================================================
-- ATFM SYSTEM - COMPLETE DATABASE SETUP
-- Run this file once to build the full database
-- Combines: Day 1 + Day 2 + Day 3 + Day 4 patch
-- ================================================

-- ================================================
-- DAY 1: CREATE ALL TABLES
-- ================================================

CREATE TABLE IF NOT EXISTS app_user (
    user_id         SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       VARCHAR(100),
    is_active       BOOLEAN DEFAULT true,
    airline_code    VARCHAR(5),
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role (
    role_id         SERIAL PRIMARY KEY,
    role_name       VARCHAR(50) NOT NULL UNIQUE,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS permission (
    permission_id   SERIAL PRIMARY KEY,
    resource        VARCHAR(100) NOT NULL,
    action          VARCHAR(50) NOT NULL,
    UNIQUE(resource, action)
);

CREATE TABLE IF NOT EXISTS user_role (
    user_id         INT REFERENCES app_user(user_id) ON DELETE CASCADE,
    role_id         INT REFERENCES role(role_id) ON DELETE CASCADE,
    assigned_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permission (
    role_id         INT REFERENCES role(role_id) ON DELETE CASCADE,
    permission_id   INT REFERENCES permission(permission_id) ON DELETE CASCADE,
    granted_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_login_history (
    login_id        SERIAL PRIMARY KEY,
    user_id         INT REFERENCES app_user(user_id),
    login_time      TIMESTAMPTZ DEFAULT now(),
    ip_address      INET,
    success         BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id        SERIAL PRIMARY KEY,
    table_name      VARCHAR(100),
    record_id       INT,
    action          VARCHAR(20),
    changed_by      INT REFERENCES app_user(user_id),
    changed_at      TIMESTAMPTZ DEFAULT now()
);

-- Audit trigger function: reads app.current_user_id set by Flask
CREATE OR REPLACE FUNCTION fn_audit_log()
RETURNS TRIGGER AS $$
DECLARE
    v_user_id INTEGER;
    v_record_id INTEGER;
BEGIN
    BEGIN
        v_user_id := current_setting('app.current_user_id', true)::INTEGER;
    EXCEPTION WHEN OTHERS THEN
        v_user_id := NULL;
    END;

    IF TG_OP = 'DELETE' THEN
        IF TG_TABLE_NAME = 'flight_plan' THEN
            v_record_id := OLD.flight_plan_id;
        ELSIF TG_TABLE_NAME = 'flight_operation' THEN
            v_record_id := OLD.op_id;
        END IF;
    ELSE
        IF TG_TABLE_NAME = 'flight_plan' THEN
            v_record_id := NEW.flight_plan_id;
        ELSIF TG_TABLE_NAME = 'flight_operation' THEN
            v_record_id := NEW.op_id;
        END IF;
    END IF;

    INSERT INTO audit_log (table_name, record_id, action, changed_by, changed_at)
    VALUES (TG_TABLE_NAME, v_record_id, TG_OP, v_user_id, now());

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS airline_master (
    airline_code VARCHAR(5) PRIMARY KEY,
    airline_name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS airport_master (
    airport_code VARCHAR(5) PRIMARY KEY,
    airport_name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS flight_plan (
    flight_plan_id  SERIAL PRIMARY KEY,
    flight_no       VARCHAR(10),
    airline_code    VARCHAR(5) REFERENCES airline_master(airline_code),
    origin          VARCHAR(5) REFERENCES airport_master(airport_code),
    destination     VARCHAR(5) REFERENCES airport_master(airport_code),
    sobt            TIMESTAMPTZ,
    created_by      INT REFERENCES app_user(user_id)
);

CREATE TABLE IF NOT EXISTS flight_operation (
    op_id           SERIAL PRIMARY KEY,
    flight_plan_id  INT REFERENCES flight_plan(flight_plan_id),
    aobt            TIMESTAMPTZ,
    atot            TIMESTAMPTZ,
    stand           VARCHAR(10),
    runway          VARCHAR(10),
    status          VARCHAR(20)
);

-- ================================================
-- DAY 2: ROLES, PERMISSIONS, USERS
-- ================================================

INSERT INTO role (role_name, description) VALUES
('system_admin',     'Full system control - can do everything'),
('airline_operator', 'Manages own airline flights only'),
('atc_controller',   'Controls departure and arrival slots'),
('airport_ops',      'Manages stands and runways'),
('ai_analyst',       'Trains and views AI predictions'),
('observer',         'Read only access - cannot change anything')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO permission (resource, action) VALUES
('flight_plan', 'create'),
('flight_plan', 'read'),
('flight_plan', 'update'),
('stand',       'read'),
('stand',       'update'),
('runway',      'read'),
('runway',      'update'),
('ai_model',    'train'),
('ai_model',    'view'),
('user',        'manage')
ON CONFLICT (resource, action) DO NOTHING;

-- 6 sample users — password for all: password123
INSERT INTO app_user (username, email, password_hash, full_name, is_active, airline_code) VALUES
('admin1',       'admin@atfm.com', '$2b$12$MevNVbNnuwn.odqf/0R59O9rodmP2QcBuHK.HD5JvzbafI62QninO', 'System Admin',          true, NULL),
('airline_ba',   'ba@airline.com', '$2b$12$nJ3qH3/NzjeUHoAr089XnuT9QWyUAYWjqprgJcOPPG81AItEYC/PG', 'British Airways Ops',   true, 'AA'),
('atc_dxb',      'atc@dxb.com',   '$2b$12$2b4M6E03eQ8qQ0PcONBtruv3TPhmn7SIkvdjnHA2cGAFat7DZEbqW', 'Dubai ATC Controller',  true, NULL),
('airport_ops1', 'ops@dxb.com',   '$2b$12$2De3ZCNv0fdqxazcJXp1ruiV2VZof1/ZJPluxTQ2sYK3fNHIE/C22', 'Airport Operations',    true, NULL),
('ai_analyst1',  'ai@atfm.com',   '$2b$12$tcqbKeLucwp.e9SqDCnvC.M9iVO9pbgnzRw3lhhisYVYTYTa7A8F6', 'AI Data Analyst',       true, NULL),
('observer1',    'obs@caa.com',   '$2b$12$TgfzP2Z/apuI2gIxQvjG9OMnSGNSanyeMD9yP6zZ5UeiR5Jj9eD3K', 'CAA Regulator',         true, NULL)
ON CONFLICT (username) DO NOTHING;

INSERT INTO user_role (user_id, role_id)
SELECT u.user_id, r.role_id FROM app_user u, role r
WHERE (u.username='admin1'       AND r.role_name='system_admin')
   OR (u.username='airline_ba'   AND r.role_name='airline_operator')
   OR (u.username='atc_dxb'      AND r.role_name='atc_controller')
   OR (u.username='airport_ops1' AND r.role_name='airport_ops')
   OR (u.username='ai_analyst1'  AND r.role_name='ai_analyst')
   OR (u.username='observer1'    AND r.role_name='observer')
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM role r, permission p
WHERE r.role_name = 'system_admin'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM role r, permission p
WHERE r.role_name = 'airline_operator'
  AND p.resource = 'flight_plan'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM role r, permission p
WHERE r.role_name = 'atc_controller'
  AND p.resource = 'runway'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM role r, permission p
WHERE r.role_name = 'airport_ops'
  AND p.resource = 'stand'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM role r, permission p
WHERE r.role_name = 'ai_analyst'
  AND p.resource = 'ai_model'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM role r, permission p
WHERE r.role_name = 'observer'
  AND p.action = 'read'
ON CONFLICT DO NOTHING;

-- ================================================
-- DAY 3: MASTER DATA AND FLIGHTS
-- ================================================

INSERT INTO airline_master (airline_code, airline_name) VALUES
('AA', 'American Airlines'),
('UA', 'United Airlines'),
('F9', 'Frontier Airlines'),
('DL', 'Delta Air Lines'),
('AS', 'Alaska Airlines'),
('B6', 'JetBlue Airways'),
('NK', 'Spirit Airlines'),
('WN', 'Southwest Airlines'),
('MQ', 'Envoy Air'),
('OH', 'PSA Airlines'),
('OO', 'SkyWest Airlines'),
('EV', 'ExpressJet Airlines'),
('9E', 'Endeavor Air'),
('YV', 'Mesa Airlines'),
('YX', 'Republic Airways'),
('G4', 'Allegiant Air')
ON CONFLICT (airline_code) DO NOTHING;

INSERT INTO airport_master (airport_code, airport_name) VALUES
('PHX', 'Phoenix Sky Harbor International'),
('CLT', 'Charlotte Douglas International'),
('DEN', 'Denver International'),
('RDU', 'Raleigh Durham International'),
('LAX', 'Los Angeles International'),
('EWR', 'Newark Liberty International'),
('MIA', 'Miami International'),
('JFK', 'New York John F Kennedy International'),
('ORD', 'Chicago O Hare International'),
('SFO', 'San Francisco International'),
('SEA', 'Seattle Tacoma International'),
('ANC', 'Ted Stevens Anchorage International'),
('LAS', 'Harry Reid International'),
('AUS', 'Austin Bergstrom International'),
('FLL', 'Fort Lauderdale Hollywood International'),
('TPA', 'Tampa International'),
('PHL', 'Philadelphia International'),
('SJU', 'Luis Munoz Marin International'),
('MSP', 'Minneapolis Saint Paul International'),
('SMF', 'Sacramento International'),
('IAH', 'George Bush Intercontinental'),
('ATL', 'Hartsfield Jackson Atlanta International'),
('DTW', 'Detroit Metropolitan Wayne County'),
('MCO', 'Orlando International'),
('TUS', 'Tucson International'),
('RNO', 'Reno Tahoe International'),
('PDX', 'Portland International'),
('FAR', 'Hector International'),
('AGS', 'Augusta Regional'),
('PSP', 'Palm Springs International'),
('SLC', 'Salt Lake City International'),
('SBP', 'San Luis Obispo County Regional'),
('EYW', 'Key West International'),
('AMA', 'Rick Husband Amarillo International'),
('CHO', 'Charlottesville Albemarle'),
('ELP', 'El Paso International'),
('OKC', 'Will Rogers World'),
('SAN', 'San Diego International'),
('MKE', 'Milwaukee Mitchell International'),
('STT', 'Cyril E King'),
('IND', 'Indianapolis International'),
('STL', 'St Louis Lambert International')
ON CONFLICT (airport_code) DO NOTHING;

INSERT INTO flight_plan (flight_no, airline_code, origin, destination, sobt, created_by) VALUES
('AA_PHX_CLT', 'AA', 'PHX', 'CLT', '2020-01-01 00:05:00+00', 2),
('F9_DEN_RDU', 'F9', 'DEN', 'RDU', '2020-01-01 00:05:00+00', 2),
('UA_LAX_EWR', 'UA', 'LAX', 'EWR', '2020-01-01 00:15:00+00', 2),
('AA_PHX_MIA', 'AA', 'PHX', 'MIA', '2020-01-01 00:20:00+00', 2),
('AA_PHX_JFK', 'AA', 'PHX', 'JFK', '2020-01-01 00:23:00+00', 2),
('F9_DEN_MIA', 'F9', 'DEN', 'MIA', '2020-01-01 00:29:00+00', 2),
('B6_LAX_JFK', 'B6', 'LAX', 'JFK', '2020-01-01 00:30:00+00', 2),
('AS_PHX_ANC', 'AS', 'PHX', 'ANC', '2020-01-01 00:35:00+00', 2),
('B6_PHX_FLL', 'B6', 'PHX', 'FLL', '2020-01-01 00:37:00+00', 2),
('F9_SFO_DEN', 'F9', 'SFO', 'DEN', '2020-01-01 00:39:00+00', 2),
('UA_SFO_EWR', 'UA', 'SFO', 'EWR', '2020-01-01 00:40:00+00', 2),
('AS_SEA_ANC', 'AS', 'SEA', 'ANC', '2020-01-01 00:40:00+00', 2),
('DL_LAX_MSP', 'DL', 'LAX', 'MSP', '2020-01-01 00:40:00+00', 2),
('UA_LAX_ORD', 'UA', 'LAX', 'ORD', '2020-01-01 00:48:00+00', 2),
('AA_PHX_PHL', 'AA', 'PHX', 'PHL', '2020-01-01 00:40:00+00', 2)
ON CONFLICT DO NOTHING;

INSERT INTO flight_operation (flight_plan_id, aobt, atot, stand, runway, status) VALUES
(1,  '2020-01-01 00:05:00+00', '2020-01-01 00:19:00+00', 'A1', '25R', 'DEPARTED'),
(2,  '2020-01-01 00:03:00+00', '2020-01-01 00:15:00+00', 'B1', '35R', 'DEPARTED'),
(3,  '2020-01-01 00:13:00+00', '2020-01-01 00:29:00+00', 'C1', '24R', 'DEPARTED'),
(4,  '2020-01-01 00:29:00+00', '2020-01-01 00:40:00+00', 'A2', '25R', 'DELAYED'),
(5,  '2020-01-01 00:34:00+00', '2020-01-01 00:47:00+00', 'A3', '25L', 'DELAYED'),
(6,  '2020-01-01 00:27:00+00', '2020-01-01 00:38:00+00', 'B2', '35L', 'DEPARTED'),
(7,  '2020-01-01 00:22:00+00', '2020-01-01 00:36:00+00', 'C2', '24L', 'DEPARTED'),
(8,  '2020-01-01 00:24:00+00', '2020-01-01 00:42:00+00', 'A4', '25R', 'DEPARTED'),
(9,  '2020-01-01 00:28:00+00', '2020-01-01 00:38:00+00', 'A5', '25L', 'DEPARTED'),
(10, '2020-01-01 00:29:00+00', '2020-01-01 00:41:00+00', 'D1', '28R', 'DEPARTED'),
(11, '2020-01-01 00:37:00+00', '2020-01-01 00:52:00+00', 'D2', '28L', 'DEPARTED'),
(12, '2020-01-01 00:36:00+00', '2020-01-01 00:50:00+00', 'E1', '16R', 'DEPARTED'),
(13, '2020-01-01 00:29:00+00', '2020-01-01 00:54:00+00', 'C3', '24R', 'DEPARTED'),
(14, '2020-01-01 00:40:00+00', '2020-01-01 00:52:00+00', 'C4', '24L', 'DEPARTED'),
(15, '2020-01-01 00:36:00+00', '2020-01-01 00:49:00+00', 'A6', '25R', 'DEPARTED')
ON CONFLICT DO NOTHING;

-- Audit triggers on flight_plan and flight_operation
DROP TRIGGER IF EXISTS trg_audit_flight_plan ON flight_plan;
DROP TRIGGER IF EXISTS trg_audit_flight_operation ON flight_operation;

CREATE TRIGGER trg_audit_flight_plan
AFTER INSERT OR UPDATE OR DELETE ON flight_plan
FOR EACH ROW EXECUTE FUNCTION fn_audit_log();

CREATE TRIGGER trg_audit_flight_operation
AFTER INSERT OR UPDATE OR DELETE ON flight_operation
FOR EACH ROW EXECUTE FUNCTION fn_audit_log();
