import logging
import os
import sqlite3
from datetime import datetime, timedelta
import hashlib
import pandas as pd
import fitz
import re
from concurrent.futures import ThreadPoolExecutor
from database import get_connection
import soap_client

# Configuração de Logs
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

sil_logger = logging.getLogger("SIL_Opentech")
sil_handler = logging.FileHandler(os.path.join(LOG_DIR, "consultas_portaria.log"), encoding='utf-8')
sil_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
sil_logger.addHandler(sil_handler)
sil_logger.setLevel(logging.INFO)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validar_cpf(cpf):
    """
    Valida CPF seguindo o algoritmo oficial. 
    Permite CPFs de 3 dígitos (123, 456) apenas para fins de teste/homologação.
    """
    # Remove caracteres não numéricos
    cpf = ''.join(filter(str.isdigit, cpf))

    # BYPASS PARA TESTE
    if len(cpf) == 3:
        return True

    if len(cpf) != 11:
        return False

    # Impede CPFs com todos os dígitos iguais (Ex: 111.111.111-11)
    if cpf == cpf[0] * 11:
        return False

    # Cálculo do primeiro dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digito_1 = (soma * 10 % 11) % 10

    # Cálculo do segundo dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digito_2 = (soma * 10 % 11) % 10

    return int(cpf[9]) == digito_1 and int(cpf[10]) == digito_2

def autenticar_usuario(login, senha):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.*, e.nome as empresa_nome, e.logo_url, e.cor_primaria, e.cor_secundaria, u.role
        FROM usuarios u
        JOIN empresas e ON u.empresa_id = e.id
        WHERE u.login = ? AND u.senha = ?
    ''', (login, hash_password(senha)))
    user = cursor.fetchone()
    conn.close()
    return user

# --- INTEGRAÇÃO MOCK SIL OPENTECH ---
def formatar_data_validade(data_expira_str):
    """
    Calcula o tempo restante para expiração e retorna uma string formatada.
    """
    if not data_expira_str or data_expira_str == "N/I":
        return "Validade: N/I"
    try:
        # Tenta converter a data (Opentech costuma enviar ISO 8601)
        # Ex: 2027-05-13T13:44:12-03:00
        data_limpa = data_expira_str.split('T')[0]
        dt_exp = datetime.strptime(data_limpa, "%Y-%m-%d")
        hoje = datetime.now()
        
        delta = dt_exp - hoje
        data_formatada = dt_exp.strftime("%d/%m/%Y")
        
        if delta.days < 0:
            return f"❌ Vencido em {data_formatada} (há {-delta.days} dias)"
        elif delta.days < 30:
            return f"⚠️ Vence em {data_formatada} ({delta.days} dias)"
        else:
            meses = delta.days // 30
            return f"✅ Vence em {data_formatada} ({meses} meses)"
    except Exception:
        return f"Validade: {data_expira_str}"

def consultar_opentech(cpf, token_empresa, usuario_nome="Sistema"):
    """
    Integração real com a API SIL Opentech.
    """
    cpf_limpo = ''.join(filter(str.isdigit, cpf))
    sil_logger.info(f"REQ | Usuário: {usuario_nome} | CPF: {cpf_limpo}")
    
    try:
        resultado = soap_client.consultar_motorista(cpf_limpo)
        if "error" in resultado:
            return {"nome": "Erro", "status": f"Erro: {resultado['error']}", "data_consulta": datetime.now().strftime("%d/%m/%Y %H:%M"), "validade": "N/I"}

        return {
            "nome": resultado.get("nome", "Não Identificado"),
            "cnh": resultado.get("cnh", "N/I"),
            "categoria": resultado.get("categoria", "N/I"),
            "status": resultado.get("status_label", "Sem Informação"),
            "data_consulta": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "validade": resultado.get("data_expiracao", "N/I")
        }
    except Exception as e:
        sil_logger.exception(f"FATAL | Erro ao consultar Opentech para CPF {cpf_limpo}")
        return {"nome": "Erro Fatal", "status": "Erro de Conexão", "data_consulta": datetime.now().strftime("%d/%m/%Y %H:%M"), "validade": "N/I"}

# --- GESTÃO DE MOTORISTAS ---
def listar_motoristas(empresa_id, busca=""):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT m.*, MAX(r.data_hora) as ultima_consulta 
        FROM motoristas m 
        LEFT JOIN registros_acesso r ON m.id = r.motorista_id AND r.empresa_id = m.empresa_id
        WHERE m.empresa_id = ?
    """
    params = [empresa_id]
    
    if busca:
        query += " AND (m.nome LIKE ? OR m.cpf LIKE ?)"
        params.extend([f"%{busca}%", f"%{busca}%"])
        
    query += " GROUP BY m.id ORDER BY COALESCE(ultima_consulta, '') DESC, m.id DESC"
    
    cursor.execute(query, params)
    motoristas = cursor.fetchall()
    conn.close()
    return motoristas

def verificar_validade_existente(cpf, empresa_id):
    """
    Verifica se o motorista já existe e se a consulta SIL ainda é válida.
    Retorna (existe, valida, data_expiracao)
    """
    cpf_limpo = ''.join(filter(str.isdigit, cpf))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT data_expiracao, nome FROM motoristas 
        WHERE cpf = ? AND empresa_id = ?
    ''', (cpf_limpo, empresa_id))
    res = cursor.fetchone()
    conn.close()
    
    if res:
        data_exp = res['data_expiracao']
        if not data_exp or data_exp == "N/I":
            return True, False, "N/I", res['nome']
        
        try:
            data_limpa = data_exp.split('T')[0]
            dt_exp = datetime.strptime(data_limpa, "%Y-%m-%d")
            if dt_exp > datetime.now():
                return True, True, dt_exp.strftime("%d/%m/%Y"), res['nome']
        except:
            pass
        return True, False, data_exp, res['nome']
    
    return False, False, None, None

