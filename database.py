import sqlite3
import hashlib
import os

DB_NAME = "guard_gr.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db_exists = os.path.exists(DB_NAME)
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de Empresas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            logo_url TEXT,
            cor_primaria TEXT DEFAULT '#003366',
            cor_secundaria TEXT DEFAULT '#f0f2f6',
            compartilhar_historico INTEGER DEFAULT 0,
            limite_advertencias INTEGER DEFAULT 3,
            intervalo_dias_regra INTEGER DEFAULT 90,
            limite_suspensoes_exclusao INTEGER DEFAULT 3,
            dias_susp_1 INTEGER DEFAULT 7,
            dias_susp_2 INTEGER DEFAULT 15
        )
    ''')

    # Tabela de Usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        empresa_id INTEGER,
        role TEXT DEFAULT 'Portaria',
        cpf TEXT,
        data_nascimento TEXT,
        email TEXT,
        FOREIGN KEY (empresa_id) REFERENCES empresas (id)
    )
    ''')
    # Garantir colunas adicionais caso a tabela já exista sem elas
    try:
        cursor.execute('ALTER TABLE usuarios ADD COLUMN cpf TEXT')
    except Exception:
        pass
    try:
        cursor.execute('ALTER TABLE usuarios ADD COLUMN data_nascimento TEXT')
    except Exception:
        pass
    try:
        cursor.execute('ALTER TABLE usuarios ADD COLUMN email TEXT')
    except Exception:
        pass

    # Tabela de Motoristas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS motoristas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT NOT NULL,
            cnh TEXT,
            categoria TEXT,
            status_interno TEXT DEFAULT 'Ativo',
            status_sil TEXT DEFAULT 'Não consultado',
            data_consulta_sil TEXT,
            data_fim_suspensao TEXT,
            empresa_id INTEGER,
            UNIQUE(cpf, empresa_id),
            FOREIGN KEY (empresa_id) REFERENCES empresas (id)
        )
    ''')

    # Tabela de Ocorrências (Mantida para Fase 2)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            motivo TEXT,
            gravidade TEXT,
            data TEXT NOT NULL,
            usuario_id INTEGER,
            motorista_id INTEGER,
            empresa_id INTEGER,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
            FOREIGN KEY (motorista_id) REFERENCES motoristas (id),
            FOREIGN KEY (empresa_id) REFERENCES empresas (id)
        )
    ''')

    # Tabela de Histórico de Consultas / Portaria (Nova funcionalidade)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros_acesso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motorista_id INTEGER,
            cpf TEXT,
            status_resultado TEXT,
            data_hora TEXT,
            usuario_id INTEGER,
            empresa_id INTEGER,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
            FOREIGN KEY (motorista_id) REFERENCES motoristas (id),
            FOREIGN KEY (empresa_id) REFERENCES empresas (id)
        )
    ''')

    conn.commit()

    if not db_exists:
        seed_data(conn)
    
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()
    
    # Inserir Empresa BBM
    cursor.execute('''
        INSERT INTO empresas (nome, logo_url, cor_primaria, cor_secundaria)
        VALUES (?, ?, ?, ?)
    ''', ('Grupo BBM', 'https://www.bbmlogistica.com.br/wp-content/themes/bbm/assets/images/logo.png', '#003366', '#FFFFFF'))
    bbm_id = cursor.lastrowid

    # Inserir Usuários para BBM (Senha padrão: admin123)
    senha_hash = hashlib.sha256("admin123".encode()).hexdigest()
    
    cursor.execute('''
        INSERT INTO usuarios (nome, login, senha, empresa_id, role)
        VALUES (?, ?, ?, ?, ?)
    ''', ('Administrador BBM', 'admin_bbm', senha_hash, bbm_id, 'Admin'))


    # Inserir uma segunda empresa para testar multi-tenancy
    cursor.execute('''
        INSERT INTO empresas (nome, logo_url, cor_primaria, cor_secundaria)
        VALUES (?, ?, ?, ?)
    ''', ('Logistica Express', 'https://via.placeholder.com/150', '#FF5733', '#FFFFFF'))
    log_exp_id = cursor.lastrowid

    cursor.execute('''
        INSERT INTO usuarios (nome, login, senha, empresa_id, role)
        VALUES (?, ?, ?, ?, ?)
    ''', ('Admin Express', 'admin_exp', senha_hash, log_exp_id, 'Admin'))

    conn.commit()
    print("Banco de dados inicializado e populado com dados de exemplo.")

if __name__ == "__main__":
    init_db()
