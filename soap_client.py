import requests
import xml.etree.ElementTree as ET
import re
import logging
from config import WS_URL, WS_USUARIO, WS_SENHA, WS_DOMINIO, CD_PAS, CD_CLIENTE, get_status_label

logger = logging.getLogger("soap_client")

def post_soap(action, body):
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"http://tempuri.org/{action}"'
    }
    try:
        r = requests.post(WS_URL, data=body.encode("utf-8"), headers=headers, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.error(f"Erro na chamada SOAP {action}: {e}")
        return None

def find_text(xml_string, tag):
    if not xml_string:
        return None
    try:
        # Regex simples para evitar problemas com namespaces complexos do ET
        match = re.search(f"<{tag}>(.*?)</{tag}>", xml_string, re.DOTALL)
        return match.group(1) if match else None
    except Exception:
        return None

def sgr_login():
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/">
  <soapenv:Header/>
  <soapenv:Body>
    <tem:sgrLogin>
      <tem:usuario>{WS_USUARIO}</tem:usuario>
      <tem:senha>{WS_SENHA}</tem:senha>
      <tem:dominio>{WS_DOMINIO}</tem:dominio>
    </tem:sgrLogin>
  </soapenv:Body>
</soapenv:Envelope>"""
    
    resp = post_soap("sgrLogin", body)
    return find_text(resp, "ReturnKey")

def consultar_motorista(cpf):
    """
    Consulta o status do motorista na OpenTech via sgrConsultaPFV3.
    Retorna um dicionário com nome, status_original, status_label e data_expiracao.
    """
    chave = sgr_login()
    if not chave:
        return {"error": "Falha na autenticação com OpenTech"}

    cpf_limpo = ''.join(filter(str.isdigit, cpf))
    
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/">
  <soapenv:Header/>
  <soapenv:Body>
    <tem:sgrConsultaPFV3>
      <tem:chaveacesso>{chave}</tem:chaveacesso>
      <tem:cdpas>{CD_PAS}</tem:cdpas>
      <tem:cdcliente>{CD_CLIENTE}</tem:cdcliente>
      <tem:cdpaisorigem>1</tem:cdpaisorigem>
      <tem:nrdocumento>{cpf_limpo}</tem:nrdocumento>
      <tem:cdOrigemConsulta>1</tem:cdOrigemConsulta>
    </tem:sgrConsultaPFV3>
  </soapenv:Body>
</soapenv:Envelope>"""

    resp = post_soap("sgrConsultaPFV3", body)
    if not resp:
        return {"error": "Sem resposta da OpenTech"}

    return_id = find_text(resp, "ReturnID")
    if return_id != "0":
        desc = find_text(resp, "ReturnDescription")
        return {"error": desc or f"Erro ID {return_id}"}

    # Extração de dados do diffgram
    nome = find_text(resp, "DSNOME")
    status_cod = find_text(resp, "FLSITPF")
    status_desc = find_text(resp, "DSSITUACAO")
    expira = find_text(resp, "DTEXPIRACAO")
    cnh = find_text(resp, "NRCNH") or find_text(resp, "CNH") # Campos variam dependendo da versão
    cat = find_text(resp, "CDCATCNH") or find_text(resp, "DSCATCNH")

    return {
        "nome": nome,
        "status_cod": status_cod,
        "status_label": status_desc if status_desc else get_status_label(status_cod),
        "data_expiracao": expira,
        "cnh": cnh,
        "categoria": cat,
        "raw_status": status_desc
    }