def cadastrar_motorista(dados, empresa_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO motoristas (nome, cpf, cnh, categoria, status_sil, data_consulta_sil, data_expiracao, empresa_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dados['nome'], dados['cpf'], dados['cnh'], dados['categoria'], 
              dados['status_sil'], dados['data_consulta_sil'], dados.get('validade', 'N/I'), empresa_id))
        conn.commit()
        return True, f"Motorista {dados['nome']} cadastrado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Erro: Este motorista já está cadastrado nesta empresa."
    finally:
        conn.close()
def cadastrar_usuario(nome, login, senha, cpf, data_nascimento, email, empresa_id, role='Portaria'):
    """
    Cadastra um novo usuário na tabela `usuarios`.
    Recebe os dados do formulário de configuração.
    Retorna (True, mensagem) em caso de sucesso ou (False, mensagem de erro).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        hashed = hash_password(senha)
        cursor.execute('''
            INSERT INTO usuarios (nome, login, senha, cpf, data_nascimento, email, empresa_id, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nome, login, hashed, cpf, data_nascimento, email, empresa_id, role))
        conn.commit()
        return True, f"Usuário {nome} criado com sucesso."
    except sqlite3.IntegrityError as e:
        return False, "Erro: login já existe ou CPF duplicado."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def listar_usuarios(empresa_id):
    """
    Lista todos os usuários da empresa.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nome, login, cpf, data_nascimento, email, role
        FROM usuarios
        WHERE empresa_id = ?
        ORDER BY nome
    ''', (empresa_id,))
    usuarios = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return usuarios

def atualizar_usuario(usuario_id, nome, email, role, nova_senha=None):
    """
    Atualiza os dados de um usuário existente.
    Se nova_senha for informada, também atualiza a senha.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if nova_senha:
            hashed = hash_password(nova_senha)
            cursor.execute('''
                UPDATE usuarios
                SET nome = ?, email = ?, role = ?, senha = ?
                WHERE id = ?
            ''', (nome, email, role, hashed, usuario_id))
        else:
            cursor.execute('''
                UPDATE usuarios
                SET nome = ?, email = ?, role = ?
                WHERE id = ?
            ''', (nome, email, role, usuario_id))
        conn.commit()
        return True, f"Usuário {nome} atualizado com sucesso."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def excluir_usuario(usuario_id):
    """
    Exclui um usuário pelo ID.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM usuarios WHERE id = ?', (usuario_id,))
        conn.commit()
        return True, "Usuário excluído com sucesso."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def importar_motoristas_excel(file, empresa_id, usuario_nome):
    """
    Processa arquivo Excel, consulta SIL e cadastra motoristas.
    """
    try:
        df = pd.read_excel(file)
        # Tenta achar a coluna de CPF
        col_cpf = None
        for col in df.columns:
            if 'cpf' in str(col).lower():
                col_cpf = col
                break
        
        if not col_cpf:
            return False, "Erro: Coluna 'CPF' não encontrada no arquivo Excel."
        
        cpfs = df[col_cpf].dropna().astype(str).unique()
        importados = 0
        erros = 0
        duplicados = 0
        validados = 0
        bloqueados = 0
        vencidos = 0
        detalhes_processamento = []
        
        hoje = datetime.now()
        
        # Filtrar e limpar todos os CPFs válidos
        cpfs_limpos = []
        for cpf in cpfs:
            cpf_base = str(cpf).split('.')[0]
            cpf_limpo = ''.join(filter(str.isdigit, cpf_base)).zfill(11)
            if len(cpf_limpo) == 11 and cpf_limpo not in cpfs_limpos:
                cpfs_limpos.append(cpf_limpo)
                
        if not cpfs_limpos:
            return False, "Nenhum CPF válido encontrado no Excel."
            
        # Consultar Opentech em paralelo usando ThreadPoolExecutor
        resultados_opentech = {}
        def consultar_paralelo(c):
            return c, consultar_opentech(c, "TOKEN", usuario_nome)
            
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(consultar_paralelo, c) for c in cpfs_limpos]
            for future in futures:
                c, res = future.result()
                resultados_opentech[c] = res
                
        # Gravar no Banco de Dados SQLite sequencialmente
        for cpf_limpo in cpfs_limpos:
            res = resultados_opentech[cpf_limpo]
            if "Erro" not in res['status']:
                status_sil = res['status']
                status_norm = str(status_sil).strip().lower()
                
                # Status SIL
                if status_norm == "validado":
                    validados += 1
                    status_emoji = "✅"
                else:
                    bloqueados += 1
                    status_emoji = "❌"
                
                # Validade
                validade = res['validade']
                validade_status = "N/I"
                if validade and validade != "N/I":
                    try:
                        data_limpa = validade.split('T')[0]
                        dt_exp = datetime.strptime(data_limpa, "%Y-%m-%d")
                        if dt_exp < hoje:
                            vencidos += 1
                            validade_status = "❌ Vencido"
                        else:
                            validade_status = f"📅 Vence em {dt_exp.strftime('%d/%m/%Y')}"
                    except Exception:
                        validade_status = validade
                        
                dados = {
                    'nome': res['nome'], 'cpf': cpf_limpo, 'cnh': res['cnh'], 
                    'categoria': res['categoria'],
                    'status_sil': res['status'],
                    'data_consulta_sil': res['data_consulta'],
                    'validade': res['validade']
                }
                # Tenta cadastrar. Se já existir, a função cadastrar_motorista retorna False.
                sucesso, _ = cadastrar_motorista(dados, empresa_id)
                
                tipo_import = "Novo"
                if sucesso:
                    importados += 1
                else:
                    # Se já existe, vamos forçar a atualização dos dados SIL
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM motoristas WHERE cpf = ? AND empresa_id = ?", (cpf_limpo, empresa_id))
                    mot_id = cursor.fetchone()[0]
                    conn.close()
                    
                    ok, _ = atualizar_sil_motorista(mot_id, cpf_limpo, empresa_id, usuario_nome)
                    if ok: 
                        duplicados += 1
                        tipo_import = "Atualizado"
                    else: 
                        erros += 1
                        tipo_import = "Falha"
                        
                detalhes_processamento.append(
                    f"- **{res['nome']}** ({cpf_limpo}) | SIL: {status_emoji} {res['status']} | Validade: {validade_status} | ({tipo_import})"
                )
            else:
                erros += 1
                detalhes_processamento.append(f"- CPF **{cpf_limpo}** | ❌ Erro Opentech: {res['status']}")
        
        detalhes_str = "\n".join(detalhes_processamento)
        msg = (
            f"Importação de Excel concluída com sucesso!\n\n"
            f"📊 **Resumo do Processamento:**\n"
            f"- **Total de CPFs na Planilha:** {len(cpfs_limpos)}\n"
            f"- **Novos cadastrados:** {importados}\n"
            f"- **Atualizados (já cadastrados):** {duplicados}\n"
            f"- **Falhas no processamento:** {erros}\n\n"
            f"🔍 **Status SIL Opentech:**\n"
            f"- ✅ **Validados:** {validados}\n"
            f"- ❌ **Bloqueados/Outros:** {bloqueados}\n"
            f"- 📅 **Vencidos:** {vencidos}\n\n"
            f"📋 **Lista de Motoristas Processados:**\n"
            f"{detalhes_str}"
        )
        return True, msg
    except Exception as e:
        return False, f"Erro ao processar Excel: {e}"

def importar_motoristas_pdf(file, empresa_id, usuario_nome):
    """
    Processa arquivo PDF, busca CPFs via Regex, consulta SIL e cadastra motoristas.
    """
    try:
        # Lê o PDF usando fitz (PyMuPDF)
        doc = fitz.open(stream=file.read(), filetype="pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
            
        # Regex para buscar padrões de CPF
        padrao_cpf = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
        cpfs_encontrados = padrao_cpf.findall(texto)
        
        if not cpfs_encontrados:
            return False, "Nenhum CPF encontrado no arquivo PDF."
            
        # Limpar e remover duplicados
        cpfs = []
        for cpf in cpfs_encontrados:
            cpf_limpo = ''.join(filter(str.isdigit, cpf)).zfill(11)
            if len(cpf_limpo) == 11 and cpf_limpo not in cpfs:
                cpfs.append(cpf_limpo)
                
        importados = 0
        erros = 0
        duplicados = 0
        validados = 0
        bloqueados = 0
        vencidos = 0
        detalhes_processamento = []
        
        hoje = datetime.now()
        
        # Filtrar e limpar todos os CPFs válidos
        cpfs_limpos = []
        for cpf in cpfs_encontrados:
            cpf_limpo = ''.join(filter(str.isdigit, cpf)).zfill(11)
            if len(cpf_limpo) == 11 and cpf_limpo not in cpfs_limpos:
                cpfs_limpos.append(cpf_limpo)
                
        if not cpfs_limpos:
            return False, "Nenhum CPF válido encontrado no PDF."
            
        # Consultar Opentech em paralelo usando ThreadPoolExecutor
        resultados_opentech = {}
        def consultar_paralelo(c):
            return c, consultar_opentech(c, "TOKEN", usuario_nome)
            
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(consultar_paralelo, c) for c in cpfs_limpos]
            for future in futures:
                c, res = future.result()
                resultados_opentech[c] = res
                
        # Gravar no Banco de Dados SQLite sequencialmente
        for cpf_limpo in cpfs_limpos:
            res = resultados_opentech[cpf_limpo]
            if "Erro" not in res['status']:
                status_sil = res['status']
                status_norm = str(status_sil).strip().lower()
                
                # Status SIL
                if status_norm == "validado":
                    validados += 1
                    status_emoji = "✅"
                else:
                    bloqueados += 1
                    status_emoji = "❌"
                
                # Validade
                validade = res['validade']
                validade_status = "N/I"
                if validade and validade != "N/I":
                    try:
                        data_limpa = validade.split('T')[0]
                        dt_exp = datetime.strptime(data_limpa, "%Y-%m-%d")
                        if dt_exp < hoje:
                            vencidos += 1
                            validade_status = "❌ Vencido"
                        else:
                            validade_status = f"📅 Vence em {dt_exp.strftime('%d/%m/%Y')}"
                    except Exception:
                        validade_status = validade
                        
                dados = {
                    'nome': res['nome'], 'cpf': cpf_limpo, 'cnh': res['cnh'], 
                    'categoria': res['categoria'],
                    'status_sil': res['status'],
                    'data_consulta_sil': res['data_consulta'],
                    'validade': res['validade']
                }
                # Tenta cadastrar. Se já existir, a função cadastrar_motorista retorna False.
                sucesso, _ = cadastrar_motorista(dados, empresa_id)
                
                tipo_import = "Novo"
                if sucesso:
                    importados += 1
                else:
                    # Se já existe, vamos forçar a atualização dos dados SIL
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM motoristas WHERE cpf = ? AND empresa_id = ?", (cpf_limpo, empresa_id))
                    mot = cursor.fetchone()
                    conn.close()
                    
                    if mot:
                        ok, _ = atualizar_sil_motorista(mot[0], cpf_limpo, empresa_id, usuario_nome)
                        if ok: 
                            duplicados += 1
                            tipo_import = "Atualizado"
                        else: 
                            erros += 1
                            tipo_import = "Falha"
                    else:
                        erros += 1
                        tipo_import = "Falha"
                        
                detalhes_processamento.append(
                    f"- **{res['nome']}** ({cpf_limpo}) | SIL: {status_emoji} {res['status']} | Validade: {validade_status} | ({tipo_import})"
                )
            else:
                erros += 1
                detalhes_processamento.append(f"- CPF **{cpf_limpo}** | ❌ Erro Opentech: {res['status']}")
        
        detalhes_str = "\n".join(detalhes_processamento)
        msg = (
            f"Importação de PDF concluída com sucesso!\n\n"
            f"📊 **Resumo do Processamento:**\n"
            f"- **Total de CPFs no PDF:** {len(cpfs_limpos)}\n"
            f"- **Novos cadastrados:** {importados}\n"
            f"- **Atualizados (já cadastrados):** {duplicados}\n"
            f"- **Falhas no processamento:** {erros}\n\n"
            f"🔍 **Status SIL Opentech:**\n"
            f"- ✅ **Validados:** {validados}\n"
            f"- ❌ **Bloqueados/Outros:** {bloqueados}\n"
            f"- 📅 **Vencidos:** {vencidos}\n\n"
            f"📋 **Lista de Motoristas Processados:**\n"
            f"{detalhes_str}"
        )
        return True, msg
    except Exception as e:
        return False, f"Erro ao processar PDF: {e}"

def atualizar_sil_motorista(motorista_id, cpf, empresa_id, usuario_nome):
    """
    Força uma nova consulta na Opentech e atualiza o motorista existente.
    """
    res = consultar_opentech(cpf, "FORCE", usuario_nome)
    if "Erro" in res['status']:
        return False, res['status']
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE motoristas 
            SET nome = ?, cnh = ?, categoria = ?, status_sil = ?, 
                data_consulta_sil = ?, data_expiracao = ?
            WHERE id = ? AND empresa_id = ?
        ''', (res['nome'], res['cnh'], res['categoria'], res['status'], 
              res['data_consulta'], res['validade'], motorista_id, empresa_id))
        conn.commit()
        return True, f"SIL Atualizado com sucesso para {res['nome']}!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def editar_motorista(motorista_id, dados, empresa_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE motoristas 
        SET nome = ?, cnh = ?, categoria = ?
        WHERE id = ? AND empresa_id = ?
    ''', (dados['nome'], dados['cnh'], dados['categoria'], motorista_id, empresa_id))
    conn.commit()
    conn.close()
    return "Dados do motorista atualizados."

def deletar_motorista(motorista_id, empresa_id):
    conn = get_connection()
    cursor = conn.cursor()
    # Deletar ocorrências primeiro (Integridade)
    cursor.execute("DELETE FROM ocorrencias WHERE motorista_id = ? AND empresa_id = ?", (motorista_id, empresa_id))
    cursor.execute("DELETE FROM motoristas WHERE id = ? AND empresa_id = ?", (motorista_id, empresa_id))
    conn.commit()
    conn.close()
    return "Motorista e histórico removidos definitivamente."

def editar_ocorrencia(ocorrencia_id, motivo, gravidade, empresa_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ocorrencias 
        SET motivo = ?, gravidade = ?
        WHERE id = ? AND empresa_id = ?
    ''', (motivo, gravidade, ocorrencia_id, empresa_id))
    conn.commit()
    conn.close()
    return "Ocorrência atualizada com sucesso."

# --- MOTOR DE REGRAS E PENALIDADES ---
def registrar_ocorrencia(motorista_id, tipo, motivo, gravidade, data, usuario_id, empresa_id, data_fim_suspensao=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Buscar configurações da empresa
    cursor.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
    config = cursor.fetchone()
    
    # 1. Registrar a ocorrência
    cursor.execute('''
        INSERT INTO ocorrencias (tipo, motivo, gravidade, data, usuario_id, motorista_id, empresa_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (tipo, motivo, gravidade, data, usuario_id, motorista_id, empresa_id))
    
    feedback = f"Ocorrência de {tipo} registrada."

    # 2. Atualizar status do motorista baseado no tipo
    if tipo == "Suspensão":
        cursor.execute('''
            UPDATE motoristas 
            SET status_interno = 'Suspenso', data_fim_suspensao = ?
            WHERE id = ?
        ''', (data_fim_suspensao, motorista_id))
    
    elif tipo == "Exclusão":
        cursor.execute('''
            UPDATE motoristas 
            SET status_interno = 'Excluído'
            WHERE id = ?
        ''', (motorista_id,))
        
    elif tipo == "Advertência":
        # Lógica de Acúmulo Customizada
        intervalo = config['intervalo_dias_regra']
        limite_adv = config['limite_advertencias']
        limite_susp_exclusao = config['limite_suspensoes_exclusao']
        
        data_limite = (datetime.now() - timedelta(days=intervalo)).strftime("%Y-%m-%d")
        cursor.execute('''
            SELECT COUNT(*) FROM ocorrencias 
            WHERE motorista_id = ? AND tipo = 'Advertência' AND data >= ?
        ''', (motorista_id, data_limite))
        
        total_advertencias = cursor.fetchone()[0]
        
        if total_advertencias >= limite_adv:
            # 1. Verificar quantas suspensões o motorista já teve
            cursor.execute("SELECT COUNT(*) FROM ocorrencias WHERE motorista_id = ? AND tipo = 'Suspensão'", (motorista_id,))
            total_suspensoes = cursor.fetchone()[0]
            
            # 2. Decidir ação: Exclusão ou Suspensão Escalonada
            if total_suspensoes >= limite_susp_exclusao:
                cursor.execute("UPDATE motoristas SET status_interno = 'Excluído' WHERE id = ?", (motorista_id,))
                cursor.execute('''
                    INSERT INTO ocorrencias (tipo, motivo, gravidade, data, usuario_id, motorista_id, empresa_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ("Exclusão", f"Gatilho: Exclusão Automática por excesso de suspensões (>={limite_susp_exclusao}).", 
                      "Grave", datetime.now().strftime("%Y-%m-%d"), 0, motorista_id, empresa_id))
                feedback += " Crítico: Motorista atingiu limite de suspensões e foi EXCLUÍDO automaticamente."
            else:
                # 3. Definir dias da suspensão baseado no histórico
                dias = config['dias_susp_1'] if total_suspensoes == 0 else config['dias_susp_2']
                data_fim = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
                
                cursor.execute('''
                    UPDATE motoristas 
                    SET status_interno = 'Suspenso', data_fim_suspensao = ?
                    WHERE id = ?
                ''', (data_fim, motorista_id))
                
                # Log de Suspensão Automática
                cursor.execute('''
                    INSERT INTO ocorrencias (tipo, motivo, gravidade, data, usuario_id, motorista_id, empresa_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ("Suspensão", f"Gatilho: Suspensão Automática ({dias} dias) por excesso de advertências.", 
                      "Grave", datetime.now().strftime("%Y-%m-%d"), 0, motorista_id, empresa_id))
                
                feedback += f" Alerta: Motorista suspenso por {dias} dias (Ocorrência #{total_suspensoes + 1})."

    conn.commit()
    conn.close()
    return feedback

def get_prontuario(motorista_id, empresa_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Buscar configurações e CPF do motorista
    cursor.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
    config = cursor.fetchone()
    
    cursor.execute("SELECT * FROM motoristas WHERE id = ? AND empresa_id = ?", (motorista_id, empresa_id))
    motorista = cursor.fetchone()
    cpf = motorista['cpf']
    
    # Histórico de Ocorrências (Auditoria)
    # Se compartilhar_historico for 1, buscar pelo CPF em todas as empresas que também compartilham
    if config['compartilhar_historico']:
        cursor.execute('''
            SELECT o.*, u.nome as usuario_nome, e.nome as empresa_nome
            FROM ocorrencias o
            LEFT JOIN usuarios u ON o.usuario_id = u.id
            JOIN empresas e ON o.empresa_id = e.id
            JOIN motoristas m ON o.motorista_id = m.id
            WHERE m.cpf = ? AND (o.empresa_id = ? OR e.compartilhar_historico = 1)
            ORDER BY o.data DESC, o.id DESC
        ''', (cpf, empresa_id))
    else:
        cursor.execute('''
            SELECT o.*, u.nome as usuario_nome, e.nome as empresa_nome
            FROM ocorrencias o
            LEFT JOIN usuarios u ON o.usuario_id = u.id
            JOIN empresas e ON o.empresa_id = e.id
            WHERE o.motorista_id = ? AND o.empresa_id = ?
            ORDER BY o.data DESC, o.id DESC
        ''', (motorista_id, empresa_id))
        
    ocorrencias = cursor.fetchall()
    
    # Contagem de advertências recentes (usando intervalo dinâmico)
    intervalo = config['intervalo_dias_regra']
    data_limite = (datetime.now() - timedelta(days=intervalo)).strftime("%Y-%m-%d")
    cursor.execute('''
        SELECT COUNT(*) FROM ocorrencias 
        WHERE motorista_id = ? AND tipo = 'Advertência' AND data >= ?
    ''', (motorista_id, data_limite))
    recentes = cursor.fetchone()[0]
    
    conn.close()
    return motorista, ocorrencias, recentes

def get_stats_dashboard(empresa_id):
    """
    Estatísticas focadas em Portaria: Ativos, Vencidos e Liberações do Dia.
    """
    conn = get_connection()
    cursor = conn.cursor()
    hoje_dt = datetime.now()
    hoje_str = hoje_dt.strftime("%Y-%m-%d")
    
    # Consultas hoje (Total de pesquisas na portaria)
    cursor.execute("SELECT COUNT(*) FROM registros_acesso WHERE empresa_id = ? AND data_hora LIKE ?", (empresa_id, f"{hoje_str}%"))
    consultas_hoje = cursor.fetchone()[0]
    
    # Cadastros Ativos (Status Interno Ativo e Data Expiração > Hoje)
    cursor.execute('''
        SELECT COUNT(*) FROM motoristas 
        WHERE empresa_id = ? AND status_interno = 'Ativo' 
        AND (data_expiracao >= ? OR data_expiracao = 'N/I')
    ''', (empresa_id, hoje_str))
    cadastros_ativos = cursor.fetchone()[0]

    # Cadastros Vencidos (Status Interno Ativo mas Data Expiração < Hoje)
    cursor.execute('''
        SELECT COUNT(*) FROM motoristas 
        WHERE empresa_id = ? AND status_interno = 'Ativo' 
        AND data_expiracao < ? AND data_expiracao != 'N/I'
    ''', (empresa_id, hoje_str))
    cadastros_vencidos = cursor.fetchone()[0]
    
    # Liberações Hoje (Consultas que retornaram Validado ou Liberado hoje)
    cursor.execute('''
        SELECT COUNT(*) FROM registros_acesso 
        WHERE empresa_id = ? AND (status_resultado LIKE '%Validado%' OR status_resultado LIKE '%Liberado%')
        AND data_hora LIKE ?
    ''', (empresa_id, f"{hoje_str}%"))
    liberacoes_hoje = cursor.fetchone()[0]
    
    stats = {
        'cadastros_ativos': cadastros_ativos,
        'cadastros_vencidos': cadastros_vencidos,
        'liberacoes_hoje': liberacoes_hoje,
        'consultas_hoje': consultas_hoje
    }
    conn.close()
    return stats

def registrar_consulta_portaria(motorista_id, cpf, status, usuario_id, empresa_id):
    """
    Registra uma consulta no histórico de portaria.
    """
    conn = get_connection()
    cursor = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO registros_acesso (motorista_id, cpf, status_resultado, data_hora, usuario_id, empresa_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (motorista_id, cpf, status, agora, usuario_id, empresa_id))
    conn.commit()
    conn.close()

def listar_historico_acessos(empresa_id, limite=10):
    """
    Lista as últimas consultas feitas na portaria.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, m.nome as motorista_nome, u.nome as usuario_nome
        FROM registros_acesso r
        LEFT JOIN motoristas m ON r.motorista_id = m.id
        LEFT JOIN usuarios u ON r.usuario_id = u.id
        WHERE r.empresa_id = ?
        ORDER BY r.data_hora DESC
        LIMIT ?
    ''', (empresa_id, limite))
    acessos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return acessos
